import datetime
import time

import analytics_workers.database as database
import analytics_workers.jobs.rollup_state as rollup_state
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.service_edges_1h_rollup")

_JOB_NAME = "service_edges_1h_rollup"
_DEFAULT_LOOKBACK = datetime.timedelta(days=8)

# Must match query_service/services/correlation.py, which reads the same graph
# from raw spans for short windows: internal SpanKind values, the entry-span
# rule and the attributes naming an uninstrumented dependency.
_UPSERT = sa.text(
    """
    INSERT INTO service_edges_1h (
        project_id, bucket, caller, callee, calls, errors, duration_ns_sum, p95_ns
    )
    WITH window_spans AS MATERIALIZED (
        SELECT project_id, span_id, trace_id, parent_span_id, service_name, kind,
               start_time, duration_ns, status_code,
               CASE WHEN kind IN (1, 3) THEN COALESCE(
                   attributes->>'peer.service', attributes->>'db.system',
                   attributes->>'messaging.system', attributes->>'server.address'
               ) END AS dependency
        FROM spans
        -- a parent can start shortly before the hour its child falls in
        WHERE start_time >= date_trunc('hour', CAST(:since AS timestamptz)) - INTERVAL '5 minutes'
    ),
    edges AS (
        SELECT project_id, start_time, '' AS caller, service_name AS callee,
               duration_ns, status_code
        FROM window_spans
        WHERE kind IN (0, 4) OR parent_span_id IS NULL
        UNION ALL
        SELECT child.project_id, child.start_time, parent.service_name, child.service_name,
               child.duration_ns, child.status_code
        FROM window_spans child
        JOIN window_spans parent
          ON parent.project_id = child.project_id
         AND parent.trace_id = child.trace_id
         AND parent.span_id = child.parent_span_id
        WHERE parent.service_name <> child.service_name
        UNION ALL
        SELECT c.project_id, c.start_time, c.service_name, c.dependency,
               c.duration_ns, c.status_code
        FROM window_spans c
        WHERE c.dependency IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM window_spans child
              WHERE child.project_id = c.project_id
                AND child.trace_id = c.trace_id
                AND child.parent_span_id = c.span_id
          )
    )
    SELECT project_id,
           date_trunc('hour', start_time) AS bucket,
           caller,
           callee,
           COUNT(*) AS calls,
           COUNT(*) FILTER (WHERE status_code = 2) AS errors,
           SUM(duration_ns) AS duration_ns_sum,
           PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ns)::bigint AS p95_ns
    FROM edges
    WHERE start_time >= date_trunc('hour', CAST(:since AS timestamptz))
    GROUP BY project_id, date_trunc('hour', start_time), caller, callee
    ON CONFLICT (project_id, bucket, caller, callee) DO UPDATE SET
        calls = EXCLUDED.calls,
        errors = EXCLUDED.errors,
        duration_ns_sum = EXCLUDED.duration_ns_sum,
        p95_ns = EXCLUDED.p95_ns
    """
)


async def rollup_service_edges_1h() -> None:
    """Recompute the hourly service graph from the watermark's hour onwards.

    Like metric_points_1h, the scan starts at the top of the watermark's hour:
    ON CONFLICT replaces a bucket outright, so a mid-hour start would overwrite
    a complete hour with only its tail.
    """
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            last_bucket = await rollup_state.get_last_bucket(session, _JOB_NAME, _DEFAULT_LOOKBACK)
            result = await session.execute(_UPSERT, {"since": last_bucket})

            max_result = await session.execute(
                sa.text(
                    "SELECT MAX(start_time) FROM spans "
                    "WHERE start_time >= date_trunc('hour', CAST(:since AS timestamptz))"
                ),
                {"since": last_bucket},
            )
            newest = max_result.scalar()
            if newest is not None:
                await rollup_state.set_last_bucket(session, _JOB_NAME, newest)

            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"service_edges_1h rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"service_edges_1h rollup failed: {e}", exc_info=True)
        raise
