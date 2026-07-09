"""fix check_log_type to allow 'endpoint' (missing since initial migration)

Revision ID: 011
Revises: 010
Create Date: 2026-07-07 12:00:00.000000

"""
from alembic import op

revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE logs DROP CONSTRAINT IF EXISTS check_log_type")
    op.execute(
        "ALTER TABLE logs ADD CONSTRAINT check_log_type "
        "CHECK (log_type IN ('console', 'logger', 'exception', 'network', "
        "'database', 'endpoint', 'custom'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE logs DROP CONSTRAINT IF EXISTS check_log_type")
    op.execute(
        "ALTER TABLE logs ADD CONSTRAINT check_log_type "
        "CHECK (log_type IN ('console', 'logger', 'exception', 'network', "
        "'database', 'custom'))"
    )
