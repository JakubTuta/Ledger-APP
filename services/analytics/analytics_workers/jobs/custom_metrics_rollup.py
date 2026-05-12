import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.custom_metrics_rollup")


async def rollup_custom_metrics_5m() -> None:
    await _rollup_5m()


async def rollup_custom_metrics_1h() -> None:
    await _rollup_1h()


async def rollup_custom_metrics_1d() -> None:
    await _rollup_1d()


async def _rollup_5m() -> None:
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            upsert = sa.text(
                """
                INSERT INTO custom_metrics_5m (
                    project_id, name, tags, bucket, type,
                    count, sum, min_v, max_v
                )
                SELECT
                    project_id,
                    name,
                    tags,
                    date_trunc('hour', ts) +
                        (EXTRACT(minute FROM ts)::int / 5) * INTERVAL '5 minutes' AS bucket,
                    type,
                    SUM(count)       AS count,
                    SUM(sum)         AS sum,
                    MIN(min_v)       AS min_v,
                    MAX(max_v)       AS max_v
                FROM custom_metrics
                WHERE ts >= NOW() - INTERVAL '25 hours'
                GROUP BY project_id, name, tags, bucket, type
                ON CONFLICT (project_id, name, tags, bucket)
                DO UPDATE SET
                    count = EXCLUDED.count,
                    sum   = EXCLUDED.sum,
                    min_v = EXCLUDED.min_v,
                    max_v = EXCLUDED.max_v
                """
            )
            result = await session.execute(upsert)
            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"custom_metrics_5m rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"custom_metrics_5m rollup failed: {e}", exc_info=True)
        raise


async def _rollup_1h() -> None:
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            upsert = sa.text(
                """
                INSERT INTO custom_metrics_1h (
                    project_id, name, tags, bucket, type,
                    count, sum, min_v, max_v
                )
                SELECT
                    project_id,
                    name,
                    tags,
                    date_trunc('hour', bucket) AS bucket,
                    type,
                    SUM(count)  AS count,
                    SUM(sum)    AS sum,
                    MIN(min_v)  AS min_v,
                    MAX(max_v)  AS max_v
                FROM custom_metrics_5m
                WHERE bucket >= NOW() - INTERVAL '8 days'
                GROUP BY project_id, name, tags, date_trunc('hour', bucket), type
                ON CONFLICT (project_id, name, tags, bucket)
                DO UPDATE SET
                    count = EXCLUDED.count,
                    sum   = EXCLUDED.sum,
                    min_v = EXCLUDED.min_v,
                    max_v = EXCLUDED.max_v
                """
            )
            result = await session.execute(upsert)
            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"custom_metrics_1h rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"custom_metrics_1h rollup failed: {e}", exc_info=True)
        raise


async def _rollup_1d() -> None:
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            upsert = sa.text(
                """
                INSERT INTO custom_metrics_1d (
                    project_id, name, tags, bucket, type,
                    count, sum, min_v, max_v
                )
                SELECT
                    project_id,
                    name,
                    tags,
                    bucket::date AS bucket,
                    type,
                    SUM(count)  AS count,
                    SUM(sum)    AS sum,
                    MIN(min_v)  AS min_v,
                    MAX(max_v)  AS max_v
                FROM custom_metrics_1h
                WHERE bucket >= NOW() - INTERVAL '100 days'
                GROUP BY project_id, name, tags, bucket::date, type
                ON CONFLICT (project_id, name, tags, bucket)
                DO UPDATE SET
                    count = EXCLUDED.count,
                    sum   = EXCLUDED.sum,
                    min_v = EXCLUDED.min_v,
                    max_v = EXCLUDED.max_v
                """
            )
            result = await session.execute(upsert)
            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"custom_metrics_1d rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"custom_metrics_1d rollup failed: {e}", exc_info=True)
        raise
