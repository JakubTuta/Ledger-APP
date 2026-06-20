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

    op.execute("ALTER TABLE aggregated_metrics ADD COLUMN IF NOT EXISTS log_level VARCHAR(20)")
    op.execute("ALTER TABLE aggregated_metrics ADD COLUMN IF NOT EXISTS log_type VARCHAR(30)")

    op.execute("""
        DO $$ BEGIN
            ALTER TABLE aggregated_metrics ADD CONSTRAINT check_metric_type
                CHECK (metric_type IN ('exception', 'endpoint', 'log_volume'));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE aggregated_metrics ADD CONSTRAINT check_log_level
                CHECK (log_level IS NULL OR log_level IN ('debug', 'info', 'warning', 'error', 'critical'));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE aggregated_metrics ADD CONSTRAINT check_log_type
                CHECK (log_type IS NULL OR log_type IN ('console', 'logger', 'exception', 'network', 'database', 'endpoint', 'custom'));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_aggregated_metrics
        ON aggregated_metrics(
            project_id, date, hour, metric_type,
            COALESCE(endpoint_method, ''), COALESCE(endpoint_path, ''),
            COALESCE(log_level, ''), COALESCE(log_type, '')
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS log_volume_5m (
            project_id  BIGINT NOT NULL,
            level       VARCHAR(20) NOT NULL,
            bucket      TIMESTAMPTZ NOT NULL,
            count       BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (project_id, level, bucket)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_lv5m_project_bucket ON log_volume_5m (project_id, bucket DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS log_volume_1h (
            project_id  BIGINT NOT NULL,
            level       VARCHAR(20) NOT NULL,
            bucket      TIMESTAMPTZ NOT NULL,
            count       BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (project_id, level, bucket)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_lv1h_project_bucket ON log_volume_1h (project_id, bucket DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS log_volume_1d (
            project_id  BIGINT NOT NULL,
            level       VARCHAR(20) NOT NULL,
            bucket      DATE NOT NULL,
            count       BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (project_id, level, bucket)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_lv1d_project_bucket ON log_volume_1d (project_id, bucket DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS error_rate_5m (
            project_id  BIGINT NOT NULL,
            bucket      TIMESTAMPTZ NOT NULL,
            errors      BIGINT NOT NULL DEFAULT 0,
            total       BIGINT NOT NULL DEFAULT 0,
            ratio       DOUBLE PRECISION NOT NULL DEFAULT 0,
            PRIMARY KEY (project_id, bucket)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_er5m_project_bucket ON error_rate_5m (project_id, bucket DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS endpoint_latency_1h (
            project_id  BIGINT NOT NULL,
            route       TEXT NOT NULL,
            bucket      TIMESTAMPTZ NOT NULL,
            count       BIGINT NOT NULL DEFAULT 0,
            p50_ms      DOUBLE PRECISION,
            p95_ms      DOUBLE PRECISION,
            p99_ms      DOUBLE PRECISION,
            PRIMARY KEY (project_id, route, bucket)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_el1h_project_bucket ON endpoint_latency_1h (project_id, bucket DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS rollup_job_state (
            job_name    TEXT NOT NULL PRIMARY KEY,
            last_bucket TIMESTAMPTZ NOT NULL
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
