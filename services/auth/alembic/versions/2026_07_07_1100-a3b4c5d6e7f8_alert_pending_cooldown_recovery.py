"""add pending/cooldown/recovery fields to alert_rules

Revision ID: a3b4c5d6e7f8
Revises: f1a2b3c4d5e6
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa


revision = 'a3b4c5d6e7f8'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'alert_rules',
        sa.Column('for_minutes', sa.SmallInteger(), nullable=False, server_default='0'),
    )
    op.add_column(
        'alert_rules',
        sa.Column('cooldown_minutes', sa.SmallInteger(), nullable=False, server_default='0'),
    )
    op.add_column(
        'alert_rules',
        sa.Column('last_notified_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'alert_rules',
        sa.Column('pending_since', sa.DateTime(timezone=True), nullable=True),
    )

    op.drop_constraint('check_alert_state', 'alert_rules', type_='check')
    op.create_check_constraint(
        'check_alert_state',
        'alert_rules',
        "state IN ('ok', 'pending', 'firing')",
    )


def downgrade() -> None:
    op.drop_constraint('check_alert_state', 'alert_rules', type_='check')
    op.create_check_constraint(
        'check_alert_state',
        'alert_rules',
        "state IN ('ok', 'firing')",
    )

    op.drop_column('alert_rules', 'pending_since')
    op.drop_column('alert_rules', 'last_notified_at')
    op.drop_column('alert_rules', 'cooldown_minutes')
    op.drop_column('alert_rules', 'for_minutes')
