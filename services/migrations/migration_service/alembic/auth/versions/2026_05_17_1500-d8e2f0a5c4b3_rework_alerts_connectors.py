"""rework alerts: account-wide connectors, rule-connector links, alert events

Revision ID: d8e2f0a5c4b3
Revises: c7d1e9a4b3f2
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = 'd8e2f0a5c4b3'
down_revision = 'c7d1e9a4b3f2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('alert_channels')

    op.add_column(
        'alert_rules',
        sa.Column('unit', sa.VARCHAR(8), nullable=False, server_default='count'),
    )
    op.drop_constraint('check_alert_window_minutes', 'alert_rules', type_='check')
    op.create_check_constraint(
        'check_alert_unit',
        'alert_rules',
        "unit IN ('ms', 's', '%', 'count')",
    )
    op.drop_column('alert_rules', 'window_minutes')
    op.drop_column('alert_rules', 'cooldown_minutes')

    op.create_table(
        'connectors',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('account_id', sa.BigInteger(), nullable=False),
        sa.Column('kind', sa.VARCHAR(20), nullable=False),
        sa.Column('name', sa.VARCHAR(255), nullable=False),
        sa.Column('config', JSONB(), nullable=False, server_default='{}'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.CheckConstraint("kind IN ('in_app', 'email', 'webhook')", name='check_connector_kind'),
    )
    op.create_index('idx_connectors_account_id', 'connectors', ['account_id'])

    op.create_table(
        'alert_rule_connectors',
        sa.Column('rule_id', sa.BigInteger(), nullable=False),
        sa.Column('connector_id', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('rule_id', 'connector_id'),
        sa.ForeignKeyConstraint(['rule_id'], ['alert_rules.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['connector_id'], ['connectors.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_alert_rule_connectors_connector', 'alert_rule_connectors', ['connector_id'])

    op.create_table(
        'alert_events',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('rule_id', sa.BigInteger(), nullable=True),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('rule_name', sa.VARCHAR(255), nullable=False),
        sa.Column('metric_type', sa.VARCHAR(50), nullable=False),
        sa.Column('comparator', sa.VARCHAR(4), nullable=False),
        sa.Column('threshold', sa.Float(), nullable=False),
        sa.Column('unit', sa.VARCHAR(8), nullable=False, server_default='count'),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('severity', sa.VARCHAR(20), nullable=False, server_default='warning'),
        sa.Column('state', sa.VARCHAR(10), nullable=False),
        sa.Column('connectors_sent', JSONB(), nullable=False, server_default='[]'),
        sa.Column('fired_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['rule_id'], ['alert_rules.id'], ondelete='SET NULL'),
        sa.CheckConstraint("state IN ('firing', 'resolved')", name='check_alert_event_state'),
    )
    op.create_index('idx_alert_events_project_fired', 'alert_events', ['project_id', 'fired_at'])
    op.create_index('idx_alert_events_rule_id', 'alert_events', ['rule_id'])


def downgrade() -> None:
    op.drop_table('alert_events')
    op.drop_table('alert_rule_connectors')
    op.drop_table('connectors')

    op.add_column(
        'alert_rules',
        sa.Column('window_minutes', sa.Integer(), nullable=False, server_default='5'),
    )
    op.add_column(
        'alert_rules',
        sa.Column('cooldown_minutes', sa.Integer(), nullable=False, server_default='60'),
    )
    op.drop_constraint('check_alert_unit', 'alert_rules', type_='check')
    op.create_check_constraint(
        'check_alert_window_minutes',
        'alert_rules',
        "window_minutes >= 1",
    )
    op.drop_column('alert_rules', 'unit')

    op.create_table(
        'alert_channels',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('rule_id', sa.BigInteger(), nullable=False),
        sa.Column('kind', sa.VARCHAR(20), nullable=False),
        sa.Column('config', JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['rule_id'], ['alert_rules.id'], ondelete='CASCADE'),
        sa.CheckConstraint("kind IN ('in_app', 'email', 'webhook')", name='check_alert_channel_kind'),
    )
    op.create_index('idx_alert_channels_rule_id', 'alert_channels', ['rule_id'])
