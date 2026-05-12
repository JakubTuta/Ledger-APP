import datetime
import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.partition_manager")

_DAILY_TABLES = ("spans", "custom_metrics")
_DAYS_AHEAD = 7
_LOGS_MONTHS_AHEAD = 3


async def manage_partitions() -> None:
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            await _ensure_daily_partitions(session)
            await _ensure_logs_partitions(session)

        elapsed = time.perf_counter() - start
        logger.info(f"Partition management done in {elapsed:.2f}s")

    except Exception as e:
        logger.error(f"Partition management failed: {e}", exc_info=True)
        raise


async def _ensure_daily_partitions(session: sa.ext.asyncio.AsyncSession) -> None:
    today = datetime.date.today()

    for table in _DAILY_TABLES:
        for offset in range(_DAYS_AHEAD):
            d = today + datetime.timedelta(days=offset)
            partition_name = f"{table}_{d.strftime('%Y_%m_%d')}"
            range_start = d
            range_end = d + datetime.timedelta(days=1)

            exists_result = await session.execute(
                sa.text(
                    "SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = :name"
                ),
                {"name": partition_name},
            )
            if exists_result.scalar():
                continue

            try:
                await session.execute(
                    sa.text(
                        f"CREATE TABLE IF NOT EXISTS {partition_name} "
                        f"PARTITION OF {table} "
                        f"FOR VALUES FROM ('{range_start}') TO ('{range_end}')"
                    )
                )
                await session.commit()
                logger.info(f"Created partition {partition_name}")
            except Exception as e:
                await session.rollback()
                logger.warning(f"Failed to create partition {partition_name}: {e}")


async def _ensure_logs_partitions(session: sa.ext.asyncio.AsyncSession) -> None:
    today = datetime.date.today()
    first_of_month = today.replace(day=1)

    for month_offset in range(_LOGS_MONTHS_AHEAD + 1):
        year = first_of_month.year
        month = first_of_month.month + month_offset
        if month > 12:
            year += (month - 1) // 12
            month = ((month - 1) % 12) + 1

        partition_name = f"logs_{year}_{month:02d}"
        range_start = datetime.date(year, month, 1)
        if month == 12:
            range_end = datetime.date(year + 1, 1, 1)
        else:
            range_end = datetime.date(year, month + 1, 1)

        exists_result = await session.execute(
            sa.text(
                "SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = :name"
            ),
            {"name": partition_name},
        )
        if exists_result.scalar():
            continue

        try:
            await session.execute(
                sa.text(
                    f"CREATE TABLE IF NOT EXISTS {partition_name} "
                    f"PARTITION OF logs "
                    f"FOR VALUES FROM ('{range_start}') TO ('{range_end}')"
                )
            )
            await session.commit()
            logger.info(f"Created partition {partition_name}")
        except Exception as e:
            await session.rollback()
            logger.warning(f"Failed to create partition {partition_name}: {e}")
