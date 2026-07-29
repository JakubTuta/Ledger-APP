"""add BRIN time indexes and merge the two partial HTTP indexes on logs

Revision ID: 016
Revises: 015
Create Date: 2026-07-29 14:00:00.000000

Two problems this fixes.

1. Nothing indexed `logs.timestamp` on its own. Every index on the table is
   project_id-leading, so for the analytics jobs that scan a time window across
   all projects:

     log_metrics (every 10 min)      WHERE timestamp >= :since
     aggregated_metrics (hourly)     WHERE timestamp >= :start AND < :end  (x3)
     bottleneck_metrics (hourly)     WHERE timestamp >= :start AND < :end

   the planner's best option was a full index-only scan of
   idx_logs_project_timestamp, using `timestamp` as a non-boundary qual - it
   walks every entry in that partition's index and filters. Cheaper than a heap
   seq scan, but still proportional to the whole partition rather than to the
   window. A BRIN on timestamp turns it into a block-range lookup: rows arrive
   in near-timestamp order, so the summaries stay tight. Same story for
   metric_points.ts, which usage_stats and the 1h rollup scan the same way.

   Measured on 3M logs / 60 days / 12 projects: the log_metrics 10-minute pass
   goes 83.8ms -> 34.7ms (2.4x), with the BRIN scan touching 6 index buffers.

   BRIN (rather than btree) specifically because `logs` is the ingestion hot
   path - a btree on timestamp would be a second full-size index to maintain on
   every COPY.

2. idx_logs_project_status_code (project_id, status_code, timestamp DESC) and
   idx_logs_project_http_timestamp (project_id, timestamp DESC) were two
   partial indexes over the same WHERE status_code IS NOT NULL subset, i.e. two
   write costs. One index ordered (project_id, timestamp DESC, status_code)
   serves every reader at least as well:

     - query_logs()/_apply_log_filters status_class: ORDER BY timestamp DESC,
       id DESC with a LIMIT, so a timestamp-ordered index returns rows in order
       and stops early, where the status_code-leading one needed a bitmap scan
       plus a sort.
     - get_log_facets() status_class: index-only scan over the project's HTTP
       rows in the window.
     - alert evaluator error_rate_4xx/5xx: project + 10-minute window, with
       status_code available in the index for the FILTER aggregates.
"""

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS brin_logs_timestamp ON logs USING BRIN (timestamp)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS brin_metric_points_ts ON metric_points USING BRIN (ts)"
    )

    op.execute("DROP INDEX IF EXISTS idx_logs_project_status_code")
    op.execute("DROP INDEX IF EXISTS idx_logs_project_http_timestamp")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_project_http "
        "ON logs (project_id, timestamp DESC, status_code) "
        "WHERE status_code IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_logs_project_http")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_project_status_code "
        "ON logs (project_id, status_code, timestamp DESC) "
        "WHERE status_code IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_project_http_timestamp "
        "ON logs (project_id, timestamp DESC) "
        "WHERE status_code IS NOT NULL"
    )

    op.execute("DROP INDEX IF EXISTS brin_metric_points_ts")
    op.execute("DROP INDEX IF EXISTS brin_logs_timestamp")
