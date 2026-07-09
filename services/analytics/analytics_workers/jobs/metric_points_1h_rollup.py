import datetime
import time

import analytics_workers.database as database
import analytics_workers.jobs.rollup_state as rollup_state
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.metric_points_1h_rollup")

_JOB_NAME = "metric_points_1h_rollup"
_DEFAULT_LOOKBACK = datetime.timedelta(days=8)


async def rollup_metric_points_1h() -> None:
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            last_bucket = await rollup_state.get_last_bucket(session, _JOB_NAME, _DEFAULT_LOOKBACK)

            # effective_value mirrors query_service/services/metric_points.py's raw-path
            # semantics exactly: gauges/sums use `value` directly, histograms (type=2)
            # derive a mean from sum/count. count/sum_v/min_v/max_v/avg_v below are all
            # computed over that same effective_value, so the rollup and the raw path
            # agree for any window that straddles the rollup threshold.
            upsert = sa.text(
                """
                INSERT INTO metric_points_1h (
                    project_id, name, type, tags_hash, tags, bucket,
                    count, sum_v, min_v, max_v, avg_v
                )
                SELECT
                    project_id,
                    name,
                    MIN(type)                     AS type,
                    tags_hash,
                    (array_agg(tags))[1]           AS tags,
                    date_trunc('hour', ts)        AS bucket,
                    COUNT(*)                      AS count,
                    SUM(effective_value)          AS sum_v,
                    MIN(effective_value)          AS min_v,
                    MAX(effective_value)          AS max_v,
                    AVG(effective_value)          AS avg_v
                FROM (
                    SELECT
                        project_id, name, type, tags_hash, tags, ts,
                        COALESCE(value, CASE WHEN type = 2 AND count > 0 THEN sum / count END)
                            AS effective_value
                    FROM metric_points
                    WHERE ts >= :since
                ) points
                GROUP BY project_id, name, tags_hash, date_trunc('hour', ts)
                ON CONFLICT (project_id, name, tags_hash, bucket)
                DO UPDATE SET
                    type  = EXCLUDED.type,
                    tags  = EXCLUDED.tags,
                    count = EXCLUDED.count,
                    sum_v = EXCLUDED.sum_v,
                    min_v = EXCLUDED.min_v,
                    max_v = EXCLUDED.max_v,
                    avg_v = EXCLUDED.avg_v
                """
            )
            result = await session.execute(upsert, {"since": last_bucket})

            max_result = await session.execute(
                sa.text("SELECT MAX(ts) FROM metric_points WHERE ts >= :since"),
                {"since": last_bucket},
            )
            max_bucket_row = max_result.fetchone()
            if max_bucket_row and max_bucket_row[0] is not None:
                await rollup_state.set_last_bucket(session, _JOB_NAME, max_bucket_row[0])

            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"metric_points_1h rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"metric_points_1h rollup failed: {e}", exc_info=True)
        raise
