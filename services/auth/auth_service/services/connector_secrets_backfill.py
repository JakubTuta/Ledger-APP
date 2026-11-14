"""Startup pass that brings stored connector secrets under the current encryption key.

The format and the cipher live in ledger_common.connector_secrets; this is the part that needs
the auth DB models.
"""

import ledger_common.connector_secrets as connector_secrets
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

import auth_service.config as config
import ledger_common.models.auth as models


async def rewrite_stored_configs(session: AsyncSession) -> int:
    """Encrypt plaintext secrets and move old-key ones to the primary key.

    Run at startup. Each row is rewritten only if it still holds what was read
    (compare-and-set), so a concurrent edit or a second replica doing the same
    pass is never overwritten. Returns the number of rows rewritten.
    """
    key = config.settings.CONNECTOR_SECRETS_KEY
    rows = (await session.execute(sa.select(models.Connector.id, models.Connector.config))).all()
    rewritten = 0
    for connector_id, stored in rows:
        if not stored or not connector_secrets.needs_rewrite(stored, key):
            continue
        try:
            fresh = connector_secrets.reencrypt_config(stored, key)
        except connector_secrets.ConnectorSecretsError:
            raise connector_secrets.ConnectorSecretsError(
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
