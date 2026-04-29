"""add endpoint duration expression index for analytics queries

Revision ID: 006
Revises: 005
Create Date: 2026-04-29 00:00:00.000000

"""
from alembic import op

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_endpoint_duration
        ON logs (
            project_id,
            timestamp DESC,
            ((attributes->'endpoint'->>'duration_ms')::float)
        )
        WHERE log_type = 'endpoint'
          AND attributes->'endpoint'->>'duration_ms' IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_logs_endpoint_duration")
