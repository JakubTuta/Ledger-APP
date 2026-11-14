"""Encryption at rest for connector credentials.

Connector configs are JSONB in the auth DB. The fields that grant access to an external system -
the webhook signing secret, PagerDuty/Opsgenie keys and the webhook/Slack/Discord URL (posting to
one needs nothing but the URL) - are stored as Fernet tokens, so a database dump or backup does
not hand them out.

The key setting (CONNECTOR_SECRETS_KEY) holds one or more comma-separated Fernet keys: the first
encrypts, every key decrypts, which is how a key is rotated (prepend the new key, restart; the
auth service's startup backfill re-encrypts everything under it). Values saved before encryption
existed are plain strings; they read back unchanged until that backfill rewrites them.

Every function takes the key setting explicitly, so a service passes its own settings value and a
test can swap it. Auth encrypts and decrypts; analytics only decrypts.
"""

import cryptography.fernet as fernet

SECRET_FIELDS = ("hmac_secret", "integration_key", "api_key", "url")
_PREFIX = "enc:v1:"


class ConnectorSecretsError(RuntimeError):
    """The key is missing or invalid, or a stored value can't be decrypted with any key."""


def _ciphers(key_setting: str) -> tuple[fernet.Fernet, fernet.MultiFernet]:
    keys = [key.strip() for key in key_setting.split(",") if key.strip()]
    if not keys:
        raise ConnectorSecretsError(
            "CONNECTOR_SECRETS_KEY is not set. Generate one with: python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        primary_and_old = [fernet.Fernet(key) for key in keys]
    except ValueError as e:
        raise ConnectorSecretsError(f"CONNECTOR_SECRETS_KEY holds an invalid key: {e}")
    return primary_and_old[0], fernet.MultiFernet(primary_and_old)


def ensure_key_configured(key_setting: str) -> None:
    _ciphers(key_setting)


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def _decrypt_value(value: str, key_setting: str, field: str) -> str:
    _, cipher = _ciphers(key_setting)
    try:
        return cipher.decrypt(value[len(_PREFIX) :].encode()).decode()
    except fernet.InvalidToken:
        raise ConnectorSecretsError(
            f"connector field {field!r} can't be decrypted with CONNECTOR_SECRETS_KEY"
        )


def encrypt_config(connector_config: dict, key_setting: str) -> dict:
    """Return `connector_config` with every plaintext secret field encrypted."""
    _, cipher = _ciphers(key_setting)
    return {
        field: (
            _PREFIX + cipher.encrypt(value.encode()).decode()
            if field in SECRET_FIELDS
            and isinstance(value, str)
            and value
            and not is_encrypted(value)
            else value
        )
        for field, value in connector_config.items()
    }


def decrypt_config(connector_config: dict, key_setting: str) -> dict:
    """Return `connector_config` with its encrypted fields in plaintext.

    Raises ConnectorSecretsError if a field can't be decrypted with any key.
    """
    return {
        field: _decrypt_value(value, key_setting, field) if is_encrypted(value) else value
        for field, value in connector_config.items()
    }


def needs_rewrite(connector_config: dict, key_setting: str) -> bool:
    """True if a secret is still plaintext or was encrypted under an old key."""
    primary, _ = _ciphers(key_setting)
    for field in SECRET_FIELDS:
        value = connector_config.get(field)
        if not isinstance(value, str) or not value:
            continue
        if not is_encrypted(value):
            return True
        try:
            primary.decrypt(value[len(_PREFIX) :].encode())
        except fernet.InvalidToken:
            return True
    return False


def reencrypt_config(connector_config: dict, key_setting: str) -> dict:
    """Decrypt with any configured key and encrypt again under the primary one."""
    return encrypt_config(decrypt_config(connector_config, key_setting), key_setting)
