import datetime
import time

import analytics_workers.database as database
import analytics_workers.jobs.rollup_state as rollup_state
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.log_metrics")

_VALID_LEVELS = frozenset({"debug", "info", "warning", "error", "critical"})
_JOB_NAME = "log_metrics_5m"
_DEFAULT_LOOKBACK = datetime.timedelta(days=7)


async def aggregate_log_metrics() -> None:
    """Roll raw logs up into `log_volume_5m`, the source of the 1h and 1d volume rollups."""
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            last_bucket = await rollup_state.get_last_bucket(session, _JOB_NAME, _DEFAULT_LOOKBACK)

            result = await session.execute(
                sa.text(
                    """
                    SELECT
                        project_id,
                        date_trunc('hour', timestamp) +
                            (EXTRACT(minute FROM timestamp)::int / 5) * INTERVAL '5 minutes' as bucket,
                        level,
                        COUNT(*) as count
                    FROM logs
                    WHERE timestamp >= :since
                    GROUP BY project_id, bucket, level
                    ORDER BY project_id, bucket DESC
                    """
                ),
                {"since": last_bucket},
            )
            rows = result.fetchall()

            volume_5m_rows = [
                {"project_id": project_id, "level": level, "bucket": bucket, "count": count}
                for project_id, bucket, level, count in rows
                if level in _VALID_LEVELS
            ]
            max_bucket = max((bucket for _, bucket, _, _ in rows), default=None)

            if volume_5m_rows:
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO log_volume_5m (project_id, level, bucket, count)
                        VALUES (:project_id, :level, :bucket, :count)
                        ON CONFLICT (project_id, level, bucket)
                        DO UPDATE SET count = EXCLUDED.count
                        """
                    ),
                    volume_5m_rows,
                )

            if max_bucket is not None:
                await rollup_state.set_last_bucket(session, _JOB_NAME, max_bucket)

            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(
            f"Log metrics aggregation done in {elapsed:.2f}s, {len(volume_5m_rows)} volume rows"
        )

    except Exception as e:
        logger.error(f"Log metrics aggregation failed: {e}", exc_info=True)
        raise
