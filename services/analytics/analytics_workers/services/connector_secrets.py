"""Decryption of connector credentials stored by the auth service.

Decrypt-only copy of auth_service.services.connector_secrets (the services
share no package): secret fields are stored as "enc:v1:<Fernet token>" under
the comma-separated keys in CONNECTOR_SECRETS_KEY, which must match the auth
service's value. Plain strings are values saved before encryption existed and
pass through unchanged.
"""

import functools

import cryptography.fernet as fernet

import analytics_workers.config as config

_PREFIX = "enc:v1:"


class ConnectorSecretsError(RuntimeError):
    pass


@functools.lru_cache
def _cipher(key_setting: str) -> fernet.MultiFernet:
    keys = [key.strip() for key in key_setting.split(",") if key.strip()]
    if not keys:
        raise ConnectorSecretsError("CONNECTOR_SECRETS_KEY is not set")
    try:
        return fernet.MultiFernet([fernet.Fernet(key) for key in keys])
    except ValueError as e:
        raise ConnectorSecretsError(f"CONNECTOR_SECRETS_KEY holds an invalid key: {e}")


def decrypt_config(connector_config: dict) -> dict:
    """Return `connector_config` with its encrypted fields in plaintext.

    Raises ConnectorSecretsError if a field can't be decrypted with any key.
    """
    decrypted = {}
    for field, value in connector_config.items():
        if isinstance(value, str) and value.startswith(_PREFIX):
            cipher = _cipher(config.settings.CONNECTOR_SECRETS_KEY)
            try:
                value = cipher.decrypt(value[len(_PREFIX) :].encode()).decode()
            except fernet.InvalidToken:
                raise ConnectorSecretsError(
                    f"connector field {field!r} can't be decrypted with CONNECTOR_SECRETS_KEY"
                )
        decrypted[field] = value
    return decrypted
