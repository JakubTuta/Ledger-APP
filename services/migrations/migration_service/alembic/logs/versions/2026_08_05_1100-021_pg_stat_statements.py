"""enable pg_stat_statements for query-level profiling

Revision ID: 021
Revises: 020
Create Date: 2026-08-05 11:00:00.000000

"""

from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Requires shared_preload_libraries=pg_stat_statements on the server (set via
    # docker-compose's postgres `command:` block) - CREATE EXTENSION alone will
    # fail with "pg_stat_statements must be loaded via shared_preload_libraries"
    # if that flag isn't already active, since it needs a restart to take effect.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_stat_statements")
