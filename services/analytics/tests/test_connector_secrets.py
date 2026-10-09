import datetime
from unittest.mock import AsyncMock, patch

import cryptography.fernet as fernet
import pytest

import analytics_workers.config as config
import analytics_workers.jobs.alert_evaluator as alert_evaluator
import analytics_workers.services.connector_secrets as connector_secrets

_KEY = "IFmJbAUZIllVQ4ShSzg7B4tGgQ2R1A_wQzzMmlqSUMI="
_OTHER_KEY = "2jxIqg-faRcqQOw4cyaxD0Vbw9kYy4JJSU9rF6oVIks="


def _encrypted(value: str, key: str = _KEY) -> str:
    return "enc:v1:" + fernet.Fernet(key).encrypt(value.encode()).decode()


class TestDecryptConfig:
    def test_encrypted_fields_are_decrypted_and_plain_ones_pass_through(self):
        stored = {"url": _encrypted("https://hooks.example.com/x"), "address": "ops@example.com"}

        with patch.object(config.settings, "CONNECTOR_SECRETS_KEY", _KEY):
            decrypted = connector_secrets.decrypt_config(stored)

        assert decrypted == {"url": "https://hooks.example.com/x", "address": "ops@example.com"}

    def test_any_configured_key_decrypts_during_rotation(self):
        stored = {"api_key": _encrypted("og-key", key=_KEY)}

        with patch.object(config.settings, "CONNECTOR_SECRETS_KEY", f"{_OTHER_KEY},{_KEY}"):
            assert connector_secrets.decrypt_config(stored) == {"api_key": "og-key"}

    def test_a_wrong_key_is_reported_not_returned_as_ciphertext(self):
        stored = {"api_key": _encrypted("og-key", key=_KEY)}

        with patch.object(config.settings, "CONNECTOR_SECRETS_KEY", _OTHER_KEY):
            with pytest.raises(connector_secrets.ConnectorSecretsError):
                connector_secrets.decrypt_config(stored)


@pytest.mark.asyncio
class TestDispatchDecryptsCredentials:
    async def _dispatch(self, connector_config: dict) -> list[dict]:
        return await alert_evaluator._dispatch_to_connectors(
            [(7, "webhook", "hook", connector_config)],
            1,
            1,
            "rule",
            "error_rate_all",
            ">",
            1.0,
            "%",
            2.0,
            "warning",
            datetime.datetime.now(datetime.timezone.utc),
            AsyncMock(),
            event_state="firing",
        )

    async def test_webhook_is_posted_to_the_decrypted_url_and_signed_with_the_secret(self):
        post = AsyncMock(return_value=(True, None))
        connector_config = {
            "url": _encrypted("https://hooks.example.com/x"),
            "hmac_secret": _encrypted("signing-secret"),
        }

        with (
            patch.object(config.settings, "CONNECTOR_SECRETS_KEY", _KEY),
            patch.object(alert_evaluator, "_notification_recipients", AsyncMock(return_value=[])),
            patch.object(alert_evaluator, "_post_webhook", post),
        ):
            sent = await self._dispatch(connector_config)

        assert post.await_args.args[:2] == ("https://hooks.example.com/x", "signing-secret")
        assert sent[0]["delivered"] is True

    async def test_undecryptable_connector_is_recorded_as_failed_delivery(self):
        post = AsyncMock(return_value=(True, None))

        with (
            patch.object(config.settings, "CONNECTOR_SECRETS_KEY", _OTHER_KEY),
            patch.object(alert_evaluator, "_notification_recipients", AsyncMock(return_value=[])),
            patch.object(alert_evaluator, "_post_webhook", post),
        ):
            sent = await self._dispatch({"url": _encrypted("https://hooks.example.com/x")})

        post.assert_not_awaited()
        assert sent[0]["delivered"] is False
        assert "decrypt" in sent[0]["error"]
