"""alert connectors v2: slack/discord/pagerduty/opsgenie, escalation, maintenance windows

Revision ID: d4e5f6a7b8c9
Revises: c7d8e9f0a1b2
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Widen connector kind check constraint to allow the new connector kinds.
    op.drop_constraint('check_connector_kind', 'connectors', type_='check')
    op.create_check_constraint(
        'check_connector_kind',
        'connectors',
        "kind IN ('in_app', 'email', 'webhook', 'slack', 'discord', 'pagerduty', 'opsgenie')",
    )

    # Escalation: after firing for N minutes, notify an additional connector once.
    op.add_column(
        'alert_rules',
        sa.Column('escalation_after_minutes', sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        'alert_rules',
        sa.Column('escalate_connector_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_alert_rules_escalate_connector_id',
        'alert_rules',
        'connectors',
        ['escalate_connector_id'],
        ['id'],
        ondelete='SET NULL',
    )
    # Tracks whether the current firing episode has already been escalated,
    # so escalation only fires once per episode. Cleared on resolve / re-fire.
    op.add_column(
        'alert_rules',
        sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Maintenance windows: suppress dispatch for a project during a time range,
    # optionally recurring daily/weekly.
    op.create_table(
        'maintenance_windows',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            'project_id',
            sa.BigInteger(),
            sa.ForeignKey('projects.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('name', sa.VARCHAR(length=255), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('recurrence', sa.VARCHAR(length=20), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
    )
    op.create_index(
        'idx_maintenance_windows_project_id', 'maintenance_windows', ['project_id']
    )
    op.create_check_constraint(
        'check_maintenance_window_recurrence',
        'maintenance_windows',
        "recurrence IN ('none', 'daily', 'weekly') OR recurrence IS NULL",
    )

    # Ack / snooze support on alert events.
    op.add_column(
        'alert_events',
        sa.Column('acked_by', sa.Integer(), nullable=True),
    )
    op.add_column(
        'alert_events',
        sa.Column('acked_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'alert_events',
        sa.Column('snoozed_until', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_alert_events_acked_by',
        'alert_events',
        'accounts',
        ['acked_by'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_alert_events_acked_by', 'alert_events', type_='foreignkey')
    op.drop_column('alert_events', 'snoozed_until')
    op.drop_column('alert_events', 'acked_at')
    op.drop_column('alert_events', 'acked_by')

    op.drop_constraint(
        'check_maintenance_window_recurrence', 'maintenance_windows', type_='check'
    )
    op.drop_index('idx_maintenance_windows_project_id', table_name='maintenance_windows')
    op.drop_table('maintenance_windows')

    op.drop_column('alert_rules', 'escalated_at')
    op.drop_constraint(
        'fk_alert_rules_escalate_connector_id', 'alert_rules', type_='foreignkey'
    )
    op.drop_column('alert_rules', 'escalate_connector_id')
    op.drop_column('alert_rules', 'escalation_after_minutes')

    op.drop_constraint('check_connector_kind', 'connectors', type_='check')
    op.create_check_constraint(
        'check_connector_kind',
        'connectors',
        "kind IN ('in_app', 'email', 'webhook')",
    )
