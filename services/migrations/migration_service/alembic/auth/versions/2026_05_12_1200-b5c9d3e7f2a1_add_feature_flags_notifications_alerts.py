"""add_feature_flags_notifications_alerts

Revision ID: b5c9d3e7f2a1
Revises: a1b2c3d4e5f6
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = 'b5c9d3e7f2a1'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'feature_flags',
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('key', sa.VARCHAR(50), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('project_id', 'key'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.CheckConstraint("key IN ('tracing', 'custom_metrics', 'alert_rules')", name='check_feature_flag_key'),
    )
    op.create_index('idx_feature_flags_project_id', 'feature_flags', ['project_id'])

    op.create_table(
        'notifications',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('kind', sa.VARCHAR(30), nullable=False),
        sa.Column('severity', sa.VARCHAR(20), nullable=False, server_default='info'),
        sa.Column('payload', JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.CheckConstraint("kind IN ('error', 'alert_firing', 'alert_resolved', 'quota_warning')", name='check_notification_kind'),
        sa.CheckConstraint("severity IN ('critical', 'warning', 'info')", name='check_notification_severity'),
    )
    op.create_index('idx_notifications_user_unread', 'notifications', ['user_id', 'read_at'])
    op.create_index('idx_notifications_project_id', 'notifications', ['project_id'])
    op.create_index('idx_notifications_expires_at', 'notifications', ['expires_at'])

    op.create_table(
        'alert_rules',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.VARCHAR(255), nullable=False),
        sa.Column('metric_type', sa.VARCHAR(50), nullable=False),
        sa.Column('comparator', sa.VARCHAR(4), nullable=False),
        sa.Column('threshold', sa.Float(), nullable=False),
        sa.Column('window_minutes', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('severity', sa.VARCHAR(20), nullable=False, server_default='warning'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('cooldown_minutes', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('state', sa.VARCHAR(10), nullable=False, server_default='ok'),
        sa.Column('last_fired_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fired_value', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.CheckConstraint("comparator IN ('>', '<', '>=', '<=')", name='check_alert_comparator'),
        sa.CheckConstraint("severity IN ('critical', 'warning', 'info')", name='check_alert_severity'),
        sa.CheckConstraint("state IN ('ok', 'firing')", name='check_alert_state'),
        sa.CheckConstraint("window_minutes >= 1", name='check_alert_window_minutes'),
    )
    op.create_index('idx_alert_rules_project_id', 'alert_rules', ['project_id'])

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

    op.create_table(
        'notification_preferences',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('rule_id', sa.BigInteger(), nullable=True),
        sa.Column('severity', sa.VARCHAR(20), nullable=True),
        sa.Column('muted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('channel_overrides', JSONB(), nullable=False, server_default='{}'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['rule_id'], ['alert_rules.id'], ondelete='CASCADE'),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('critical', 'warning', 'info')",
            name='check_notif_pref_severity',
        ),
        sa.UniqueConstraint('user_id', 'project_id', 'rule_id', 'severity', name='uq_notif_prefs'),
    )
    op.create_index('idx_notif_prefs_user_project', 'notification_preferences', ['user_id', 'project_id'])


def downgrade() -> None:
    op.drop_table('notification_preferences')
    op.drop_table('alert_channels')
    op.drop_table('alert_rules')
    op.drop_table('notifications')
    op.drop_table('feature_flags')
