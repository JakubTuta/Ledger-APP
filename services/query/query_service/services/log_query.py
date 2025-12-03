import datetime

import sqlalchemy as sa
import sqlalchemy.ext.asyncio as async_sqlalchemy

import query_service.database as database
import query_service.models as models
import query_service.schemas as schemas


async def query_logs(
    project_id: int,
    filters: schemas.LogFilters,
    pagination: schemas.Pagination,
) -> schemas.LogsQueryResponse:
    async with database.get_logs_session() as session:
        query = sa.select(models.Log).where(models.Log.project_id == project_id)

        if filters.start_time:
            query = query.where(models.Log.timestamp >= filters.start_time)
        if filters.end_time:
            query = query.where(models.Log.timestamp <= filters.end_time)
        if filters.level:
            query = query.where(models.Log.level == filters.level)
        if filters.log_type:
            query = query.where(models.Log.log_type == filters.log_type)
        if filters.environment:
            query = query.where(models.Log.environment == filters.environment)
        if filters.error_fingerprint:
            query = query.where(
                models.Log.error_fingerprint == filters.error_fingerprint
            )

        query = query.order_by(models.Log.timestamp.desc())

        count_query = sa.select(sa.func.count()).select_from(query.subquery())
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.limit(pagination.limit).offset(pagination.offset)

        result = await session.execute(query)
        logs = result.scalars().all()

        has_more = (pagination.offset + len(logs)) < total

        return schemas.LogsQueryResponse(
            logs=[schemas.LogResponse.model_validate(log) for log in logs],
            total=total,
            has_more=has_more,
        )


async def search_logs(
    project_id: int,
    search_query: str,
    start_time: datetime.datetime | None,
    end_time: datetime.datetime | None,
    pagination: schemas.Pagination,
) -> schemas.LogsQueryResponse:
    async with database.get_logs_session() as session:
        query = sa.select(models.Log).where(models.Log.project_id == project_id)

        if start_time:
            query = query.where(models.Log.timestamp >= start_time)
        if end_time:
            query = query.where(models.Log.timestamp <= end_time)

        search_filter = sa.or_(
            models.Log.message.ilike(f"%{search_query}%"),
            models.Log.error_message.ilike(f"%{search_query}%"),
            models.Log.error_type.ilike(f"%{search_query}%"),
        )
        query = query.where(search_filter)

        query = query.order_by(models.Log.timestamp.desc())

        count_query = sa.select(sa.func.count()).select_from(query.subquery())
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.limit(pagination.limit).offset(pagination.offset)

        result = await session.execute(query)
        logs = result.scalars().all()

        has_more = (pagination.offset + len(logs)) < total

        return schemas.LogsQueryResponse(
            logs=[schemas.LogResponse.model_validate(log) for log in logs],
            total=total,
            has_more=has_more,
        )


async def get_log_by_id(
    log_id: int, project_id: int
) -> schemas.LogResponse | None:
    async with database.get_logs_session() as session:
        query = sa.select(models.Log).where(
            models.Log.id == log_id, models.Log.project_id == project_id
        )

        result = await session.execute(query)
        log = result.scalar_one_or_none()

        if log:
            return schemas.LogResponse.model_validate(log)
        return None


def _calculate_time_range_for_period(
    period: str | None,
) -> tuple[datetime.datetime, datetime.datetime]:
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == "today":
        start_time = today
        end_time = now
    elif period == "last7days":
        start_time = today - datetime.timedelta(days=7)
        end_time = now
    elif period == "last30days":
        start_time = today - datetime.timedelta(days=30)
        end_time = now
    elif period == "currentWeek":
        days_since_monday = today.weekday()
        start_time = today - datetime.timedelta(days=days_since_monday)
        end_time = now
    elif period == "currentMonth":
        start_time = today.replace(day=1)
        end_time = now
    elif period == "currentYear":
        start_time = today.replace(month=1, day=1)
        end_time = now
    else:
        start_time = today - datetime.timedelta(days=1)
        end_time = now

    return start_time, end_time


async def get_error_list(
    project_id: int,
    period: str | None = None,
    period_from: datetime.datetime | None = None,
    period_to: datetime.datetime | None = None,
    pagination: schemas.Pagination = schemas.Pagination(),
) -> schemas.ErrorListResponse:
    if period:
        start_time, end_time = _calculate_time_range_for_period(period)
    elif period_from and period_to:
        start_time = period_from
        end_time = period_to
    else:
        start_time, end_time = _calculate_time_range_for_period("today")

    async with database.get_logs_session() as session:
        query = (
            sa.select(
                models.Log.id.label("log_id"),
                models.Log.project_id,
                models.Log.level,
                models.Log.log_type,
                models.Log.message,
                models.Log.error_type,
                models.Log.timestamp,
                models.Log.error_fingerprint,
                models.Log.attributes,
                models.Log.sdk_version,
                models.Log.platform,
            )
            .where(
                models.Log.project_id == project_id,
                models.Log.timestamp >= start_time,
                models.Log.timestamp <= end_time,
                models.Log.level.in_(["error", "critical"]),
            )
            .order_by(models.Log.timestamp.desc())
        )

        count_query = sa.select(sa.func.count()).select_from(query.subquery())
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.limit(pagination.limit).offset(pagination.offset)

        result = await session.execute(query)
        rows = result.all()

        errors = []
        for row in rows:
            errors.append(
                schemas.ErrorListEntry(
                    log_id=row.log_id,
                    project_id=row.project_id,
                    level=row.level,
                    log_type=row.log_type,
                    message=row.message or "",
                    error_type=row.error_type,
                    timestamp=row.timestamp,
                    error_fingerprint=row.error_fingerprint,
                    attributes=row.attributes,
                    sdk_version=row.sdk_version,
                    platform=row.platform,
                )
            )

        has_more = (pagination.offset + len(errors)) < total

        return schemas.ErrorListResponse(
            project_id=project_id,
            errors=errors,
            total=total,
            has_more=has_more,
        )
