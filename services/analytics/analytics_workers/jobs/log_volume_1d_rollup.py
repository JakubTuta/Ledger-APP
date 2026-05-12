import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.log_volume_1d_rollup")


async def rollup_log_volume_1d() -> None:
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            upsert = sa.text(
                """
                INSERT INTO log_volume_1d (project_id, level, bucket, count)
                SELECT
                    project_id,
                    level,
                    bucket::date AS bucket,
                    SUM(count)  AS count
                FROM log_volume_1h
                WHERE bucket >= NOW() - INTERVAL '35 days'
                GROUP BY project_id, level, bucket::date
                ON CONFLICT (project_id, level, bucket)
                DO UPDATE SET count = EXCLUDED.count
                """
            )
            result = await session.execute(upsert)
            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"log_volume_1d rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"log_volume_1d rollup failed: {e}", exc_info=True)
        raise
