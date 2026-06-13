"""migrate api_key hash from bcrypt to SHA-256

All existing bcrypt-hashed API keys are revoked — users must regenerate.
New keys store a hex-encoded SHA-256 digest (64 chars) enabling O(1) lookup
via the existing unique index on key_hash.

Revision ID: f1a2b3c4d5e6
Revises: e9f3a7b2c5d1
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa


revision = 'f1a2b3c4d5e6'
down_revision = 'e9f3a7b2c5d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE api_keys SET status = 'revoked' WHERE status = 'active'")

    op.alter_column(
        'api_keys',
        'key_hash',
        existing_type=sa.CHAR(60),
        type_=sa.CHAR(64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'api_keys',
        'key_hash',
        existing_type=sa.CHAR(64),
        type_=sa.CHAR(60),
        existing_nullable=False,
    )
