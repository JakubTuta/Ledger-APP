import datetime
import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.log_volume_1h_rollup")

_JOB_NAME = "log_volume_1h_rollup"
_DEFAULT_LOOKBACK = datetime.timedelta(days=8)


async def _get_last_bucket(session: sa.ext.asyncio.AsyncSession) -> datetime.datetime:
    result = await session.execute(
        sa.text("SELECT last_bucket FROM rollup_job_state WHERE job_name = :name"),
        {"name": _JOB_NAME},
    )
    row = result.fetchone()
    if row:
        return row[0]
    return datetime.datetime.now(datetime.timezone.utc) - _DEFAULT_LOOKBACK


async def _set_last_bucket(
    session: sa.ext.asyncio.AsyncSession, bucket: datetime.datetime
) -> None:
    await session.execute(
        sa.text(
            """
            INSERT INTO rollup_job_state (job_name, last_bucket)
            VALUES (:name, :bucket)
            ON CONFLICT (job_name) DO UPDATE SET last_bucket = EXCLUDED.last_bucket
            """
        ),
        {"name": _JOB_NAME, "bucket": bucket},
    )


async def rollup_log_volume_1h() -> None:
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            last_bucket = await _get_last_bucket(session)

            upsert = sa.text(
                """
                INSERT INTO log_volume_1h (project_id, level, bucket, count)
                SELECT
                    project_id,
                    level,
                    date_trunc('hour', bucket) AS bucket,
                    SUM(count)               AS count
                FROM log_volume_5m
                WHERE bucket >= :since
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
                await _set_last_bucket(session, max_bucket_row[0])

            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(f"log_volume_1h rollup done in {elapsed:.2f}s, {result.rowcount} rows")

    except Exception as e:
        logger.error(f"log_volume_1h rollup failed: {e}", exc_info=True)
        raise
