import cryptography.fernet as fernet
import pytest

import ledger_common.connector_secrets as connector_secrets

_KEY = "IFmJbAUZIllVQ4ShSzg7B4tGgQ2R1A_wQzzMmlqSUMI="
_NEW_KEY = "2jxIqg-faRcqQOw4cyaxD0Vbw9kYy4JJSU9rF6oVIks="


def _encrypted(value: str, key: str = _KEY) -> str:
    return "enc:v1:" + fernet.Fernet(key).encrypt(value.encode()).decode()


class TestEncryptConfig:
    def test_only_plaintext_secret_fields_are_encrypted(self):
        stored = connector_secrets.encrypt_config(
            {"url": "https://hooks.example.com/x", "address": "ops@example.com", "api_key": ""},
            _KEY,
        )

        assert stored["url"].startswith("enc:v1:")
        assert stored["address"] == "ops@example.com"
        assert stored["api_key"] == ""

    def test_an_already_encrypted_value_is_not_encrypted_twice(self):
        value = _encrypted("secret")

        assert connector_secrets.encrypt_config({"api_key": value}, _KEY) == {"api_key": value}

    def test_round_trip(self):
        original = {"url": "https://hooks.example.com/x", "hmac_secret": "s3cret"}

        stored = connector_secrets.encrypt_config(original, _KEY)

        assert connector_secrets.decrypt_config(stored, _KEY) == original


class TestDecryptConfig:
    def test_plain_values_saved_before_encryption_pass_through(self):
        assert connector_secrets.decrypt_config({"api_key": "plain"}, _KEY) == {"api_key": "plain"}

    def test_any_configured_key_decrypts_during_rotation(self):
        stored = {"api_key": _encrypted("og-key", key=_KEY)}

        assert connector_secrets.decrypt_config(stored, f"{_NEW_KEY},{_KEY}") == {
            "api_key": "og-key"
        }

    def test_a_wrong_key_is_reported_not_returned_as_ciphertext(self):
        stored = {"api_key": _encrypted("og-key", key=_KEY)}

        with pytest.raises(connector_secrets.ConnectorSecretsError):
            connector_secrets.decrypt_config(stored, _NEW_KEY)


class TestKeySetting:
    def test_missing_key_is_an_error(self):
        with pytest.raises(connector_secrets.ConnectorSecretsError, match="not set"):
            connector_secrets.ensure_key_configured("")

    def test_invalid_key_is_an_error(self):
        with pytest.raises(connector_secrets.ConnectorSecretsError, match="invalid"):
            connector_secrets.ensure_key_configured("not-a-fernet-key")


class TestRotation:
    def test_plaintext_and_old_key_values_need_a_rewrite(self):
        assert connector_secrets.needs_rewrite({"api_key": "plain"}, _KEY)
        assert connector_secrets.needs_rewrite(
            {"api_key": _encrypted("v", key=_KEY)}, f"{_NEW_KEY},{_KEY}"
        )

    def test_value_under_the_primary_key_is_left_alone(self):
        assert not connector_secrets.needs_rewrite({"api_key": _encrypted("v", key=_KEY)}, _KEY)
        assert not connector_secrets.needs_rewrite(
            {"address": "x@example.com", "api_key": ""}, _KEY
        )

    def test_reencrypt_moves_values_to_the_primary_key(self):
        stored = {"api_key": _encrypted("v", key=_KEY)}

        rotated = connector_secrets.reencrypt_config(stored, f"{_NEW_KEY},{_KEY}")

        assert connector_secrets.decrypt_config(rotated, _NEW_KEY) == {"api_key": "v"}
