import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.span_latency_1h")


async def rollup_span_latency_1h() -> None:
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            upsert = sa.text(
                """
                INSERT INTO span_latency_1h (
                    project_id, service_name, name, bucket,
                    calls, p50_ns, p95_ns, p99_ns, errors
                )
                SELECT
                    project_id,
                    service_name,
                    name,
                    date_trunc('hour', start_time) AS bucket,
                    COUNT(*)                       AS calls,
                    PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY duration_ns)::bigint AS p50_ns,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ns)::bigint AS p95_ns,
                    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_ns)::bigint AS p99_ns,
                    COUNT(*) FILTER (WHERE status_code = 2)                           AS errors
                FROM spans
                WHERE start_time >= NOW() - INTERVAL '25 hours'
                GROUP BY project_id, service_name, name, date_trunc('hour', start_time)
                ON CONFLICT (project_id, service_name, name, bucket)
                DO UPDATE SET
                    calls  = EXCLUDED.calls,
                    p50_ns = EXCLUDED.p50_ns,
                    p95_ns = EXCLUDED.p95_ns,
                    p99_ns = EXCLUDED.p99_ns,
                    errors = EXCLUDED.errors
                """
            )
            result = await session.execute(upsert)
            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"span_latency_1h rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"span_latency_1h rollup failed: {e}", exc_info=True)
        raise
