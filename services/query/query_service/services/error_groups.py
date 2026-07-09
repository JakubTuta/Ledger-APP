import datetime

import sqlalchemy as sa

import query_service.database as database
import query_service.models as models
import query_service.schemas as schemas

_VALID_STATUSES = frozenset({"unresolved", "resolved", "ignored", "muted"})


async def list_error_groups(
    project_id: int,
    status: str | None = None,
    pagination: schemas.Pagination = schemas.Pagination(),
) -> schemas.ErrorGroupListResponse:
    async with database.get_logs_session() as session:
        where_conditions = [models.ErrorGroup.project_id == project_id]
        if status:
            where_conditions.append(models.ErrorGroup.status == status)
        where = sa.and_(*where_conditions)

        count_result = await session.execute(
            sa.select(sa.func.count()).select_from(models.ErrorGroup).where(where)
        )
        total = count_result.scalar() or 0

        query = (
            sa.select(models.ErrorGroup)
            .where(where)
            .order_by(models.ErrorGroup.last_seen.desc())
            .limit(pagination.limit)
            .offset(pagination.offset)
        )
        result = await session.execute(query)
        groups = result.scalars().all()

        has_more = (pagination.offset + len(groups)) < total

        return schemas.ErrorGroupListResponse(
            project_id=project_id,
            groups=[schemas.ErrorGroupResponse.model_validate(g) for g in groups],
            total=total,
            has_more=has_more,
        )


async def get_error_group(
    project_id: int, group_id: int
) -> schemas.ErrorGroupDetailResponse | None:
    async with database.get_logs_session() as session:
        query = sa.select(models.ErrorGroup).where(
            models.ErrorGroup.id == group_id,
            models.ErrorGroup.project_id == project_id,
        )
        result = await session.execute(query)
        group = result.scalar_one_or_none()

        if group is None:
            return None

        sample_log = None
        if group.sample_log_id is not None:
            log_query = sa.select(models.Log).where(
                models.Log.id == group.sample_log_id,
                models.Log.project_id == project_id,
            )
            log_result = await session.execute(log_query)
            log = log_result.scalar_one_or_none()
            if log is not None:
                sample_log = schemas.LogResponse.model_validate(log)

        return schemas.ErrorGroupDetailResponse(
            group=schemas.ErrorGroupResponse.model_validate(group),
            sample_stack_trace=group.sample_stack_trace,
            sample_log=sample_log,
        )


async def update_error_group_status(
    project_id: int,
    group_id: int,
    new_status: str,
    resolved_in_release: str | None = None,
) -> schemas.ErrorGroupResponse | None:
    if new_status not in _VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{new_status}'. Must be one of: {', '.join(sorted(_VALID_STATUSES))}"
        )

    async with database.get_logs_session() as session:
        query = sa.select(models.ErrorGroup).where(
            models.ErrorGroup.id == group_id,
            models.ErrorGroup.project_id == project_id,
        )
        result = await session.execute(query)
        group = result.scalar_one_or_none()

        if group is None:
            return None

        now = datetime.datetime.now(datetime.timezone.utc)

        group.status = new_status
        if new_status == "resolved":
            group.resolved_at = now
            if resolved_in_release:
                group.resolved_in_release = resolved_in_release
        else:
            group.resolved_at = None

        await session.commit()
        await session.refresh(group)

        return schemas.ErrorGroupResponse.model_validate(group)


async def assign_error_group(
    project_id: int,
    group_id: int,
    assigned_to: int | None,
) -> schemas.ErrorGroupResponse | None:
    async with database.get_logs_session() as session:
        query = sa.select(models.ErrorGroup).where(
            models.ErrorGroup.id == group_id,
            models.ErrorGroup.project_id == project_id,
        )
        result = await session.execute(query)
        group = result.scalar_one_or_none()

        if group is None:
            return None

        group.assigned_to = assigned_to

        await session.commit()
        await session.refresh(group)

        return schemas.ErrorGroupResponse.model_validate(group)


async def get_error_occurrence_sparkline(
    project_id: int,
    group_id: int,
    hours: int = 24,
) -> schemas.ErrorOccurrenceSparklineResponse | None:
    async with database.get_logs_session() as session:
        group_query = sa.select(models.ErrorGroup.fingerprint).where(
            models.ErrorGroup.id == group_id,
            models.ErrorGroup.project_id == project_id,
        )
        group_result = await session.execute(group_query)
        fingerprint = group_result.scalar_one_or_none()

        if fingerprint is None:
            return None

        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)

        bucket_query = sa.text(
            """
            SELECT date_trunc('hour', timestamp) AS bucket, COUNT(*) AS count
            FROM logs
            WHERE project_id = :pid
              AND error_fingerprint = :fingerprint
              AND timestamp >= :since
            GROUP BY bucket
            ORDER BY bucket
            """
        )
        result = await session.execute(
            bucket_query,
            {"pid": project_id, "fingerprint": fingerprint, "since": since},
        )
        rows = result.fetchall()

        buckets = [
            schemas.ErrorOccurrenceBucket(bucket=row.bucket, count=row.count) for row in rows
        ]

        return schemas.ErrorOccurrenceSparklineResponse(
            project_id=project_id,
            fingerprint=fingerprint.strip(),
            hours=hours,
            buckets=buckets,
        )
