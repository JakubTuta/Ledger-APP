"""widen_token_hash_char60_to_char64

Revision ID: a1b2c3d4e5f6
Revises: f3a8b2c9d4e7
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'f3a8b2c9d4e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'refresh_tokens',
        'token_hash',
        type_=sa.CHAR(64),
        existing_type=sa.CHAR(60),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'refresh_tokens',
        'token_hash',
        type_=sa.CHAR(60),
        existing_type=sa.CHAR(64),
        existing_nullable=False,
    )
