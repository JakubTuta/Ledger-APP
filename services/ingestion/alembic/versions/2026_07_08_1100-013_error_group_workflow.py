"""add resolved_at and resolved_in_release to error_groups for workflow tracking

Revision ID: 013
Revises: 012
Create Date: 2026-07-08 11:00:00.000000

"""
from alembic import op

revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE error_groups ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ")
    op.execute(
        "ALTER TABLE error_groups ADD COLUMN IF NOT EXISTS resolved_in_release VARCHAR(100)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE error_groups DROP COLUMN IF EXISTS resolved_in_release")
    op.execute("ALTER TABLE error_groups DROP COLUMN IF EXISTS resolved_at")
