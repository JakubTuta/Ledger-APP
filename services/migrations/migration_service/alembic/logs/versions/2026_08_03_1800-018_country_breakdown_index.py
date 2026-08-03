"""add partial index on logs.client_country for the country-breakdown query

Revision ID: 018
Revises: 017
Create Date: 2026-08-03 18:00:00.000000

`get_country_breakdown()` filters `project_id`, a timestamp window, and
`client_country IS NOT NULL`. Without an index on that last predicate,
Postgres has no way to know client_country is sparse - it range-scans
`idx_logs_project_timestamp` over every log row in the window (every log
type, not just endpoint logs) and filters client_country row by row after
the heap fetch. At moderate volume this scan alone exceeds the gateway's
10s gRPC deadline, so the endpoint times out (DEADLINE_EXCEEDED) instead of
returning an empty result quickly.

client_country is not restricted to log_type='endpoint': caller info is
threaded into log_request/log_exception too when captured during a request
(see Ledger-SDK core/base_middleware.py), so this can't reuse the existing
idx_logs_project_http partial index (`WHERE status_code IS NOT NULL`) -
it needs its own predicate on client_country directly.
"""

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_project_country "
        "ON logs (project_id, timestamp DESC, client_country) "
        "WHERE client_country IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_logs_project_country")
