"""add_refresh_tokens_table

Revision ID: e5a7b2f9c3d1
Revises: d4f2a8b3e7c6
Create Date: 2025-12-03 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5a7b2f9c3d1'
down_revision = 'd4f2a8b3e7c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('account_id', sa.BigInteger(), nullable=False),
        sa.Column('token_hash', sa.CHAR(60), nullable=False),
        sa.Column('device_info', sa.VARCHAR(255), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['account_id'],
            ['accounts.id'],
            name='fk_refresh_tokens_account',
            ondelete='CASCADE'
        ),
        sa.UniqueConstraint('token_hash', name='uq_refresh_tokens_token_hash')
    )

    op.create_index('idx_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'])
    op.create_index('idx_refresh_tokens_account_id', 'refresh_tokens', ['account_id'])

    op.create_index(
        'idx_refresh_tokens_active',
        'refresh_tokens',
        ['token_hash', 'account_id', 'expires_at'],
        postgresql_where=sa.text('revoked = FALSE')
    )

    op.create_index(
        'idx_refresh_tokens_cleanup',
        'refresh_tokens',
        ['expires_at'],
        postgresql_where=sa.text('revoked = FALSE')
    )


def downgrade() -> None:
    op.drop_index('idx_refresh_tokens_cleanup', table_name='refresh_tokens')
    op.drop_index('idx_refresh_tokens_active', table_name='refresh_tokens')
    op.drop_index('idx_refresh_tokens_account_id', table_name='refresh_tokens')
    op.drop_index('idx_refresh_tokens_token_hash', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
