import datetime
import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.log_facets_1h")

# Matches query_service.services.log_query._ROLLUP_WINDOW_DAYS: how far back
# the Explore filter sidebar can read from this rollup instead of raw `logs`.
# Covers last30days/currentMonth; currentYear falls back to raw beyond this.
_WINDOW_DAYS = 32

# Every run recomputes this whole trailing window from scratch (idempotent
# upsert) rather than tracking a watermark of what's already done. Simpler,
# and self-heals a missed run or late-arriving rows automatically on the next
# tick - the cost is a full re-scan of the window each hour, which is cheap
# for a background job (measured ~600ms for 7 days / 700k rows).
_UPSERT = sa.text(
    """
    INSERT INTO log_facets_1h (
        project_id, bucket, level, log_type, status_class, environment,
        client_channel, count
    )
    SELECT
        project_id,
        date_trunc('hour', timestamp) AS bucket,
        level,
        log_type,
        CASE
            WHEN status_code BETWEEN 200 AND 299 THEN '2xx'
            WHEN status_code BETWEEN 300 AND 399 THEN '3xx'
            WHEN status_code BETWEEN 400 AND 499 THEN '4xx'
            WHEN status_code BETWEEN 500 AND 599 THEN '5xx'
            ELSE ''
        END                           AS status_class,
        COALESCE(environment, '')     AS environment,
        COALESCE(client_channel, '')  AS client_channel,
        COUNT(*)                      AS count
    FROM logs
    WHERE timestamp >= :since
    GROUP BY 1, 2, 3, 4, 5, 6, 7
    ON CONFLICT (project_id, bucket, level, log_type, status_class, environment, client_channel)
    DO UPDATE SET count = EXCLUDED.count
    """
)


async def rollup_log_facets_1h() -> None:
    start = time.perf_counter()
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=_WINDOW_DAYS)

    try:
        async with database.get_logs_session() as session:
            result = await session.execute(_UPSERT, {"since": since})
            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"log_facets_1h rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"log_facets_1h rollup failed: {e}", exc_info=True)
        raise
