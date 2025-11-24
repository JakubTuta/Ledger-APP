"""add log_volume metrics support to aggregated_metrics

Revision ID: 003
Revises: 002
Create Date: 2025-11-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_aggregated_metrics")

    op.execute("ALTER TABLE aggregated_metrics DROP CONSTRAINT IF EXISTS check_metric_type")

    op.add_column('aggregated_metrics', sa.Column('log_level', sa.String(20), nullable=True))
    op.add_column('aggregated_metrics', sa.Column('log_type', sa.String(30), nullable=True))

    op.execute("""
        ALTER TABLE aggregated_metrics ADD CONSTRAINT check_metric_type
        CHECK (metric_type IN ('exception', 'endpoint', 'log_volume'))
    """)

    op.execute("""
        ALTER TABLE aggregated_metrics ADD CONSTRAINT check_log_level
        CHECK (log_level IS NULL OR log_level IN ('debug', 'info', 'warning', 'error', 'critical'))
    """)

    op.execute("""
        ALTER TABLE aggregated_metrics ADD CONSTRAINT check_log_type
        CHECK (log_type IS NULL OR log_type IN ('console', 'logger', 'exception', 'network', 'database', 'endpoint', 'custom'))
    """)

    op.execute("""
        CREATE UNIQUE INDEX uq_aggregated_metrics
        ON aggregated_metrics(
            project_id,
            date,
            hour,
            metric_type,
            COALESCE(endpoint_method, ''),
            COALESCE(endpoint_path, ''),
            COALESCE(log_level, ''),
            COALESCE(log_type, '')
        )
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_aggregated_metrics")

    op.execute("ALTER TABLE aggregated_metrics DROP CONSTRAINT IF EXISTS check_log_level")
    op.execute("ALTER TABLE aggregated_metrics DROP CONSTRAINT IF EXISTS check_log_type")
    op.execute("ALTER TABLE aggregated_metrics DROP CONSTRAINT IF EXISTS check_metric_type")

    op.drop_column('aggregated_metrics', 'log_type')
    op.drop_column('aggregated_metrics', 'log_level')

    op.execute("""
        ALTER TABLE aggregated_metrics ADD CONSTRAINT check_metric_type
        CHECK (metric_type IN ('exception', 'endpoint'))
    """)

    op.execute("""
        CREATE UNIQUE INDEX uq_aggregated_metrics
        ON aggregated_metrics(
            project_id,
            date,
            hour,
            metric_type,
            COALESCE(endpoint_method, ''),
            COALESCE(endpoint_path, '')
        )
    """)
