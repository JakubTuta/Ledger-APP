import datetime
import re
import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.retention")

_DELETE_BATCH_SIZE = 5000
_ROLLUP_RETENTION_DAYS = 90

_LOGS_PARTITION_RE = re.compile(r"^logs_(\d{4})_(\d{2})$")
_SPANS_PARTITION_RE = re.compile(r"^spans_(\d{4})_(\d{2})_(\d{2})$")
_METRIC_POINTS_PARTITION_RE = re.compile(r"^metric_points_(\d{4})_(\d{2})$")

_ROLLUP_TABLES = (
    ("log_volume_5m", "bucket"),
    ("log_volume_1h", "bucket"),
    ("log_volume_1d", "bucket"),
    ("error_rate_5m", "bucket"),
    ("endpoint_latency_1h", "bucket"),
    ("span_latency_1h", "bucket"),
    ("metric_points_1h", "bucket"),
)


async def enforce_retention() -> None:
    start = time.perf_counter()

    try:
        async with database.get_auth_session() as auth_session:
            result = await auth_session.execute(sa.text("SELECT id, retention_days FROM projects"))
            project_retention = {row[0]: row[1] for row in result.fetchall()}

        if not project_retention:
            logger.info("No projects found; skipping retention enforcement")
            return

        max_retention_days = max(project_retention.values())
        now = datetime.datetime.now(datetime.timezone.utc)

        async with database.get_logs_session() as logs_session:
            await _drop_expired_partitions(logs_session, "logs", now, max_retention_days)
            await _drop_expired_partitions(logs_session, "spans", now, max_retention_days)
            await _drop_expired_partitions(logs_session, "metric_points", now, max_retention_days)
            await _trim_short_retention_projects(
                logs_session, "logs", "timestamp", project_retention, max_retention_days, now
            )
            await _trim_short_retention_projects(
                logs_session, "spans", "start_time", project_retention, max_retention_days, now
            )
            await _trim_short_retention_projects(
                logs_session, "metric_points", "ts", project_retention, max_retention_days, now
            )
            await _prune_error_groups(logs_session, project_retention, now)
            await _prune_rollups(logs_session, now)

        elapsed = time.perf_counter() - start
        logger.info(f"Retention enforcement done in {elapsed:.2f}s")

    except Exception as e:
        logger.error(f"Retention enforcement failed: {e}", exc_info=True)
        raise


def _partition_range_end(table: str, name: str) -> datetime.date | None:
    if table == "logs" or table == "metric_points":
        pattern = _LOGS_PARTITION_RE if table == "logs" else _METRIC_POINTS_PARTITION_RE
        m = pattern.match(name)
        if not m:
            return None
        year, month = int(m.group(1)), int(m.group(2))
        if month == 12:
            return datetime.date(year + 1, 1, 1)
        return datetime.date(year, month + 1, 1)

    if table == "spans":
        m = _SPANS_PARTITION_RE.match(name)
        if not m:
            return None
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return datetime.date(year, month, day) + datetime.timedelta(days=1)

    return None


async def _drop_expired_partitions(
    session: sa.ext.asyncio.AsyncSession,
    table: str,
    now: datetime.datetime,
    max_retention_days: int,
) -> None:
    cutoff_date = (now - datetime.timedelta(days=max_retention_days)).date()

    result = await session.execute(
        sa.text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE :pattern"
        ),
        {"pattern": f"{table}\\_%"},
    )
    partition_names = [row[0] for row in result.fetchall()]

    for name in partition_names:
        range_end = _partition_range_end(table, name)
        if range_end is None or range_end > cutoff_date:
            continue

        try:
            await session.execute(sa.text(f"ALTER TABLE {table} DETACH PARTITION {name}"))
            await session.execute(sa.text(f"DROP TABLE IF EXISTS {name}"))
            await session.commit()
            logger.info(f"Dropped expired partition {name} (range end {range_end})")
        except Exception as e:
            await session.rollback()
            logger.warning(f"Failed to drop expired partition {name}: {e}")


async def _trim_short_retention_projects(
    session: sa.ext.asyncio.AsyncSession,
    table: str,
    timestamp_column: str,
    project_retention: dict[int, int],
    max_retention_days: int,
    now: datetime.datetime,
) -> None:
    for project_id, retention_days in project_retention.items():
        if retention_days >= max_retention_days:
            continue

        cutoff = now - datetime.timedelta(days=retention_days)

        while True:
            result = await session.execute(
                sa.text(
                    f"""
                    DELETE FROM {table} WHERE ctid IN (
                        SELECT ctid FROM {table}
                        WHERE project_id = :pid AND {timestamp_column} < :cutoff
                        LIMIT :limit
                    )
                    """
                ),
                {"pid": project_id, "cutoff": cutoff, "limit": _DELETE_BATCH_SIZE},
            )
            await session.commit()

            if result.rowcount is None or result.rowcount < _DELETE_BATCH_SIZE:
                break


async def _prune_error_groups(
    session: sa.ext.asyncio.AsyncSession,
    project_retention: dict[int, int],
    now: datetime.datetime,
) -> None:
    for project_id, retention_days in project_retention.items():
        cutoff = now - datetime.timedelta(days=retention_days)
        await session.execute(
            sa.text("DELETE FROM error_groups WHERE project_id = :pid AND last_seen < :cutoff"),
            {"pid": project_id, "cutoff": cutoff},
        )
    await session.commit()


async def _prune_rollups(session: sa.ext.asyncio.AsyncSession, now: datetime.datetime) -> None:
    cutoff = now - datetime.timedelta(days=_ROLLUP_RETENTION_DAYS)
    for table, column in _ROLLUP_TABLES:
        await session.execute(
            sa.text(f"DELETE FROM {table} WHERE {column} < :cutoff"),
            {"cutoff": cutoff},
        )
    await session.commit()
