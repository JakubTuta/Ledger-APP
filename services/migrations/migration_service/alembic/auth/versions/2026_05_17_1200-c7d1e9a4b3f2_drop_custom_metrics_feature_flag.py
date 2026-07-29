"""drop custom_metrics feature flag

Revision ID: c7d1e9a4b3f2
Revises: b5c9d3e7f2a1
Branch Labels: None
Depends On: None

"""
from alembic import op

revision = 'c7d1e9a4b3f2'
down_revision = 'b5c9d3e7f2a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM feature_flags WHERE key = 'custom_metrics'")
    op.drop_constraint('check_feature_flag_key', 'feature_flags', type_='check')
    op.create_check_constraint(
        'check_feature_flag_key',
        'feature_flags',
        "key IN ('tracing', 'alert_rules')",
    )


def downgrade() -> None:
    op.drop_constraint('check_feature_flag_key', 'feature_flags', type_='check')
    op.create_check_constraint(
        'check_feature_flag_key',
        'feature_flags',
        "key IN ('tracing', 'custom_metrics', 'alert_rules')",
    )
