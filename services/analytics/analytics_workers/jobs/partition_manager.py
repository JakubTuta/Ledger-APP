import datetime
import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.partition_manager")

# All three partitioned tables are range-partitioned by calendar month, matching
# ingestion_service.services.partition_manager (which creates them on the write
# path) and the retention job (which drops them by the same name shape). This
# job used to create daily `spans_YYYY_MM_DD` partitions instead, which can
# never coexist with the monthly ones the ingestion worker creates: whichever
# ran first won and the other side failed with an overlap error on every pass.
# metric_points was not covered here at all.
_PARTITIONED_TABLES = ("logs", "spans", "metric_points")
_MONTHS_AHEAD = 3


async def manage_partitions() -> None:
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            for table in _PARTITIONED_TABLES:
                await _ensure_monthly_partitions(session, table)

        elapsed = time.perf_counter() - start
        logger.info(f"Partition management done in {elapsed:.2f}s")

    except Exception as e:
        logger.error(f"Partition management failed: {e}", exc_info=True)
        raise


def _month_range(base: datetime.date, offset: int) -> tuple[datetime.date, datetime.date]:
    month_index = base.year * 12 + (base.month - 1) + offset
    year, month_zero_based = divmod(month_index, 12)
    range_start = datetime.date(year, month_zero_based + 1, 1)

    if range_start.month == 12:
        return range_start, datetime.date(range_start.year + 1, 1, 1)
    return range_start, datetime.date(range_start.year, range_start.month + 1, 1)


async def _ensure_monthly_partitions(session: sa.ext.asyncio.AsyncSession, table: str) -> None:
    first_of_month = datetime.date.today().replace(day=1)

    for month_offset in range(_MONTHS_AHEAD + 1):
        range_start, range_end = _month_range(first_of_month, month_offset)
        partition_name = f"{table}_{range_start.year}_{range_start.month:02d}"

        exists_result = await session.execute(
            sa.text("SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = :name"),
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
