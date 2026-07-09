import base64
import datetime

import sqlalchemy as sa

import query_service.database as database
import query_service.models as models
import query_service.schemas as schemas


def _encode_cursor(timestamp: datetime.datetime, log_id: int) -> str:
    raw = f"{timestamp.isoformat()}|{log_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime.datetime, int]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts_str, id_str = raw.rsplit("|", 1)
    return datetime.datetime.fromisoformat(ts_str), int(id_str)


def _apply_log_filters(query: sa.Select, filters: schemas.LogFilters) -> sa.Select:
    """
    Apply the shared LogFilters where-clauses to a select() that already
    filters on project_id. Used by query_logs() and get_log_facets() so both
    stay in sync.
    """
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
        query = query.where(models.Log.error_fingerprint == filters.error_fingerprint)
    if filters.status_class:
        status_conditions = []
        for sc in filters.status_class:
            if sc == "2xx":
                status_conditions.append(models.Log.status_code.between(200, 299))
            elif sc == "4xx":
                status_conditions.append(models.Log.status_code.between(400, 499))
            elif sc == "5xx":
                status_conditions.append(models.Log.status_code.between(500, 599))
        if status_conditions:
            query = query.where(sa.or_(*status_conditions))
    if filters.search:
        term = f"%{filters.search}%"
        # Message/error_message are backed by GIN trigram indexes
        # (ix_logs_message_trgm / ix_logs_error_message_trgm), so this ILIKE
        # substring search stays index-assisted even at scale.
        query = query.where(
            sa.or_(
                models.Log.method.ilike(term),
                models.Log.path.ilike(term),
                models.Log.message.ilike(term),
                models.Log.error_message.ilike(term),
            )
        )
    return query


async def query_logs(
    project_id: int,
    filters: schemas.LogFilters,
    pagination: schemas.Pagination,
) -> schemas.LogsQueryResponse:
    async with database.get_logs_session() as session:
        query = sa.select(models.Log).where(models.Log.project_id == project_id)
        query = _apply_log_filters(query, filters)

        # Keyset (cursor) pagination takes precedence over offset: offset
        # pagination degrades on deep pages (the DB still has to walk/skip all
        # prior rows), and duplicate timestamps make plain OFFSET unstable
        # across pages. The cursor is opaque to the caller - it just echoes
        # back next_cursor from the previous response.
        if pagination.cursor:
            cursor_ts, cursor_id = _decode_cursor(pagination.cursor)
            query = query.where(
                sa.tuple_(models.Log.timestamp, models.Log.id) < (cursor_ts, cursor_id)
            )

        query = query.order_by(models.Log.timestamp.desc(), models.Log.id.desc())
        query = query.limit(pagination.limit + 1)
        if not pagination.cursor:
            query = query.offset(pagination.offset)

        result = await session.execute(query)
        logs = result.scalars().all()

        has_more = len(logs) > pagination.limit
        if has_more:
            logs = logs[: pagination.limit]

        next_cursor = None
        if has_more and logs:
            last = logs[-1]
            next_cursor = _encode_cursor(last.timestamp, last.id)

        return schemas.LogsQueryResponse(
            logs=[schemas.LogResponse.model_validate(log) for log in logs],
            total=None,
            has_more=has_more,
            next_cursor=next_cursor,
        )


_STATUS_CLASS_EXPR = sa.case(
    (models.Log.status_code.between(200, 299), sa.literal("2xx")),
    (models.Log.status_code.between(300, 399), sa.literal("3xx")),
    (models.Log.status_code.between(400, 499), sa.literal("4xx")),
    (models.Log.status_code.between(500, 599), sa.literal("5xx")),
    else_=sa.null(),
)


async def get_log_facets(
    project_id: int,
    filters: schemas.LogFilters,
) -> schemas.LogFacetsResponse:
    """
    Aggregate counts per facet value (level, log_type, status_class,
    environment) under the current filter set. Reuses the same
    _apply_log_filters() where-clauses as query_logs() so facet counts always
    match what the log table itself would show.
    """
    async with database.get_logs_session() as session:

        def _facet_query(column: sa.ColumnElement, label: str) -> sa.Select:
            value_col = column.label("value")
            count_col = sa.func.count().label("count")
            q = sa.select(value_col, count_col).where(models.Log.project_id == project_id)
            q = _apply_log_filters(q, filters)
            return q.group_by(value_col).order_by(count_col.desc())

        def _rows_to_values(rows) -> list[schemas.LogFacetValue]:
            return [
                schemas.LogFacetValue(value=row.value, count=row.count)
                for row in rows
                if row.value is not None
            ]

        level_result = await session.execute(_facet_query(models.Log.level, "level"))
        log_type_result = await session.execute(_facet_query(models.Log.log_type, "log_type"))
        environment_result = await session.execute(
            _facet_query(models.Log.environment, "environment")
        )
        status_class_query = sa.select(
            _STATUS_CLASS_EXPR.label("value"), sa.func.count().label("count")
        ).where(
            models.Log.project_id == project_id,
            models.Log.status_code.isnot(None),
        )
        status_class_query = _apply_log_filters(status_class_query, filters)
        status_class_query = status_class_query.group_by(_STATUS_CLASS_EXPR).order_by(
            sa.func.count().desc()
        )
        status_class_result = await session.execute(status_class_query)

        return schemas.LogFacetsResponse(
            project_id=project_id,
            level=_rows_to_values(level_result.all()),
            log_type=_rows_to_values(log_type_result.all()),
            status_class=_rows_to_values(status_class_result.all()),
            environment=_rows_to_values(environment_result.all()),
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
        query = query.limit(pagination.limit + 1).offset(pagination.offset)

        result = await session.execute(query)
        logs = result.scalars().all()

        has_more = len(logs) > pagination.limit
        if has_more:
            logs = logs[: pagination.limit]

        return schemas.LogsQueryResponse(
            logs=[schemas.LogResponse.model_validate(log) for log in logs],
            total=None,
            has_more=has_more,
        )


async def get_log_by_id(log_id: int, project_id: int) -> schemas.LogResponse | None:
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
    search: str | None = None,
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
        # Build group_key expression: fingerprint or hash(error_type|message)
        group_key_col = sa.func.coalesce(
            models.Log.error_fingerprint,
            sa.func.md5(
                sa.func.coalesce(models.Log.error_type, sa.literal(""))
                + sa.literal("|")
                + sa.func.coalesce(models.Log.message, sa.literal(""))
            ),
        )

        base_where_conditions = [
            models.Log.project_id == project_id,
            models.Log.timestamp >= start_time,
            models.Log.timestamp <= end_time,
            sa.or_(
                models.Log.level.in_(["error", "critical"]),
                models.Log.status_code >= 400,
            ),
        ]

        if search:
            term = f"%{search}%"
            base_where_conditions.append(
                sa.or_(
                    models.Log.path.ilike(term),
                    models.Log.message.ilike(term),
                )
            )

        base_where = sa.and_(*base_where_conditions)

        # Step 1: group aggregation — count, first/last seen, latest id per group
        groups_subq = (
            sa.select(
                group_key_col.label("group_key"),
                sa.func.count().label("occurrence_count"),
                sa.func.min(models.Log.timestamp).label("first_seen"),
                sa.func.max(models.Log.timestamp).label("last_seen"),
                sa.func.max(models.Log.id).label("latest_log_id"),
                models.Log.project_id.label("project_id"),
            )
            .where(base_where)
            .group_by(group_key_col, models.Log.project_id)
            .subquery("groups")
        )

        # Total distinct groups
        count_result = await session.execute(sa.select(sa.func.count()).select_from(groups_subq))
        total = count_result.scalar() or 0

        # Step 2: paginate groups, then join latest row to get sample fields
        paged_groups = (
            sa.select(groups_subq)
            .order_by(groups_subq.c.last_seen.desc())
            .limit(pagination.limit)
            .offset(pagination.offset)
            .subquery("paged_groups")
        )

        latest_log = models.Log.__table__.alias("latest_log")

        final_query = (
            sa.select(
                paged_groups.c.group_key,
                paged_groups.c.occurrence_count,
                paged_groups.c.first_seen,
                paged_groups.c.last_seen,
                paged_groups.c.latest_log_id,
                paged_groups.c.project_id,
                latest_log.c.message,
                latest_log.c.error_type,
                latest_log.c.path,
                latest_log.c.status_code,
                latest_log.c.level,
                latest_log.c.log_type,
                latest_log.c.error_fingerprint,
                latest_log.c.attributes,
                latest_log.c.stack_trace,
                latest_log.c.sdk_version,
                latest_log.c.platform,
            )
            .join(latest_log, latest_log.c.id == paged_groups.c.latest_log_id)
            .order_by(paged_groups.c.last_seen.desc())
        )

        result = await session.execute(final_query)
        rows = result.all()

        errors = []
        for row in rows:
            attributes = row.attributes if isinstance(row.attributes, dict) else None

            errors.append(
                schemas.ErrorListEntry(
                    log_id=row.latest_log_id,
                    project_id=row.project_id,
                    level=row.level or "error",
                    log_type=row.log_type or "exception",
                    message=row.message or "",
                    error_type=row.error_type,
                    timestamp=row.last_seen,
                    error_fingerprint=row.error_fingerprint,
                    attributes=attributes,
                    sdk_version=row.sdk_version,
                    platform=row.platform,
                    group_key=row.group_key,
                    occurrence_count=row.occurrence_count,
                    first_seen=row.first_seen,
                    last_seen=row.last_seen,
                    status_code=row.status_code,
                    path=row.path,
                    stack_trace=row.stack_trace,
                    latest_log_id=row.latest_log_id,
                )
            )

        has_more = (pagination.offset + len(errors)) < total

        return schemas.ErrorListResponse(
            project_id=project_id,
            errors=errors,
            total=total,
            has_more=has_more,
        )
