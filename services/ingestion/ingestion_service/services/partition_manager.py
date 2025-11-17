import asyncio
import datetime
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_partition_cache: set[str] = set()
_cache_lock = asyncio.Lock()


def _get_partition_name(table_name: str, date: datetime.date) -> str:
    first_of_month = date.replace(day=1)
    return f"{table_name}_{first_of_month.year}_{first_of_month.month:02d}"


def _get_partition_range(date: datetime.date) -> tuple[datetime.date, datetime.date]:
    first_of_month = date.replace(day=1)

    if first_of_month.month == 12:
        next_month = datetime.date(first_of_month.year + 1, 1, 1)
    else:
        next_month = datetime.date(first_of_month.year, first_of_month.month + 1, 1)

    return first_of_month, next_month


async def check_partition_exists(
    session: AsyncSession,
    table_name: str,
    date: datetime.date,
) -> bool:
    partition_name = _get_partition_name(table_name, date)

    async with _cache_lock:
        if partition_name in _partition_cache:
            return True

    check_sql = text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename = :partition_name
        )
    """)

    result = await session.execute(check_sql, {"partition_name": partition_name})
    exists = result.scalar()

    if exists:
        async with _cache_lock:
            _partition_cache.add(partition_name)

    return exists


async def create_partition(
    session: AsyncSession,
    table_name: str,
    date: datetime.date,
) -> bool:
    partition_name = _get_partition_name(table_name, date)
    range_start, range_end = _get_partition_range(date)

    try:
        create_partition_sql = text(f"""
            CREATE TABLE IF NOT EXISTS {partition_name} PARTITION OF {table_name}
            FOR VALUES FROM ('{range_start}') TO ('{range_end}')
        """)

        await session.execute(create_partition_sql)
        await session.commit()

        async with _cache_lock:
            _partition_cache.add(partition_name)

        logger.info(
            f"Created partition: {partition_name} "
            f"(range: {range_start} to {range_end})"
        )
        return True

    except Exception as e:
        await session.rollback()
        logger.error(f"Failed to create partition {partition_name}: {e}")
        return False


async def ensure_partition_for_date(
    session: AsyncSession,
    table_name: str,
    date: datetime.date,
) -> bool:
    exists = await check_partition_exists(session, table_name, date)

    if not exists:
        logger.info(
            f"Partition for {table_name} on {date} does not exist, creating..."
        )
        return await create_partition(session, table_name, date)

    return True


async def ensure_partition_for_timestamp(
    session: AsyncSession,
    table_name: str,
    timestamp: datetime.datetime,
) -> bool:
    date = timestamp.date() if isinstance(timestamp, datetime.datetime) else timestamp
    return await ensure_partition_for_date(session, table_name, date)


async def ensure_partitions_range(
    session: AsyncSession,
    table_name: str,
    start_date: datetime.date,
    months_ahead: int = 3,
) -> int:
    created_count = 0
    current_date = start_date.replace(day=1)

    for month_offset in range(months_ahead + 1):
        partition_date = current_date + datetime.timedelta(days=32 * month_offset)
        partition_date = partition_date.replace(day=1)

        exists = await check_partition_exists(session, table_name, partition_date)

        if not exists:
            success = await create_partition(session, table_name, partition_date)
            if success:
                created_count += 1

    return created_count


async def ensure_logs_partitions(
    session: AsyncSession,
    months_ahead: int = 3,
) -> int:
    today = datetime.date.today()
    return await ensure_partitions_range(session, "logs", today, months_ahead)


async def ensure_metrics_partitions(
    session: AsyncSession,
    months_ahead: int = 3,
) -> int:
    today = datetime.date.today()
    return await ensure_partitions_range(session, "ingestion_metrics", today, months_ahead)


async def ensure_all_partitions(
    session: AsyncSession,
    months_ahead: int = 3,
) -> dict[str, int]:
    logs_created = await ensure_logs_partitions(session, months_ahead)
    metrics_created = await ensure_metrics_partitions(session, months_ahead)

    logger.info(
        f"Partition management complete: "
        f"logs={logs_created} created, "
        f"metrics={metrics_created} created, "
        f"covering {months_ahead + 1} months"
    )

    return {
        "logs": logs_created,
        "ingestion_metrics": metrics_created,
    }


def clear_partition_cache() -> None:
    global _partition_cache
    _partition_cache.clear()
    logger.info("Partition cache cleared")
