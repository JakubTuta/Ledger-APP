"""drop custom_metrics tables and metric_series_count

Revision ID: 009
Revises: 008
Create Date: 2026-05-17 12:00:00.000000

"""
from alembic import op

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cm1d_lookup")
    op.execute("DROP TABLE IF EXISTS custom_metrics_1d")

    op.execute("DROP INDEX IF EXISTS idx_cm1h_lookup")
    op.execute("DROP TABLE IF EXISTS custom_metrics_1h")

    op.execute("DROP INDEX IF EXISTS idx_cm5m_lookup")
    op.execute("DROP TABLE IF EXISTS custom_metrics_5m")

    op.execute("DROP TABLE IF EXISTS metric_series_count")

    op.execute("DROP INDEX IF EXISTS idx_cm_tags")
    op.execute("DROP INDEX IF EXISTS idx_cm_lookup")
    op.execute("DROP TABLE IF EXISTS custom_metrics")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS custom_metrics (
            project_id  BIGINT NOT NULL,
            name        TEXT NOT NULL,
            tags        JSONB NOT NULL DEFAULT '{}'::jsonb,
            ts          TIMESTAMPTZ NOT NULL,
            type        SMALLINT NOT NULL,
            count       BIGINT NOT NULL DEFAULT 0,
            sum         DOUBLE PRECISION NOT NULL DEFAULT 0,
            min_v       DOUBLE PRECISION,
            max_v       DOUBLE PRECISION,
            buckets     JSONB,
            PRIMARY KEY (project_id, name, tags, ts)
        ) PARTITION BY RANGE (ts)
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cm_lookup ON custom_metrics (project_id, name, ts DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cm_tags ON custom_metrics USING GIN (tags)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS metric_series_count (
            project_id   BIGINT NOT NULL PRIMARY KEY,
            series_count BIGINT NOT NULL DEFAULT 0,
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS custom_metrics_5m (
            project_id  BIGINT NOT NULL,
            name        TEXT NOT NULL,
            tags        JSONB NOT NULL DEFAULT '{}'::jsonb,
            bucket      TIMESTAMPTZ NOT NULL,
            type        SMALLINT NOT NULL,
            count       BIGINT NOT NULL DEFAULT 0,
            sum         DOUBLE PRECISION NOT NULL DEFAULT 0,
            min_v       DOUBLE PRECISION,
            max_v       DOUBLE PRECISION,
            PRIMARY KEY (project_id, name, tags, bucket)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cm5m_lookup ON custom_metrics_5m (project_id, name, bucket DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS custom_metrics_1h (
            project_id  BIGINT NOT NULL,
            name        TEXT NOT NULL,
            tags        JSONB NOT NULL DEFAULT '{}'::jsonb,
            bucket      TIMESTAMPTZ NOT NULL,
            type        SMALLINT NOT NULL,
            count       BIGINT NOT NULL DEFAULT 0,
            sum         DOUBLE PRECISION NOT NULL DEFAULT 0,
            min_v       DOUBLE PRECISION,
            max_v       DOUBLE PRECISION,
            PRIMARY KEY (project_id, name, tags, bucket)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cm1h_lookup ON custom_metrics_1h (project_id, name, bucket DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS custom_metrics_1d (
            project_id  BIGINT NOT NULL,
            name        TEXT NOT NULL,
            tags        JSONB NOT NULL DEFAULT '{}'::jsonb,
            bucket      DATE NOT NULL,
            type        SMALLINT NOT NULL,
            count       BIGINT NOT NULL DEFAULT 0,
            sum         DOUBLE PRECISION NOT NULL DEFAULT 0,
            min_v       DOUBLE PRECISION,
            max_v       DOUBLE PRECISION,
            PRIMARY KEY (project_id, name, tags, bucket)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cm1d_lookup ON custom_metrics_1d (project_id, name, bucket DESC)")
