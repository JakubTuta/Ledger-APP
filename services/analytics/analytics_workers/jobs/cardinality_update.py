import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.cardinality_update")


async def update_metric_series_cardinality() -> None:
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            await session.execute(
                sa.text(
                    """
                    INSERT INTO metric_series_count (project_id, series_count, updated_at)
                    SELECT
                        project_id,
                        COUNT(DISTINCT (name, tags::text)) AS series_count,
                        NOW()
                    FROM custom_metrics_5m
                    WHERE bucket >= NOW() - INTERVAL '24 hours'
                    GROUP BY project_id
                    ON CONFLICT (project_id) DO UPDATE
                        SET series_count = EXCLUDED.series_count,
                            updated_at   = EXCLUDED.updated_at
                    """
                )
            )
            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"Cardinality update done in {elapsed:.2f}s")

    except Exception as e:
        logger.error(f"Cardinality update failed: {e}", exc_info=True)
        raise
