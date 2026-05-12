import datetime
import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.custom_metrics_rollup")

_DEFAULT_LOOKBACKS = {
    "custom_metrics_5m_rollup": datetime.timedelta(hours=25),
    "custom_metrics_1h_rollup": datetime.timedelta(days=8),
    "custom_metrics_1d_rollup": datetime.timedelta(days=100),
}


async def _get_last_bucket(
    session: sa.ext.asyncio.AsyncSession, job_name: str
) -> datetime.datetime:
    result = await session.execute(
        sa.text("SELECT last_bucket FROM rollup_job_state WHERE job_name = :name"),
        {"name": job_name},
    )
    row = result.fetchone()
    if row:
        return row[0]
    return datetime.datetime.now(datetime.timezone.utc) - _DEFAULT_LOOKBACKS[job_name]


async def _set_last_bucket(
    session: sa.ext.asyncio.AsyncSession, job_name: str, bucket: datetime.datetime
) -> None:
    await session.execute(
        sa.text(
            """
            INSERT INTO rollup_job_state (job_name, last_bucket)
            VALUES (:name, :bucket)
            ON CONFLICT (job_name) DO UPDATE SET last_bucket = EXCLUDED.last_bucket
            """
        ),
        {"name": job_name, "bucket": bucket},
    )


async def rollup_custom_metrics_5m() -> None:
    await _rollup_5m()


async def rollup_custom_metrics_1h() -> None:
    await _rollup_1h()


async def rollup_custom_metrics_1d() -> None:
    await _rollup_1d()


async def _rollup_5m() -> None:
    job_name = "custom_metrics_5m_rollup"
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            last_bucket = await _get_last_bucket(session, job_name)

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
                WHERE ts >= :since
                GROUP BY project_id, name, tags, bucket, type
                ON CONFLICT (project_id, name, tags, bucket)
                DO UPDATE SET
                    count = EXCLUDED.count,
                    sum   = EXCLUDED.sum,
                    min_v = EXCLUDED.min_v,
                    max_v = EXCLUDED.max_v
                """
            )
            result = await session.execute(upsert, {"since": last_bucket})

            max_result = await session.execute(
                sa.text("SELECT MAX(ts) FROM custom_metrics WHERE ts >= :since"),
                {"since": last_bucket},
            )
            max_bucket_row = max_result.fetchone()
            if max_bucket_row and max_bucket_row[0] is not None:
                await _set_last_bucket(session, job_name, max_bucket_row[0])

            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"custom_metrics_5m rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"custom_metrics_5m rollup failed: {e}", exc_info=True)
        raise


async def _rollup_1h() -> None:
    job_name = "custom_metrics_1h_rollup"
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            last_bucket = await _get_last_bucket(session, job_name)

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
                WHERE bucket >= :since
                GROUP BY project_id, name, tags, date_trunc('hour', bucket), type
                ON CONFLICT (project_id, name, tags, bucket)
                DO UPDATE SET
                    count = EXCLUDED.count,
                    sum   = EXCLUDED.sum,
                    min_v = EXCLUDED.min_v,
                    max_v = EXCLUDED.max_v
                """
            )
            result = await session.execute(upsert, {"since": last_bucket})

            max_result = await session.execute(
                sa.text("SELECT MAX(bucket) FROM custom_metrics_5m WHERE bucket >= :since"),
                {"since": last_bucket},
            )
            max_bucket_row = max_result.fetchone()
            if max_bucket_row and max_bucket_row[0] is not None:
                await _set_last_bucket(session, job_name, max_bucket_row[0])

            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"custom_metrics_1h rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"custom_metrics_1h rollup failed: {e}", exc_info=True)
        raise


async def _rollup_1d() -> None:
    job_name = "custom_metrics_1d_rollup"
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            last_bucket = await _get_last_bucket(session, job_name)

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
                WHERE bucket >= :since
                GROUP BY project_id, name, tags, bucket::date, type
                ON CONFLICT (project_id, name, tags, bucket)
                DO UPDATE SET
                    count = EXCLUDED.count,
                    sum   = EXCLUDED.sum,
                    min_v = EXCLUDED.min_v,
                    max_v = EXCLUDED.max_v
                """
            )
            result = await session.execute(upsert, {"since": last_bucket})

            max_result = await session.execute(
                sa.text("SELECT MAX(bucket) FROM custom_metrics_1h WHERE bucket >= :since"),
                {"since": last_bucket},
            )
            max_bucket_row = max_result.fetchone()
            if max_bucket_row and max_bucket_row[0] is not None:
                await _set_last_bucket(session, job_name, max_bucket_row[0])

            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"custom_metrics_1d rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"custom_metrics_1d rollup failed: {e}", exc_info=True)
        raise
