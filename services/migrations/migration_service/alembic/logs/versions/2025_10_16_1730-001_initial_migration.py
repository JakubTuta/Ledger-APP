"""initial migration

Revision ID: 001
Revises:
Create Date: 2025-10-16 17:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id BIGSERIAL NOT NULL,
            project_id BIGINT NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            level VARCHAR(20) NOT NULL,
            log_type VARCHAR(30) NOT NULL,
            importance VARCHAR(20) DEFAULT 'standard' NOT NULL,
            environment VARCHAR(20),
            release VARCHAR(100),
            message TEXT,
            error_type VARCHAR(255),
            error_message TEXT,
            stack_trace TEXT,
            attributes JSONB,
            sdk_version VARCHAR(20),
            platform VARCHAR(50),
            platform_version VARCHAR(50),
            processing_time_ms SMALLINT,
            error_fingerprint CHAR(64),
            PRIMARY KEY (id, timestamp),
            CONSTRAINT check_level CHECK (level IN ('debug', 'info', 'warning', 'error', 'critical')),
            CONSTRAINT check_log_type CHECK (log_type IN ('console', 'logger', 'exception', 'network', 'database', 'custom')),
            CONSTRAINT check_importance CHECK (importance IN ('critical', 'high', 'standard', 'low'))
        ) PARTITION BY RANGE (timestamp);
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_logs_project_timestamp ON logs (project_id, timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON logs (level)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_logs_log_type ON logs (log_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_logs_importance ON logs (importance)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_logs_error_fingerprint ON logs (error_fingerprint) WHERE error_fingerprint IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_logs_attributes_gin ON logs USING gin (attributes)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS error_groups (
            id BIGSERIAL NOT NULL,
            project_id BIGINT NOT NULL,
            fingerprint CHAR(64) NOT NULL,
            error_type VARCHAR(255) NOT NULL,
            error_message TEXT,
            first_seen TIMESTAMPTZ NOT NULL,
            last_seen TIMESTAMPTZ NOT NULL,
            occurrence_count BIGINT DEFAULT 1 NOT NULL,
            status VARCHAR(20) DEFAULT 'unresolved' NOT NULL,
            assigned_to BIGINT,
            sample_log_id BIGINT,
            sample_stack_trace TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_error_groups_project_fingerprint UNIQUE (project_id, fingerprint),
            CONSTRAINT check_error_status CHECK (status IN ('unresolved', 'resolved', 'ignored', 'muted'))
        );
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_error_groups_fingerprint ON error_groups (project_id, fingerprint)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_error_groups_status ON error_groups (project_id, status, last_seen)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_error_groups_type ON error_groups (project_id, error_type, last_seen)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_metrics (
            id BIGSERIAL NOT NULL,
            project_id BIGINT NOT NULL,
            metric_date DATE NOT NULL,
            total_logs BIGINT DEFAULT 0 NOT NULL,
            total_errors BIGINT DEFAULT 0 NOT NULL,
            total_criticals BIGINT DEFAULT 0 NOT NULL,
            avg_processing_time_ms FLOAT,
            created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_metrics_project_date UNIQUE (project_id, metric_date)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_ingestion_metrics_project_date ON ingestion_metrics (project_id, metric_date)")


def downgrade() -> None:
    # Drop ingestion_metrics table
    op.drop_index('idx_ingestion_metrics_project_date', table_name='ingestion_metrics')
    op.drop_table('ingestion_metrics')

    # Drop error_groups table
    op.drop_index('idx_error_groups_project_count', table_name='error_groups')
    op.drop_index('idx_error_groups_project_last_seen', table_name='error_groups')
    op.drop_table('error_groups')

    # Drop logs table
    op.drop_index('idx_logs_attributes_gin', table_name='logs')
    op.drop_index('idx_logs_error_fingerprint', table_name='logs')
    op.drop_index('idx_logs_importance', table_name='logs')
    op.drop_index('idx_logs_log_type', table_name='logs')
    op.drop_index('idx_logs_level', table_name='logs')
    op.drop_index('idx_logs_project_timestamp', table_name='logs')
    op.execute('DROP TABLE logs')
