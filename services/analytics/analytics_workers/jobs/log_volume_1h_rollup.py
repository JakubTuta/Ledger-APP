import datetime
import time

import analytics_workers.database as database
import analytics_workers.jobs.rollup_state as rollup_state
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.log_volume_1h_rollup")

_JOB_NAME = "log_volume_1h_rollup"
# Matches log_volume_1d's lookback: a fresh watermark has to rebuild every hour
# that the daily rollup will read, or the older days come out short.
_DEFAULT_LOOKBACK = datetime.timedelta(days=35)


async def rollup_log_volume_1h() -> None:
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            last_bucket = await rollup_state.get_last_bucket(session, _JOB_NAME, _DEFAULT_LOOKBACK)

            # The scan starts at the top of the watermark's hour, not at the
            # watermark itself: ON CONFLICT overwrites a bucket outright, so
            # summing from a mid-hour watermark would replace a complete hour
            # with just the slice after it.
            upsert = sa.text(
                """
                INSERT INTO log_volume_1h (project_id, level, bucket, count)
                SELECT
                    project_id,
                    level,
                    date_trunc('hour', bucket) AS bucket,
                    SUM(count)               AS count
                FROM log_volume_5m
                WHERE bucket >= date_trunc('hour', CAST(:since AS timestamptz))
                GROUP BY project_id, level, date_trunc('hour', bucket)
                ON CONFLICT (project_id, level, bucket)
                DO UPDATE SET count = EXCLUDED.count
                """
            )
            result = await session.execute(upsert, {"since": last_bucket})

            max_result = await session.execute(
                sa.text("SELECT MAX(bucket) FROM log_volume_5m WHERE bucket >= :since"),
                {"since": last_bucket},
            )
            max_bucket_row = max_result.fetchone()
            if max_bucket_row and max_bucket_row[0] is not None:
                await rollup_state.set_last_bucket(session, _JOB_NAME, max_bucket_row[0])

            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"log_volume_1h rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"log_volume_1h rollup failed: {e}", exc_info=True)
        raise
