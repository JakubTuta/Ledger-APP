"""add client_channel to the country-breakdown index on logs

Revision ID: 020
Revises: 019
Create Date: 2026-08-05 10:00:00.000000

Revision 018 gave get_country_breakdown() an index-only scan over
(project_id, timestamp DESC, client_country). Panel-level traffic filters
now put a `client_channel IN (...)` predicate on that same query, and
client_channel was in no index - so the planner dropped the index-only scan
and fell back to a bitmap heap scan, fetching every candidate row from the
heap just to read one column.

Measured on 3M logs / 60 days / 12 projects, 30-day window, project 1
(warm cache, median of 4 runs after a discarded first run):

    filter                    before      after     buffers before -> after
    bot only (5% of traffic)  96.3 ms    3.8 ms     37,950 -> 489
    people (75%)             103.2 ms   12.2 ms
    no channel filter          9.7 ms   10.1 ms     (control, unchanged)

Adding client_channel as a fourth key column restores the index-only scan
(Heap Fetches: 0) for the filtered case. It is a key column rather than
INCLUDE because both build to the same size here (90 MB vs 90 MB across all
partitions), and a key column can additionally serve as a non-boundary qual.

Write cost: the index grows 70 MB -> 90 MB (+29%) on this dataset. It stays
partial on `client_country IS NOT NULL`, so only rows that actually carry
caller info are indexed - no new index is added to the ingestion hot path,
the existing one just gets one more column.

Not done here, and why: the logs-panel list query
(idx_logs_project_timestamp) shows no benefit - its LIMIT 26 terminates
early, so a bot-only first page already runs in 0.75 ms and a deep page
(offset 200) in 4.7 ms. Widening the largest index on the hottest table
buys nothing measurable. get_error_list() is likewise unchanged (~46 ms
either way): it heap-fetches for message/error_type regardless of the
channel predicate.
"""

from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_logs_project_country")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_project_country "
        "ON logs (project_id, timestamp DESC, client_country, client_channel) "
        "WHERE client_country IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_logs_project_country")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_project_country "
        "ON logs (project_id, timestamp DESC, client_country) "
        "WHERE client_country IS NOT NULL"
    )
