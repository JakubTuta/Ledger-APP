"""add trigram indexes for fast log search

Revision ID: 012
Revises: 011
Create Date: 2026-07-08 10:00:00.000000

"""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_logs_message_trgm
        ON logs USING gin (message gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_logs_error_message_trgm
        ON logs USING gin (error_message gin_trgm_ops)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_logs_error_message_trgm")
    op.execute("DROP INDEX IF EXISTS ix_logs_message_trgm")
    # pg_trgm extension intentionally left in place; other objects may depend on it.
