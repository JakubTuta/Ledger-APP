"""drop dead logs-db objects and rebuild the logs index set around real query shapes

Revision ID: 015
Revises: 014
Create Date: 2026-07-29 10:00:00.000000

Every index on `logs` is paid for on the ingestion hot path (COPY into a staging
table + INSERT ... SELECT, ~10k rows/s). This revision removes the indexes that
no query in the codebase can actually use and replaces the ones whose column
order or predicate did not match the queries that do exist.

Dropped and why:
  idx_logs_level / idx_logs_log_type / idx_logs_importance
      Single low-cardinality columns from revision 001. Every read path filters
      project_id first, so the planner never picks these.
  idx_logs_attributes_gin / idx_logs_attributes
      GIN over the whole `attributes` JSONB. No query uses a GIN-indexable
      operator (@>, ?, ?|) on it - analytics only dereferences with ->>, which
      GIN cannot serve. Most expensive index on the write path.
  ix_logs_message_trgm / ix_logs_error_message_trgm
      Both search paths (query_service log_query.search_logs and
      _apply_log_filters) OR the ILIKE across columns that have no trigram
      index (method/path/error_type), so the planner cannot use a trigram
      index for either - a BitmapOr needs every arm indexable. Two GIN indexes
      of pure write cost. Re-add together with trigram indexes on the other
      OR'd columns if unbounded full-text search over logs becomes a
      requirement.
  idx_logs_error_list_covering
      Nine columns including `message TEXT`; index tuples nearly as wide as the
      heap tuples. get_error_list()'s predicate is
      `level IN (...) OR status_code >= 400`, which always goes back to the heap,
      so the covering columns never pay off. idx_logs_project_level below serves
      the same arm at a fraction of the write cost.
  idx_logs_endpoint_duration
      Expression index on (attributes->'endpoint'->>'duration_ms')::float, added
      for the analytics endpoint aggregations. Those now read the promoted
      `duration_ms` column instead.
  idx_log_trace + logs.trace_id / logs.span_id
      Added in revision 007 and never wired up: the ingestion worker does not
      write either column and no service reads them.
  ingestion_metrics
      Created in revision 001, never read or written since.
  endpoint_latency_1h
      Created in revision 003, read by the analytics alert evaluator and pruned
      by the retention job, but never written by anything - so the evaluator's
      rollup lookup always missed and fell through to a PERCENTILE_CONT over raw
      logs, once per latency rule, every minute. The evaluator now reads the
      p95/p99 columns that aggregated_metrics already stores.

Also drops idx_error_groups_type (nothing queries error groups by error_type)
and idx_spans_errors / idx_spans_trace, superseded by the project-scoped
indexes added below.
"""

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_logs_level")
    op.execute("DROP INDEX IF EXISTS idx_logs_log_type")
    op.execute("DROP INDEX IF EXISTS idx_logs_importance")
    op.execute("DROP INDEX IF EXISTS idx_logs_attributes_gin")
    op.execute("DROP INDEX IF EXISTS idx_logs_attributes")
    op.execute("DROP INDEX IF EXISTS ix_logs_message_trgm")
    op.execute("DROP INDEX IF EXISTS ix_logs_error_message_trgm")
    op.execute("DROP INDEX IF EXISTS idx_logs_error_list_covering")
    op.execute("DROP INDEX IF EXISTS idx_logs_endpoint_duration")
    op.execute("DROP INDEX IF EXISTS idx_logs_dashboard")
    op.execute("DROP INDEX IF EXISTS idx_logs_endpoint_monitoring")
    op.execute("DROP INDEX IF EXISTS idx_log_trace")

    op.execute("ALTER TABLE logs DROP COLUMN IF EXISTS trace_id")
    op.execute("ALTER TABLE logs DROP COLUMN IF EXISTS span_id")

    # query_logs() orders by (timestamp DESC, id DESC) and keyset-paginates on
    # the same tuple, so `id` belongs in the index to keep it a plain ordered
    # scan with no sort node.
    op.execute("DROP INDEX IF EXISTS idx_logs_project_timestamp")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_project_timestamp "
        "ON logs (project_id, timestamp DESC, id DESC)"
    )

    # Revision 001 created this on (error_fingerprint) alone; the only reader
    # (get_error_occurrence_sparkline) filters project_id and a timestamp range
    # alongside it.
    op.execute("DROP INDEX IF EXISTS idx_logs_error_fingerprint")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_error_fingerprint "
        "ON logs (project_id, error_fingerprint, timestamp DESC) "
        "WHERE error_fingerprint IS NOT NULL"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_project_level "
        "ON logs (project_id, level, timestamp DESC) "
        "WHERE level IN ('error', 'critical')"
    )

    # list_traces() selects root spans only, ordered by start_time - previously
    # a full scan of every span partition plus a sort.
    op.execute("DROP INDEX IF EXISTS idx_spans_errors")
    op.execute("DROP INDEX IF EXISTS idx_spans_trace")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_spans_roots "
        "ON spans (project_id, start_time DESC) WHERE parent_span_id IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_spans_project_trace ON spans (project_id, trace_id)"
    )

    op.execute("DROP INDEX IF EXISTS idx_error_groups_type")
    # Revision 001 created both a UNIQUE constraint and a matching unique index
    # on (project_id, fingerprint); the index alone is enough to enforce it and
    # to serve as the ingestion worker's ON CONFLICT target.
    op.execute(
        "ALTER TABLE error_groups DROP CONSTRAINT IF EXISTS uq_error_groups_project_fingerprint"
    )
    # list_error_groups() without a status filter, and the retention job's
    # per-project prune, both want (project_id, last_seen).
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_error_groups_last_seen "
        "ON error_groups (project_id, last_seen DESC)"
    )
    # Alert metric 'new_error_type' counts groups first seen inside the lookback.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_error_groups_first_seen "
        "ON error_groups (project_id, first_seen DESC)"
    )
    # Regression detector scans for resolved groups that have been seen again.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_error_groups_resolved "
        "ON error_groups (project_id, resolved_at) "
        "WHERE status = 'resolved' AND resolved_at IS NOT NULL"
    )

    # Readers filter (project_id, metric_type) for equality and `date` as a
    # range, so `date` has to come last or it stops metric_type from being used
    # as an index qual.
    op.execute("DROP INDEX IF EXISTS idx_aggregated_metrics_lookup")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_aggregated_metrics_lookup "
        "ON aggregated_metrics (project_id, metric_type, date)"
    )
    op.execute("DROP INDEX IF EXISTS idx_aggregated_metrics_endpoint")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_aggregated_metrics_endpoint "
        "ON aggregated_metrics (project_id, endpoint_path, date) "
        "WHERE metric_type = 'endpoint'"
    )

    # uq_bottleneck_metrics (project_id, date, hour, route) already serves the
    # only reader (get_bottleneck_list: project_id equality + date range) via its
    # leading prefix; nothing filters on `hour` or on an exact `route`.
    op.execute("DROP INDEX IF EXISTS idx_bottleneck_metrics_lookup")
    op.execute("DROP INDEX IF EXISTS idx_bottleneck_metrics_route")

    op.execute("DROP INDEX IF EXISTS idx_el1h_project_bucket")
    op.execute("DROP TABLE IF EXISTS endpoint_latency_1h")

    op.execute("DROP INDEX IF EXISTS idx_ingestion_metrics_project_date")
    op.execute("DROP TABLE IF EXISTS ingestion_metrics")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_metrics (
            id BIGSERIAL NOT NULL,
            project_id BIGINT NOT NULL,
            metric_date DATE NOT NULL,
            total_logs BIGINT DEFAULT 0 NOT NULL,
            total_errors BIGINT DEFAULT 0 NOT NULL,
            total_criticals BIGINT DEFAULT 0 NOT NULL,
            avg_processing_time_ms FLOAT,
            created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_metrics_project_date UNIQUE (project_id, metric_date)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ingestion_metrics_project_date "
        "ON ingestion_metrics (project_id, metric_date)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS endpoint_latency_1h (
            project_id  BIGINT NOT NULL,
            route       TEXT NOT NULL,
            bucket      TIMESTAMPTZ NOT NULL,
            count       BIGINT NOT NULL DEFAULT 0,
            p50_ms      DOUBLE PRECISION,
            p95_ms      DOUBLE PRECISION,
            p99_ms      DOUBLE PRECISION,
            PRIMARY KEY (project_id, route, bucket)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_el1h_project_bucket "
        "ON endpoint_latency_1h (project_id, bucket DESC)"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bottleneck_metrics_route "
        "ON bottleneck_metrics (project_id, date, route)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bottleneck_metrics_lookup "
        "ON bottleneck_metrics (project_id, date, hour)"
    )

    op.execute("DROP INDEX IF EXISTS idx_aggregated_metrics_endpoint")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_aggregated_metrics_endpoint "
        "ON aggregated_metrics (project_id, date, endpoint_path) "
        "WHERE metric_type = 'endpoint'"
    )
    op.execute("DROP INDEX IF EXISTS idx_aggregated_metrics_lookup")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_aggregated_metrics_lookup "
        "ON aggregated_metrics (project_id, date, metric_type)"
    )

    op.execute("DROP INDEX IF EXISTS idx_error_groups_resolved")
    op.execute("DROP INDEX IF EXISTS idx_error_groups_first_seen")
    op.execute("DROP INDEX IF EXISTS idx_error_groups_last_seen")
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE error_groups ADD CONSTRAINT uq_error_groups_project_fingerprint
                UNIQUE (project_id, fingerprint);
        EXCEPTION WHEN duplicate_table THEN NULL;
        END $$
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_error_groups_type "
        "ON error_groups (project_id, error_type, last_seen)"
    )

    op.execute("DROP INDEX IF EXISTS idx_spans_project_trace")
    op.execute("DROP INDEX IF EXISTS idx_spans_roots")
    op.execute("CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans (trace_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_spans_errors "
        "ON spans (project_id, start_time DESC) WHERE status_code = 2"
    )

    op.execute("DROP INDEX IF EXISTS idx_logs_project_level")

    op.execute("DROP INDEX IF EXISTS idx_logs_error_fingerprint")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_error_fingerprint "
        "ON logs (error_fingerprint) WHERE error_fingerprint IS NOT NULL"
    )

    op.execute("DROP INDEX IF EXISTS idx_logs_project_timestamp")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_project_timestamp ON logs (project_id, timestamp)"
    )

    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS trace_id CHAR(32)")
    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS span_id CHAR(16)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_log_trace ON logs (trace_id) WHERE trace_id IS NOT NULL"
    )

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_logs_message_trgm ON logs USING gin (message gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_logs_error_message_trgm "
        "ON logs USING gin (error_message gin_trgm_ops)"
    )
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_error_list_covering
        ON logs (project_id, timestamp DESC, level, log_type, error_type, message,
                 error_fingerprint, sdk_version, platform)
        WHERE level IN ('error', 'critical')
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_endpoint_duration
        ON logs (project_id, timestamp DESC, ((attributes->'endpoint'->>'duration_ms')::float))
        WHERE log_type = 'endpoint' AND attributes->'endpoint'->>'duration_ms' IS NOT NULL
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_logs_attributes_gin ON logs USING gin (attributes)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_logs_importance ON logs (importance)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_logs_log_type ON logs (log_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON logs (level)")
