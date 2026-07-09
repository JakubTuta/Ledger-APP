"""add log_id column and dedup index to logs

Revision ID: 010
Revises: 009
Create Date: 2026-07-07 10:00:00.000000

"""
from alembic import op

revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS log_id VARCHAR(64)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_dedup "
        "ON logs (project_id, log_id, timestamp) WHERE log_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_logs_dedup")
    op.execute("ALTER TABLE logs DROP COLUMN IF EXISTS log_id")
