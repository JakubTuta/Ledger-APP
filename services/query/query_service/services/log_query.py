import base64
import collections
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


def _apply_log_dimension_filters(query: sa.Select, filters: schemas.LogFilters) -> sa.Select:
    """
    Apply every LogFilters where-clause except the time window, to a select()
    that already filters on project_id. Split out from _apply_log_filters() so
    the facet path can drive its own time bounds while keeping the dimension
    predicates identical to what the log table itself would show.
    """
    if filters.level:
        query = query.where(models.Log.level == filters.level)
    if filters.log_type:
        query = query.where(models.Log.log_type == filters.log_type)
    if filters.environment:
        query = query.where(models.Log.environment == filters.environment)
    if filters.error_fingerprint:
        query = query.where(models.Log.error_fingerprint == filters.error_fingerprint)
    if filters.client_channel:
        query = query.where(models.Log.client_channel.in_(filters.client_channel))
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
        # This OR spans columns with no per-column index, so no index can serve
        # it directly - it is evaluated as a filter on top of whatever the
        # project_id/timestamp predicates already narrowed the scan to. Keep
        # search requests time-bounded. (Trigram GIN indexes on message and
        # error_message were dropped in ingestion revision 015: a BitmapOr needs
        # every arm indexable, so they were never usable here, while costing on
        # every insert.)
        query = query.where(
            sa.or_(
                models.Log.method.ilike(term),
                models.Log.path.ilike(term),
                models.Log.message.ilike(term),
                models.Log.error_message.ilike(term),
            )
        )
    return query


def _apply_log_filters(query: sa.Select, filters: schemas.LogFilters) -> sa.Select:
    """
    Apply the shared LogFilters where-clauses to a select() that already
    filters on project_id.
    """
    if filters.start_time:
        query = query.where(models.Log.timestamp >= filters.start_time)
    if filters.end_time:
        query = query.where(models.Log.timestamp <= filters.end_time)
    return _apply_log_dimension_filters(query, filters)


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


_FACET_DIMENSIONS: tuple[tuple[str, sa.ColumnElement], ...] = (
    ("level", models.Log.level),
    ("log_type", models.Log.log_type),
    ("status_class", _STATUS_CLASS_EXPR),
    ("environment", models.Log.environment),
    ("client_channel", models.Log.client_channel),
)

_ROLLUP_FACET_DIMENSIONS: tuple[tuple[str, sa.ColumnElement], ...] = (
    ("level", models.log_facets_1h.c.level),
    ("log_type", models.log_facets_1h.c.log_type),
    ("status_class", models.log_facets_1h.c.status_class),
    ("environment", models.log_facets_1h.c.environment),
    ("client_channel", models.log_facets_1h.c.client_channel),
)

# log_facets_1h stores '' where the source column was NULL, so that the whole
# dimension tuple can be a primary key. Dropped on read, same as a raw NULL.
_ROLLUP_ABSENT = ""

# Must match analytics_workers.jobs.log_facets_1h._WINDOW_DAYS: how far back
# the rollup is kept fresh. No watermark table to check - the job recomputes
# this whole window every run, so trusting a fixed wall-clock boundary here is
# only wrong if the job itself has been down longer than _ROLLUP_SAFE_LAG.
_ROLLUP_WINDOW_DAYS = 32
# Trust the rollup only up to an hour behind wall-clock, giving the top-of-hour
# job run time to land before a request would otherwise read a stale bucket.
_ROLLUP_SAFE_LAG = datetime.timedelta(hours=1)

_FacetCounts = dict[str, collections.Counter]


def _empty_facet_counts() -> _FacetCounts:
    return {name: collections.Counter() for name, _ in _FACET_DIMENSIONS}


def _merge_facet_counts(into: _FacetCounts, other: _FacetCounts) -> None:
    for name, counter in other.items():
        into[name].update(counter)


def _collect_grouping_sets_rows(
    rows: list,
    dimensions: tuple[tuple[str, sa.ColumnElement], ...],
    absent: str | None,
) -> _FacetCounts:
    """
    Fan a GROUPING SETS result out into one counter per facet.

    Exactly one dimension is non-NULL per row - the one its grouping set
    grouped on. Rows whose grouped value is itself absent (a NULL source
    column, or its '' stand-in in the rollup) carry no facet value and are
    dropped.
    """
    counts = _empty_facet_counts()
    for row in rows:
        for index, (name, _) in enumerate(dimensions):
            value = row[index]
            if value is None or value == absent:
                continue
            counts[name][value] += row.count
            break
    return counts


async def _facets_from_logs(
    session: sa.ext.asyncio.AsyncSession,
    project_id: int,
    filters: schemas.LogFilters,
    start_time: datetime.datetime | None,
    end_time: datetime.datetime | None,
    end_inclusive: bool,
) -> _FacetCounts:
    """Facet counts straight off `logs`, for a window the rollup can't serve."""
    dimension_columns = [expression.label(f"dim_{name}") for name, expression in _FACET_DIMENSIONS]
    grouping_sets = sa.func.grouping_sets(
        *[sa.tuple_(expression) for _, expression in _FACET_DIMENSIONS]
    )

    query = sa.select(*dimension_columns, sa.func.count().label("count")).where(
        models.Log.project_id == project_id
    )
    query = _apply_log_dimension_filters(query, filters)
    if start_time:
        query = query.where(models.Log.timestamp >= start_time)
    if end_time:
        query = query.where(
            models.Log.timestamp <= end_time if end_inclusive else models.Log.timestamp < end_time
        )
    query = query.group_by(grouping_sets)

    result = await session.execute(query)
    return _collect_grouping_sets_rows(result.all(), _FACET_DIMENSIONS, None)


async def _facets_from_rollup(
    session: sa.ext.asyncio.AsyncSession,
    project_id: int,
    filters: schemas.LogFilters,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
) -> _FacetCounts:
    """
    Facet counts off the pre-aggregated log_facets_1h rollup, over a
    hour-aligned half-open [start_time, end_time) window.
    """
    facets = models.log_facets_1h.c
    dimension_columns = [
        expression.label(f"dim_{name}") for name, expression in _ROLLUP_FACET_DIMENSIONS
    ]
    grouping_sets = sa.func.grouping_sets(
        *[sa.tuple_(expression) for _, expression in _ROLLUP_FACET_DIMENSIONS]
    )

    # SUM() over a BIGINT comes back as numeric; cast so the counter stays int.
    total = sa.cast(sa.func.sum(facets["count"]), sa.BigInteger).label("count")

    query = sa.select(*dimension_columns, total).where(
        facets.project_id == project_id,
        facets.bucket >= start_time,
        facets.bucket < end_time,
    )
    if filters.level:
        query = query.where(facets.level == filters.level)
    if filters.log_type:
        query = query.where(facets.log_type == filters.log_type)
    if filters.environment:
        query = query.where(facets.environment == filters.environment)
    if filters.status_class:
        query = query.where(facets.status_class.in_(filters.status_class))
    if filters.client_channel:
        query = query.where(facets.client_channel.in_(filters.client_channel))
    query = query.group_by(grouping_sets)

    result = await session.execute(query)
    return _collect_grouping_sets_rows(result.all(), _ROLLUP_FACET_DIMENSIONS, _ROLLUP_ABSENT)


def _floor_hour(moment: datetime.datetime) -> datetime.datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def _ceil_hour(moment: datetime.datetime) -> datetime.datetime:
    floored = _floor_hour(moment)
    if floored == moment:
        return floored
    return floored + datetime.timedelta(hours=1)


def _split_facet_window(
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    now: datetime.datetime,
) -> tuple[
    list[tuple[datetime.datetime, datetime.datetime, bool]],
    tuple[datetime.datetime, datetime.datetime] | None,
]:
    """
    Decide which part of [start_time, end_time] the rollup can answer.

    Returns (raw_ranges, rollup_range). Each raw range is
    (start, end, end_inclusive); the rollup range is hour-aligned and
    half-open, bounded to the fixed trailing window the rollup job maintains
    (_ROLLUP_WINDOW_DAYS, up to _ROLLUP_SAFE_LAG behind `now`). Everything
    outside that - older history, and the partial hours at either edge -
    comes off `logs` directly.
    """
    whole_window_raw = ([(start_time, end_time, True)], None)

    rollup_floor = _floor_hour(now) - datetime.timedelta(days=_ROLLUP_WINDOW_DAYS)
    rollup_ceiling = _floor_hour(now) - _ROLLUP_SAFE_LAG

    rollup_start = max(_ceil_hour(start_time), rollup_floor)
    rollup_end = min(_floor_hour(end_time), rollup_ceiling)
    if rollup_end <= rollup_start:
        return whole_window_raw

    raw_ranges: list[tuple[datetime.datetime, datetime.datetime, bool]] = []
    if start_time < rollup_start:
        raw_ranges.append((start_time, rollup_start, False))
    if rollup_end < end_time:
        raw_ranges.append((rollup_end, end_time, True))

    return raw_ranges, (rollup_start, rollup_end)


def _rollup_can_serve(filters: schemas.LogFilters) -> bool:
    """
    log_facets_1h only carries the five facet dimensions. A free-text search
    or an error_fingerprint filter has to be evaluated against the log rows
    themselves, so those fall back to a full raw pass.
    """
    return not filters.search and not filters.error_fingerprint


async def get_log_facets(
    project_id: int,
    filters: schemas.LogFilters,
) -> schemas.LogFacetsResponse:
    """
    Aggregate counts per facet value (level, log_type, status_class,
    environment, client_channel) under the current filter set, using the same
    dimension predicates as query_logs() so facet counts always match what the
    log table itself would show.

    All facets come out of a single GROUPING SETS pass per source. The bulk of
    the window is answered from the hourly log_facets_1h rollup - counting
    every raw row instead put this past the gateway's 10s deadline at a few
    hundred thousand logs per window, since the facet dimensions live in no
    index and each row costs a heap fetch. Only the partial hours at the edges
    and anything outside the rollup's trailing window are read from `logs`.
    """
    async with database.get_logs_session() as session:
        counts = _empty_facet_counts()

        if filters.start_time and filters.end_time and _rollup_can_serve(filters):
            now = datetime.datetime.now(datetime.timezone.utc)
            raw_ranges, rollup_range = _split_facet_window(
                filters.start_time, filters.end_time, now
            )
        else:
            raw_ranges = [(filters.start_time, filters.end_time, True)]
            rollup_range = None

        if rollup_range:
            _merge_facet_counts(
                counts,
                await _facets_from_rollup(session, project_id, filters, *rollup_range),
            )

        for range_start, range_end, end_inclusive in raw_ranges:
            _merge_facet_counts(
                counts,
                await _facets_from_logs(
                    session, project_id, filters, range_start, range_end, end_inclusive
                ),
            )

        return schemas.LogFacetsResponse(
            project_id=project_id,
            **{
                name: [
                    schemas.LogFacetValue(value=value, count=count)
                    for value, count in counts[name].most_common()
                ]
                for name, _ in _FACET_DIMENSIONS
            },
        )


_DEFAULT_COUNTRY_BREAKDOWN_LIMIT = 50


async def get_country_breakdown(
    project_id: int,
    filters: schemas.LogFilters,
    limit: int = _DEFAULT_COUNTRY_BREAKDOWN_LIMIT,
) -> schemas.CountryBreakdownResponse:
    """
    Top-N country counts under the current filter set, for the request map.

    Deliberately not one of the GROUPING SETS facets in get_log_facets():
    country has ~250 possible values (vs. single digits for the other
    facets), which would both bloat that response and not fit a filter
    sidebar. This is its own query, capped with LIMIT, shaped as the
    (country, count) pairs a map needs directly.
    """
    async with database.get_logs_session() as session:
        query = sa.select(models.Log.client_country, sa.func.count().label("count")).where(
            models.Log.project_id == project_id, models.Log.client_country.is_not(None)
        )
        query = _apply_log_filters(query, filters)
        query = query.group_by(models.Log.client_country).order_by(sa.desc("count")).limit(limit)

        result = await session.execute(query)

        return schemas.CountryBreakdownResponse(
            project_id=project_id,
            countries=[
                schemas.CountryBreakdownEntry(country=row.client_country, count=row.count)
                for row in result.all()
            ],
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
    client_channel: list[str] | None = None,
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

        if client_channel:
            base_where_conditions.append(models.Log.client_channel.in_(client_channel))

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

        # `logs` is partitioned on timestamp and `id` alone is not part of the
        # partition key, so joining on id would probe every partition's primary
        # key. Repeating the caller's window (which every joined row satisfies
        # by construction - it came out of the same filtered set) and the
        # project scope lets the planner prune to the partitions in range.
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
            .join(
                latest_log,
                sa.and_(
                    latest_log.c.id == paged_groups.c.latest_log_id,
                    latest_log.c.project_id == project_id,
                    latest_log.c.timestamp >= start_time,
                    latest_log.c.timestamp <= end_time,
                ),
            )
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
