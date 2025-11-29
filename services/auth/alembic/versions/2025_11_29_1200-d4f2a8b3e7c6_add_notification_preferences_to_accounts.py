"""add_notification_preferences_to_accounts

Revision ID: d4f2a8b3e7c6
Revises: f8c9d3e2a1b0
Create Date: 2025-11-29 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'd4f2a8b3e7c6'
down_revision = 'f8c9d3e2a1b0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'accounts',
        sa.Column(
            'notification_preferences',
            postgresql.JSONB,
            nullable=False,
            server_default='{"enabled": true, "projects": {}}'
        )
    )

    op.create_index(
        'idx_accounts_notification_prefs',
        'accounts',
        ['notification_preferences'],
        postgresql_using='gin'
    )


def downgrade() -> None:
    op.drop_index('idx_accounts_notification_prefs', table_name='accounts')
    op.drop_column('accounts', 'notification_preferences')
