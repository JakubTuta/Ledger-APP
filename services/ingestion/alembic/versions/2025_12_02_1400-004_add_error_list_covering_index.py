"""add covering index for error list queries

Revision ID: 004
Revises: 003
Create Date: 2025-12-02 14:00:00.000000

"""
from alembic import op

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_error_list_covering
        ON logs (project_id, timestamp DESC, level, log_type, error_type, message, error_fingerprint, sdk_version, platform)
        WHERE level IN ('error', 'critical')
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_logs_error_list_covering")
