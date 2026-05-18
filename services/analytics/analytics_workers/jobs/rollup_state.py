import datetime

import sqlalchemy as sa


async def get_last_bucket(
    session: sa.ext.asyncio.AsyncSession,
    job_name: str,
    default_lookback: datetime.timedelta,
) -> datetime.datetime:
    result = await session.execute(
        sa.text("SELECT last_bucket FROM rollup_job_state WHERE job_name = :name"),
        {"name": job_name},
    )
    row = result.fetchone()
    if row:
        return row[0]
    return datetime.datetime.now(datetime.timezone.utc) - default_lookback


async def set_last_bucket(
    session: sa.ext.asyncio.AsyncSession,
    job_name: str,
    bucket: datetime.datetime,
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
