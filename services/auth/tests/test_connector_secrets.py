import json
import unittest.mock

import auth_service.config as config
import auth_service.database as database
import auth_service.models as models
import auth_service.services.connector_secrets as connector_secrets
import pytest
import sqlalchemy as sa
from auth_service.proto import auth_pb2

from .test_base import BaseGrpcTest

_OLD_KEY = "IFmJbAUZIllVQ4ShSzg7B4tGgQ2R1A_wQzzMmlqSUMI="
_NEW_KEY = "2jxIqg-faRcqQOw4cyaxD0Vbw9kYy4JJSU9rF6oVIks="


async def _stored_config(connector_id: int) -> dict:
    async with database.get_session() as session:
        return (
            await session.execute(
                sa.select(models.Connector.config).where(models.Connector.id == connector_id)
            )
        ).scalar_one()


@pytest.mark.asyncio
class TestConnectorSecretsAtRest(BaseGrpcTest):
    async def _account_id(self) -> int:
        response = await self.stub.Register(
            auth_pb2.RegisterRequest(email="owner@example.com", password="Password123", plan="free")
        )
        return response.account_id

    async def _create(self, account_id: int, kind: str, connector_config: dict) -> int:
        response = await self.stub.CreateConnector(
            auth_pb2.CreateConnectorRequest(
                account_id=account_id, kind=kind, name=kind, config=json.dumps(connector_config)
            )
        )
        return response.connector.id

    async def test_credentials_are_stored_encrypted(self):
        account_id = await self._account_id()
        connector_id = await self._create(
            account_id,
            "webhook",
            {"url": "https://hooks.example.com/abc", "hmac_secret": "s3cr3t-value"},
        )

        stored = await _stored_config(connector_id)

        assert stored["url"].startswith("enc:v1:")
        assert stored["hmac_secret"].startswith("enc:v1:")
        assert "hooks.example.com" not in json.dumps(stored)
        assert "s3cr3t-value" not in json.dumps(stored)

    async def test_listing_shows_the_url_but_never_write_only_secrets(self):
        account_id = await self._account_id()
        await self._create(
            account_id,
            "webhook",
            {"url": "https://hooks.example.com/abc", "hmac_secret": "s3cr3t-value"},
        )

        response = await self.stub.ListConnectors(
            auth_pb2.ListConnectorsRequest(account_id=account_id)
        )
        (webhook,) = [c for c in response.connectors if c.kind == "webhook"]

        assert json.loads(webhook.config) == {"url": "https://hooks.example.com/abc"}

    async def test_test_fire_lookup_gets_the_decrypted_credentials(self):
        account_id = await self._account_id()
        connector_id = await self._create(account_id, "pagerduty", {"integration_key": "pd-key"})

        public = await self.stub.GetConnector(
            auth_pb2.GetConnectorRequest(connector_id=connector_id, account_id=account_id)
        )
        internal = await self.stub.GetConnector(
            auth_pb2.GetConnectorRequest(
                connector_id=connector_id, account_id=account_id, include_secrets=True
            )
        )

        assert "integration_key" not in json.loads(public.connector.config)
        assert json.loads(internal.connector.config)["integration_key"] == "pd-key"

    async def test_update_without_the_secret_keeps_it(self):
        account_id = await self._account_id()
        connector_id = await self._create(
            account_id,
            "webhook",
            {"url": "https://hooks.example.com/abc", "hmac_secret": "s3cr3t-value"},
        )

        await self.stub.UpdateConnector(
            auth_pb2.UpdateConnectorRequest(
                connector_id=connector_id,
                account_id=account_id,
                config=json.dumps({"url": "https://hooks.example.com/new"}),
            )
        )

        stored = connector_secrets.decrypt_config(await _stored_config(connector_id))
        assert stored == {"url": "https://hooks.example.com/new", "hmac_secret": "s3cr3t-value"}

    async def test_startup_pass_encrypts_rows_saved_before_encryption(self):
        account_id = await self._account_id()
        async with database.get_session() as session:
            legacy = models.Connector(
                account_id=account_id,
                kind="opsgenie",
                name="legacy",
                config={"api_key": "plain-key"},
                enabled=True,
            )
            session.add(legacy)
            await session.commit()
            legacy_id = legacy.id

        async with database.get_session() as session:
            first_pass = await connector_secrets.rewrite_stored_configs(session)
        async with database.get_session() as session:
            second_pass = await connector_secrets.rewrite_stored_configs(session)

        stored = await _stored_config(legacy_id)
        assert first_pass == 1
        assert second_pass == 0
        assert stored["api_key"].startswith("enc:v1:")
        assert connector_secrets.decrypt_config(stored) == {"api_key": "plain-key"}

    async def test_rotation_moves_secrets_to_the_new_key(self):
        account_id = await self._account_id()
        with unittest.mock.patch.object(config.settings, "CONNECTOR_SECRETS_KEY", _OLD_KEY):
            connector_id = await self._create(account_id, "opsgenie", {"api_key": "og-key"})

        with unittest.mock.patch.object(
            config.settings, "CONNECTOR_SECRETS_KEY", f"{_NEW_KEY},{_OLD_KEY}"
        ):
            async with database.get_session() as session:
                rotated = await connector_secrets.rewrite_stored_configs(session)

        with unittest.mock.patch.object(config.settings, "CONNECTOR_SECRETS_KEY", _NEW_KEY):
            stored = connector_secrets.decrypt_config(await _stored_config(connector_id))

        assert rotated == 1
        assert stored == {"api_key": "og-key"}
