"""add aggregated_metrics table

Revision ID: 002
Revises: 001
Create Date: 2025-11-22 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE aggregated_metrics (
            id BIGSERIAL PRIMARY KEY,
            project_id BIGINT NOT NULL,
            date VARCHAR(8) NOT NULL,
            hour SMALLINT NOT NULL,
            metric_type VARCHAR(20) NOT NULL,
            endpoint_method VARCHAR(10),
            endpoint_path VARCHAR(500),
            log_count INTEGER DEFAULT 0 NOT NULL,
            error_count INTEGER DEFAULT 0 NOT NULL,
            avg_duration_ms FLOAT,
            min_duration_ms INTEGER,
            max_duration_ms INTEGER,
            p95_duration_ms INTEGER,
            p99_duration_ms INTEGER,
            extra_metadata JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            CONSTRAINT check_metric_type CHECK (metric_type IN ('exception', 'endpoint')),
            CONSTRAINT check_hour_range CHECK (hour >= 0 AND hour <= 23)
        );
    """)

    op.create_index(
        'idx_aggregated_metrics_lookup',
        'aggregated_metrics',
        ['project_id', 'date', 'metric_type'],
        unique=False
    )

    op.create_index(
        'idx_aggregated_metrics_endpoint',
        'aggregated_metrics',
        ['project_id', 'date', 'endpoint_path'],
        unique=False,
        postgresql_where=sa.text("metric_type = 'endpoint'")
    )

    op.execute("""
        CREATE UNIQUE INDEX uq_aggregated_metrics
        ON aggregated_metrics(project_id, date, hour, metric_type,
            COALESCE(endpoint_method, ''), COALESCE(endpoint_path, ''));
    """)


def downgrade() -> None:
    op.drop_index('uq_aggregated_metrics', table_name='aggregated_metrics')
    op.drop_index('idx_aggregated_metrics_endpoint', table_name='aggregated_metrics')
    op.drop_index('idx_aggregated_metrics_lookup', table_name='aggregated_metrics')
    op.drop_table('aggregated_metrics')
