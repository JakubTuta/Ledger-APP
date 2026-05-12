import datetime
import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.span_latency_1h")

_JOB_NAME = "span_latency_1h_rollup"
_DEFAULT_LOOKBACK = datetime.timedelta(hours=25)


async def _get_last_bucket(session: sa.ext.asyncio.AsyncSession) -> datetime.datetime:
    result = await session.execute(
        sa.text("SELECT last_bucket FROM rollup_job_state WHERE job_name = :name"),
        {"name": _JOB_NAME},
    )
    row = result.fetchone()
    if row:
        return row[0]
    return datetime.datetime.now(datetime.timezone.utc) - _DEFAULT_LOOKBACK


async def _set_last_bucket(
    session: sa.ext.asyncio.AsyncSession, bucket: datetime.datetime
) -> None:
    await session.execute(
        sa.text(
            """
            INSERT INTO rollup_job_state (job_name, last_bucket)
            VALUES (:name, :bucket)
            ON CONFLICT (job_name) DO UPDATE SET last_bucket = EXCLUDED.last_bucket
            """
        ),
        {"name": _JOB_NAME, "bucket": bucket},
    )


async def rollup_span_latency_1h() -> None:
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            last_bucket = await _get_last_bucket(session)

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
                WHERE start_time >= :since
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
            result = await session.execute(upsert, {"since": last_bucket})

            max_result = await session.execute(
                sa.text("SELECT MAX(start_time) FROM spans WHERE start_time >= :since"),
                {"since": last_bucket},
            )
            max_bucket_row = max_result.fetchone()
            if max_bucket_row and max_bucket_row[0] is not None:
                await _set_last_bucket(session, max_bucket_row[0])

            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"span_latency_1h rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"span_latency_1h rollup failed: {e}", exc_info=True)
        raise
