"""Signals joined across logs and spans.

- a trace's logs (trace -> logs; logs -> trace is the trace_id the log carries)
- the service dependency graph, from parent/child spans in different services
- RED metrics (rate, errors, duration) per service or per operation of one
  service, from entry spans
"""

import datetime

import sqlalchemy as sa

import query_service.database as database
import query_service.models as models
import query_service.schemas as schemas
import query_service.services.log_resources as log_resources

# Internal SpanKind values (proto/ingestion.proto).
_KIND_SERVER = 0
_KIND_CLIENT = 1
_KIND_PRODUCER = 3
_KIND_CONSUMER = 4
_STATUS_ERROR = 2

# A request's entry into a service: a server/consumer span, or a trace root
# (a cron job or a script has no server span).
_ENTRY_SPAN_PREDICATE = f"(kind IN ({_KIND_SERVER}, {_KIND_CONSUMER}) OR parent_span_id IS NULL)"

# A log's timestamp is when it was emitted, inside its span; the margin only
# absorbs clock skew between the hosts of one trace. Every row in the window
# is scanned, so it is kept tight (measured: 5 minutes made one lookup scan
# ~10x the rows for no extra matches).
_TRACE_LOG_WINDOW_MARGIN = datetime.timedelta(seconds=30)
# A trace that was sampled out has no spans to take a window from.
_UNSTORED_TRACE_WINDOW = datetime.timedelta(days=1)
DEFAULT_TRACE_LOG_LIMIT = 500
MAX_TRACE_LOG_LIMIT = 2000

_DEFAULT_WINDOW = datetime.timedelta(hours=1)
# Both span aggregations scan every span in the window; a week is the widest
# window the dashboard offers for them.
MAX_WINDOW = datetime.timedelta(days=7)

_INTERVAL_SECONDS = {"1m": 60, "5m": 300, "1h": 3600, "1d": 86400}

# An uninstrumented dependency (database, third-party API) shows up only as
# the client span calling it; these attributes name it, most specific first.
_DEPENDENCY_NAME_KEYS = ("peer.service", "db.system", "messaging.system", "server.address")


def resolve_window(
    from_time: str | None, to_time: str | None
) -> tuple[datetime.datetime, datetime.datetime]:
    end = _parse_iso(to_time) if to_time else datetime.datetime.now(datetime.timezone.utc)
    start = _parse_iso(from_time) if from_time else end - _DEFAULT_WINDOW
    if start >= end:
        raise ValueError("from_time must be before to_time")
    if end - start > MAX_WINDOW:
        raise ValueError(f"Window too wide: at most {MAX_WINDOW.days} days")
    return start, end


def _parse_iso(value: str) -> datetime.datetime:
    parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


async def _trace_window(
    session, project_id: int, trace_id: str
) -> tuple[datetime.datetime, datetime.datetime] | None:
    row = (
        await session.execute(
            sa.text(
                """
                SELECT MIN(start_time) AS first_start,
                       MAX(start_time + duration_ns * INTERVAL '1 microsecond' / 1000) AS last_end
                FROM spans
                WHERE project_id = :project_id AND trace_id = :trace_id
                """
            ),
            {"project_id": project_id, "trace_id": trace_id},
        )
    ).one()
    if row.first_start is None:
        return None
    return row.first_start, row.last_end


async def get_trace_logs(
    project_id: int, trace_id: str, span_id: str | None, limit: int
) -> tuple[list[schemas.LogResponse], bool]:
    """Logs emitted inside a trace (or one of its spans), oldest first.

    Bounded to the trace's own time window, so it is an index range scan of the
    project's logs in that window rather than a search of all history. Rows
    stored before logs revision 024 carry the ids inside `attributes`.
    """
    async with database.get_logs_session() as session:
        window = await _trace_window(session, project_id, trace_id)
        if window is None:
            end = datetime.datetime.now(datetime.timezone.utc)
            window = (end - _UNSTORED_TRACE_WINDOW, end)
        start, end = window[0] - _TRACE_LOG_WINDOW_MARGIN, window[1] + _TRACE_LOG_WINDOW_MARGIN

        query = sa.select(models.Log).where(
            models.Log.project_id == project_id,
            models.Log.timestamp >= start,
            models.Log.timestamp <= end,
            _id_matches(models.Log.trace_id, "trace_id", trace_id),
        )
        if span_id:
            query = query.where(_id_matches(models.Log.span_id, "span_id", span_id))
        query = query.order_by(models.Log.timestamp, models.Log.id).limit(limit + 1)

        logs = (await session.execute(query)).scalars().all()
        truncated = len(logs) > limit
        return await log_resources.log_responses(session, project_id, logs[:limit]), truncated


def _id_matches(column, legacy_key: str, value: str) -> sa.ColumnElement[bool]:
    """Rows stored before logs revision 024 (no resource_hash) kept the id in
    the JSONB; newer rows without a trace context must not be detoasted."""
    return sa.or_(
        column == value,
        sa.and_(
            column.is_(None),
            models.Log.resource_hash.is_(None),
            models.Log.attributes[legacy_key].astext == value,
        ),
    )


async def get_service_map(
    project_id: int, start: datetime.datetime, end: datetime.datetime
) -> dict:
    """Services and the calls between them in a window.

    An edge is a span whose parent span belongs to a different service (the
    usual client span -> server span hop), or a client/producer span with no
    child at all, which is a call into something uninstrumented that the span's
    attributes name (a database, a third-party API). Rows with an empty caller
    are the requests entering a service, i.e. its node.

    The raw graph is a self-join of every span in the window, so windows wider
    than _RAW_SERVICE_MAP_MAX_WINDOW read the service_edges_1h rollup instead;
    there p95 is the highest hourly p95 rather than the window's.
    """
    downsampled = end - start > _RAW_SERVICE_MAP_MAX_WINDOW
    params = {"project_id": project_id, "start": start, "end": end}
    async with database.get_logs_session() as session:
        rows = (
            await session.execute(
                _SERVICE_GRAPH_FROM_ROLLUP if downsampled else _SERVICE_GRAPH_FROM_SPANS,
                params,
            )
        ).all()

    node_list = [_node(r.callee, r.calls, r.errors, r.p95_ms) for r in rows if r.caller == ""]
    edges = [_edge(row) for row in rows if row.caller != ""]
    known = {node["service"] for node in node_list}
    # Dependencies and services seen only as callees still get a node.
    for edge in edges:
        for name in (edge["caller"], edge["callee"]):
            if name not in known:
                known.add(name)
                node_list.append(_node(name, 0, 0, 0.0))

    return {
        "nodes": node_list,
        "edges": edges,
        "from_time": start,
        "to_time": end,
        "downsampled": downsampled,
    }


# Measured on 0.5 CPU: ~0.3 s for 1 h of a busy project, 3-6 s for 24 h
# (430k spans); the rollup answers any window in milliseconds.
_RAW_SERVICE_MAP_MAX_WINDOW = datetime.timedelta(hours=3)

# One scan of the window's spans, materialized once and joined against itself.
# Mirrors analytics_workers/jobs/service_edges_1h_rollup.py, which builds the
# rollup with the same rules.
_SERVICE_GRAPH_FROM_SPANS = sa.text(
    f"""
    WITH window_spans AS MATERIALIZED (
        SELECT span_id, trace_id, parent_span_id, service_name, kind,
               start_time, duration_ns, status_code,
               CASE WHEN kind IN ({_KIND_CLIENT}, {_KIND_PRODUCER}) THEN COALESCE(
                   {", ".join(f"attributes->>'{key}'" for key in _DEPENDENCY_NAME_KEYS)}
               ) END AS dependency
        FROM spans
        WHERE project_id = :project_id
          -- a parent can start shortly before the window its child falls in
          AND start_time >= CAST(:start AS timestamptz) - INTERVAL '5 minutes'
          AND start_time <= :end
    ),
    edges AS (
        SELECT start_time, '' AS caller, service_name AS callee, duration_ns, status_code
        FROM window_spans
        WHERE {_ENTRY_SPAN_PREDICATE}
        UNION ALL
        SELECT child.start_time, parent.service_name, child.service_name,
               child.duration_ns, child.status_code
        FROM window_spans child
        JOIN window_spans parent
          ON parent.trace_id = child.trace_id AND parent.span_id = child.parent_span_id
        WHERE parent.service_name <> child.service_name
        UNION ALL
        SELECT c.start_time, c.service_name, c.dependency, c.duration_ns, c.status_code
        FROM window_spans c
        WHERE c.dependency IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM window_spans child
              WHERE child.trace_id = c.trace_id AND child.parent_span_id = c.span_id
          )
    )
    SELECT caller, callee,
           COUNT(*) AS calls,
           COUNT(*) FILTER (WHERE status_code = {_STATUS_ERROR}) AS errors,
           PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ns) / 1e6 AS p95_ms
    FROM edges
    WHERE start_time >= :start
    GROUP BY caller, callee
    """
)

_SERVICE_GRAPH_FROM_ROLLUP = sa.text(
    """
    SELECT caller, callee,
           SUM(calls)::bigint AS calls,
           SUM(errors)::bigint AS errors,
           MAX(p95_ns) / 1e6 AS p95_ms
    FROM service_edges_1h
    WHERE project_id = :project_id
      AND bucket >= date_trunc('hour', CAST(:start AS timestamptz))
      AND bucket <= :end
    GROUP BY caller, callee
    """
)


def _node(service: str, calls: int, errors: int, p95_ms: float | None) -> dict:
    return {"service": service, "calls": calls, "errors": errors, "p95_ms": float(p95_ms or 0.0)}


def _edge(row) -> dict:
    return {
        "caller": row.caller,
        "callee": row.callee,
        "calls": row.calls,
        "errors": row.errors,
        "p95_ms": float(row.p95_ms or 0.0),
    }


def resolve_interval(
    start: datetime.datetime, end: datetime.datetime, requested: str | None
) -> str:
    if requested in _INTERVAL_SECONDS:
        return requested
    span = end - start
    if span <= datetime.timedelta(hours=2):
        return "1m"
    if span <= datetime.timedelta(hours=12):
        return "5m"
    if span <= datetime.timedelta(days=3):
        return "1h"
    return "1d"


def _bucket_expression(interval: str) -> str:
    seconds = _INTERVAL_SECONDS[interval]
    if seconds >= 3600:
        unit = "hour" if seconds == 3600 else "day"
        return f"date_trunc('{unit}', start_time)"
    return f"to_timestamp(floor(extract(epoch from start_time) / {seconds}) * {seconds})"


async def get_service_red(
    project_id: int,
    service: str | None,
    start: datetime.datetime,
    end: datetime.datetime,
    interval: str,
) -> list[dict]:
    """Rate, errors and duration of entry spans, per service - or, for one
    service, per operation (span name)."""
    params: dict = {"project_id": project_id, "start": start, "end": end}
    group_columns = "service_name"
    operation_select = "''"
    service_predicate = ""
    if service:
        params["service"] = service
        service_predicate = "AND service_name = :service"
        group_columns = "service_name, name"
        operation_select = "name"

    base = f"""
        FROM spans
        WHERE project_id = :project_id
          AND start_time >= :start AND start_time <= :end
          AND {_ENTRY_SPAN_PREDICATE}
          {service_predicate}
    """
    aggregates = f"""
        COUNT(*) AS calls,
        COUNT(*) FILTER (WHERE status_code = {_STATUS_ERROR}) AS errors,
        PERCENTILE_CONT(ARRAY[0.5, 0.95, 0.99]) WITHIN GROUP (ORDER BY duration_ns) AS pcts
    """
    bucket = _bucket_expression(interval)

    async with database.get_logs_session() as session:
        bucket_rows = (
            await session.execute(
                sa.text(
                    f"""
                    SELECT {bucket} AS bucket, service_name AS service,
                           {operation_select} AS operation, {aggregates}
                    {base}
                    GROUP BY {bucket}, {group_columns}
                    ORDER BY bucket
                    """
                ),
                params,
            )
        ).all()
        total_rows = (
            await session.execute(
                sa.text(
                    f"""
                    SELECT service_name AS service, {operation_select} AS operation,
                           {aggregates}
                    {base}
                    GROUP BY {group_columns}
                    """
                ),
                params,
            )
        ).all()

    series: dict[tuple[str, str], dict] = {}
    for row in total_rows:
        series[(row.service, row.operation)] = {
            "service": row.service,
            "operation": row.operation,
            "points": [],
            "calls": row.calls,
            "errors": row.errors,
            "p95_ms": _ms(row.pcts, 1),
        }
    for row in bucket_rows:
        entry = series.get((row.service, row.operation))
        if entry is None:
            continue
        entry["points"].append(
            {
                "bucket": row.bucket,
                "calls": row.calls,
                "errors": row.errors,
                "p50_ms": _ms(row.pcts, 0),
                "p95_ms": _ms(row.pcts, 1),
                "p99_ms": _ms(row.pcts, 2),
            }
        )
    return sorted(series.values(), key=lambda s: s["calls"], reverse=True)


def _ms(percentiles: list | None, index: int) -> float:
    if not percentiles or percentiles[index] is None:
        return 0.0
    return float(percentiles[index]) / 1e6
