"""add spans, span_latency_1h, custom_metrics tables and trace columns on logs

Revision ID: 007
Revises: 006
Create Date: 2026-05-14 12:00:00.000000

"""
from alembic import op

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS spans (
            span_id           CHAR(16) NOT NULL,
            trace_id          CHAR(32) NOT NULL,
            parent_span_id    CHAR(16),
            project_id        BIGINT NOT NULL,
            service_name      TEXT NOT NULL,
            name              TEXT NOT NULL,
            kind              SMALLINT NOT NULL DEFAULT 0,
            start_time        TIMESTAMPTZ NOT NULL,
            duration_ns       BIGINT NOT NULL DEFAULT 0,
            status_code       SMALLINT NOT NULL DEFAULT 0,
            status_message    TEXT,
            attributes        JSONB NOT NULL DEFAULT '{}'::jsonb,
            events            JSONB,
            error_fingerprint CHAR(64),
            PRIMARY KEY (span_id, start_time)
        ) PARTITION BY RANGE (start_time)
    """)

    op.execute("CREATE INDEX IF NOT EXISTS brin_spans_project_time ON spans USING BRIN (project_id, start_time)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans (trace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_spans_op ON spans (project_id, service_name, name, start_time DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_spans_errors ON spans (project_id, start_time DESC) WHERE status_code = 2")

    op.execute("""
        CREATE TABLE IF NOT EXISTS span_latency_1h (
            project_id   BIGINT NOT NULL,
            service_name TEXT NOT NULL,
            name         TEXT NOT NULL,
            bucket       TIMESTAMPTZ NOT NULL,
            calls        BIGINT NOT NULL DEFAULT 0,
            p50_ns       BIGINT,
            p95_ns       BIGINT,
            p99_ns       BIGINT,
            errors       BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (project_id, service_name, name, bucket)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_sl1h_project_bucket ON span_latency_1h (project_id, bucket DESC)")

    op.execute("""
        ALTER TABLE logs
            ADD COLUMN IF NOT EXISTS trace_id CHAR(32),
            ADD COLUMN IF NOT EXISTS span_id CHAR(16)
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_log_trace ON logs (trace_id) WHERE trace_id IS NOT NULL")

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


def downgrade() -> None:
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

    op.execute("DROP INDEX IF EXISTS idx_log_trace")
    op.execute("ALTER TABLE logs DROP COLUMN IF EXISTS span_id")
    op.execute("ALTER TABLE logs DROP COLUMN IF EXISTS trace_id")

    op.execute("DROP INDEX IF EXISTS idx_sl1h_project_bucket")
    op.execute("DROP TABLE IF EXISTS span_latency_1h")

    op.execute("DROP INDEX IF EXISTS idx_spans_errors")
    op.execute("DROP INDEX IF EXISTS idx_spans_op")
    op.execute("DROP INDEX IF EXISTS idx_spans_trace")
    op.execute("DROP INDEX IF EXISTS brin_spans_project_time")
    op.execute("DROP TABLE IF EXISTS spans")
