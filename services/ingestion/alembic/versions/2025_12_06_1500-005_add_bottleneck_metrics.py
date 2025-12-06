"""add bottleneck_metrics table

Revision ID: 005
Revises: 004
Create Date: 2025-12-06 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE bottleneck_metrics (
            id BIGSERIAL PRIMARY KEY,
            project_id BIGINT NOT NULL,
            date VARCHAR(8) NOT NULL,
            hour SMALLINT NOT NULL,
            route VARCHAR(500) NOT NULL,
            log_count INTEGER DEFAULT 0 NOT NULL,
            min_duration_ms INTEGER DEFAULT 0,
            max_duration_ms INTEGER DEFAULT 0,
            avg_duration_ms FLOAT DEFAULT 0,
            median_duration_ms INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            CONSTRAINT check_bottleneck_hour_range CHECK (hour >= 0 AND hour <= 23)
        );
    """)

    op.create_index(
        'idx_bottleneck_metrics_lookup',
        'bottleneck_metrics',
        ['project_id', 'date', 'hour'],
        unique=False
    )

    op.create_index(
        'idx_bottleneck_metrics_route',
        'bottleneck_metrics',
        ['project_id', 'date', 'route'],
        unique=False
    )

    op.execute("""
        CREATE UNIQUE INDEX uq_bottleneck_metrics
        ON bottleneck_metrics(project_id, date, hour, route);
    """)


def downgrade() -> None:
    op.drop_index('uq_bottleneck_metrics', table_name='bottleneck_metrics')
    op.drop_index('idx_bottleneck_metrics_route', table_name='bottleneck_metrics')
    op.drop_index('idx_bottleneck_metrics_lookup', table_name='bottleneck_metrics')
    op.drop_table('bottleneck_metrics')
