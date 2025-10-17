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
    # Create logs table (partitioned by timestamp)
    op.execute("""
        CREATE TABLE logs (
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

    # Create indexes for logs table
    op.create_index('idx_logs_project_timestamp', 'logs', ['project_id', 'timestamp'], unique=False)
    op.create_index('idx_logs_level', 'logs', ['level'], unique=False)
    op.create_index('idx_logs_log_type', 'logs', ['log_type'], unique=False)
    op.create_index('idx_logs_importance', 'logs', ['importance'], unique=False)
    op.create_index('idx_logs_error_fingerprint', 'logs', ['error_fingerprint'], unique=False, postgresql_where=sa.text("error_fingerprint IS NOT NULL"))
    op.create_index('idx_logs_attributes_gin', 'logs', ['attributes'], unique=False, postgresql_using='gin')

    # Create error_groups table
    op.create_table(
        'error_groups',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('error_fingerprint', sa.CHAR(length=64), nullable=False),
        sa.Column('error_type', sa.String(length=255), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('first_seen', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('occurrence_count', sa.BigInteger(), server_default=sa.text('1'), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=True),
        sa.Column('stack_frames', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'error_fingerprint', name='uq_error_groups_project_fingerprint')
    )
    op.create_index('idx_error_groups_project_last_seen', 'error_groups', ['project_id', 'last_seen'], unique=False)
    op.create_index('idx_error_groups_project_count', 'error_groups', ['project_id', 'occurrence_count'], unique=False)

    # Create ingestion_metrics table
    op.create_table(
        'ingestion_metrics',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('total_logs', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('total_errors', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('total_criticals', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('avg_processing_time_ms', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'metric_date', name='uq_metrics_project_date')
    )
    op.create_index('idx_ingestion_metrics_project_date', 'ingestion_metrics', ['project_id', 'metric_date'], unique=False)


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
