"""promote http fields (method, path, status_code, duration_ms) to first-class columns on logs

Revision ID: 008
Revises: 007
Create Date: 2026-05-14 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE logs
            ADD COLUMN IF NOT EXISTS method VARCHAR(8),
            ADD COLUMN IF NOT EXISTS path VARCHAR(2048),
            ADD COLUMN IF NOT EXISTS status_code SMALLINT,
            ADD COLUMN IF NOT EXISTS duration_ms INTEGER
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_project_status_code
            ON logs (project_id, status_code, timestamp DESC)
            WHERE status_code IS NOT NULL
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_project_http_timestamp
            ON logs (project_id, timestamp DESC)
            WHERE status_code IS NOT NULL
    """)

    op.execute("""
        UPDATE logs
        SET
            method      = attributes->'endpoint'->>'method',
            path        = attributes->'endpoint'->>'path',
            status_code = (attributes->'endpoint'->>'status_code')::smallint,
            duration_ms = ROUND((attributes->'endpoint'->>'duration_ms')::numeric)::integer
        WHERE log_type IN ('endpoint', 'network')
          AND attributes ? 'endpoint'
          AND attributes->'endpoint' ? 'status_code'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_logs_project_http_timestamp")
    op.execute("DROP INDEX IF EXISTS idx_logs_project_status_code")
    op.execute("""
        ALTER TABLE logs
            DROP COLUMN IF EXISTS method,
            DROP COLUMN IF EXISTS path,
            DROP COLUMN IF EXISTS status_code,
            DROP COLUMN IF EXISTS duration_ms
    """)
