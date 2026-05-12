import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.log_volume_1h_rollup")


async def rollup_log_volume_1h() -> None:
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            upsert = sa.text(
                """
                INSERT INTO log_volume_1h (project_id, level, bucket, count)
                SELECT
                    project_id,
                    level,
                    date_trunc('hour', bucket) AS bucket,
                    SUM(count)               AS count
                FROM log_volume_5m
                WHERE bucket >= NOW() - INTERVAL '8 days'
                GROUP BY project_id, level, date_trunc('hour', bucket)
                ON CONFLICT (project_id, level, bucket)
                DO UPDATE SET count = EXCLUDED.count
                """
            )
            result = await session.execute(upsert)
            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"log_volume_1h rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"log_volume_1h rollup failed: {e}", exc_info=True)
        raise
