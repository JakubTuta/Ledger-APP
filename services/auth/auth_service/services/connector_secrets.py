"""Encryption at rest for connector credentials.

Connector configs are JSONB in the auth DB. The fields that grant access to an
external system - the webhook signing secret, PagerDuty/Opsgenie keys and the
webhook/Slack/Discord URL (posting to one needs nothing but the URL) - are
stored as Fernet tokens, so a database dump or backup does not hand them out.

CONNECTOR_SECRETS_KEY holds one or more comma-separated Fernet keys: the first
encrypts, every key decrypts, which is how a key is rotated (prepend the new
key, restart; the startup backfill re-encrypts everything under it). Values
saved before encryption existed are plain strings; they read back unchanged
until that backfill rewrites them.

analytics_workers.services.connector_secrets is a decrypt-only copy - the two
services share no package - so keep the format in sync.
"""

import functools

import cryptography.fernet as fernet
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

import auth_service.config as config
import auth_service.models as models

SECRET_FIELDS = ("hmac_secret", "integration_key", "api_key", "url")
_PREFIX = "enc:v1:"


class ConnectorSecretsKeyError(RuntimeError):
    pass


@functools.lru_cache
def _ciphers(key_setting: str) -> tuple[fernet.Fernet, fernet.MultiFernet]:
    keys = [key.strip() for key in key_setting.split(",") if key.strip()]
    if not keys:
        raise ConnectorSecretsKeyError(
            "CONNECTOR_SECRETS_KEY is not set. Generate one with: python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        primary_and_old = [fernet.Fernet(key) for key in keys]
    except ValueError as e:
        raise ConnectorSecretsKeyError(f"CONNECTOR_SECRETS_KEY holds an invalid key: {e}")
    return primary_and_old[0], fernet.MultiFernet(primary_and_old)


def ensure_key_configured() -> None:
    _ciphers(config.settings.CONNECTOR_SECRETS_KEY)


def _is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def _encrypt_value(value: str) -> str:
    _, cipher = _ciphers(config.settings.CONNECTOR_SECRETS_KEY)
    return _PREFIX + cipher.encrypt(value.encode()).decode()


def _decrypt_value(value: str) -> str:
    _, cipher = _ciphers(config.settings.CONNECTOR_SECRETS_KEY)
    return cipher.decrypt(value[len(_PREFIX) :].encode()).decode()


def encrypt_config(connector_config: dict) -> dict:
    """Return `connector_config` with every plaintext secret field encrypted."""
    return {
        field: (
            _encrypt_value(value)
            if field in SECRET_FIELDS
            and isinstance(value, str)
            and value
            and not _is_encrypted(value)
            else value
        )
        for field, value in connector_config.items()
    }


def decrypt_config(connector_config: dict) -> dict:
    return {
        field: _decrypt_value(value) if _is_encrypted(value) else value
        for field, value in connector_config.items()
    }


def needs_rewrite(connector_config: dict) -> bool:
    """True if a secret is still plaintext or was encrypted under an old key."""
    primary, _ = _ciphers(config.settings.CONNECTOR_SECRETS_KEY)
    for field in SECRET_FIELDS:
        value = connector_config.get(field)
        if not isinstance(value, str) or not value:
            continue
        if not _is_encrypted(value):
            return True
        try:
            primary.decrypt(value[len(_PREFIX) :].encode())
        except fernet.InvalidToken:
            return True
    return False


def reencrypt_config(connector_config: dict) -> dict:
    """Decrypt with any configured key and encrypt again under the primary one."""
    return encrypt_config(decrypt_config(connector_config))


async def rewrite_stored_configs(session: AsyncSession) -> int:
    """Encrypt plaintext secrets and move old-key ones to the primary key.

    Run at startup. Each row is rewritten only if it still holds what was read
    (compare-and-set), so a concurrent edit or a second replica doing the same
    pass is never overwritten. Returns the number of rows rewritten.
    """
    rows = (await session.execute(sa.select(models.Connector.id, models.Connector.config))).all()
    rewritten = 0
    for connector_id, stored in rows:
        if not stored or not needs_rewrite(stored):
            continue
        try:
            fresh = reencrypt_config(stored)
        except fernet.InvalidToken:
            raise ConnectorSecretsKeyError(
                f"Connector {connector_id} holds secrets no configured key can decrypt; keep the "
                "previous key in CONNECTOR_SECRETS_KEY (after the new one) until this has run"
            )
        result = await session.execute(
            sa.update(models.Connector)
            .where(models.Connector.id == connector_id, models.Connector.config == stored)
            .values(config=fresh, updated_at=models.Connector.updated_at)
        )
        rewritten += result.rowcount
    await session.commit()
    return rewritten
