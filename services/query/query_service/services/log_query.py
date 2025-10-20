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
