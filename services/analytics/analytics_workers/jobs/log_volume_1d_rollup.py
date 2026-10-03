import datetime
import time

import analytics_workers.database as database
import analytics_workers.jobs.rollup_state as rollup_state
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.log_volume_1d_rollup")

_JOB_NAME = "log_volume_1d_rollup"
_DEFAULT_LOOKBACK = datetime.timedelta(days=35)


async def rollup_log_volume_1d() -> None:
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            last_bucket = await rollup_state.get_last_bucket(session, _JOB_NAME, _DEFAULT_LOOKBACK)

            # Same reasoning as the hourly rollup: ON CONFLICT overwrites the
            # day, so the scan has to start at the top of the watermark's day.
            upsert = sa.text(
                """
                INSERT INTO log_volume_1d (project_id, level, bucket, count)
                SELECT
                    project_id,
                    level,
                    bucket::date AS bucket,
                    SUM(count)  AS count
                FROM log_volume_1h
                WHERE bucket >= date_trunc('day', CAST(:since AS timestamptz))
                GROUP BY project_id, level, bucket::date
                ON CONFLICT (project_id, level, bucket)
                DO UPDATE SET count = EXCLUDED.count
                """
            )
            result = await session.execute(upsert, {"since": last_bucket})

            max_result = await session.execute(
                sa.text("SELECT MAX(bucket) FROM log_volume_1h WHERE bucket >= :since"),
                {"since": last_bucket},
            )
            max_bucket_row = max_result.fetchone()
            if max_bucket_row and max_bucket_row[0] is not None:
                await rollup_state.set_last_bucket(session, _JOB_NAME, max_bucket_row[0])

            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"log_volume_1d rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"log_volume_1d rollup failed: {e}", exc_info=True)
        raise
