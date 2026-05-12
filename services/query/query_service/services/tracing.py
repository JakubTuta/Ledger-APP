import json

import sqlalchemy as sa

import query_service.database as database


async def get_trace(project_id: int, trace_id: str) -> dict | None:
    async with database.get_logs_session() as session:
        result = await session.execute(
            sa.text("""
                SELECT span_id, trace_id, parent_span_id, project_id, service_name,
                       name, kind, start_time, duration_ns, status_code, status_message,
                       attributes, events, error_fingerprint
                FROM spans
                WHERE trace_id = :trace_id AND project_id = :project_id
                ORDER BY start_time ASC
            """),
            {"trace_id": trace_id, "project_id": project_id},
        )
        rows = result.fetchall()
        if not rows:
            return None

        spans = [_row_to_span_dict(r) for r in rows]
        services = list({s["service_name"] for s in spans})
        root = next(
            (s for s in spans if not s["parent_span_id"]),
            spans[0],
        )
        total_duration_ms = max(
            (s["duration_ns"] for s in spans), default=0
        ) // 1_000_000

        return {
            "trace_id": trace_id,
            "spans": spans,
            "duration_ms": total_duration_ms,
            "services": services,
            "root_span_id": root["span_id"],
        }


async def list_traces(
    project_id: int,
    service: str | None,
    name: str | None,
    min_duration_ms: int | None,
    has_error: bool | None,
    from_time: str | None,
    to_time: str | None,
    limit: int,
    offset: int,
) -> dict:
    conditions = ["project_id = :project_id"]
    params: dict = {"project_id": project_id}

    if service:
        conditions.append("service_name = :service")
        params["service"] = service
    if name:
        conditions.append("name ILIKE :name")
        params["name"] = f"%{name}%"
    if min_duration_ms is not None:
        conditions.append("duration_ns >= :min_dur")
        params["min_dur"] = min_duration_ms * 1_000_000
    if has_error is True:
        conditions.append("status_code = 2")
    elif has_error is False:
        conditions.append("status_code != 2")
    if from_time:
        conditions.append("start_time >= :from_time")
        params["from_time"] = from_time
    if to_time:
        conditions.append("start_time <= :to_time")
        params["to_time"] = to_time

    where = " AND ".join(conditions)
    count_sql = f"SELECT COUNT(*) FROM spans WHERE parent_span_id IS NULL AND {where}"
    data_sql = f"""
        SELECT span_id, trace_id, name, service_name, start_time,
               duration_ns, status_code,
               (SELECT COUNT(*) FROM spans s2 WHERE s2.trace_id = spans.trace_id
                AND s2.project_id = spans.project_id) AS span_count
        FROM spans
        WHERE parent_span_id IS NULL AND {where}
        ORDER BY start_time DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = limit + 1
    params["offset"] = offset

    async with database.get_logs_session() as session:
        total_result = await session.execute(sa.text(count_sql), params)
        total = total_result.scalar() or 0

        data_result = await session.execute(sa.text(data_sql), params)
        rows = data_result.fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]

    traces = [
        {
            "trace_id": r.trace_id,
            "root_span_id": r.span_id,
            "root_name": r.name,
            "service_name": r.service_name,
            "start_time": r.start_time.isoformat(),
            "duration_ms": (r.duration_ns or 0) // 1_000_000,
            "span_count": r.span_count,
            "has_error": r.status_code == 2,
        }
        for r in rows
    ]

    return {"traces": traces, "total": total, "has_more": has_more}


async def get_span_latency(
    project_id: int,
    service: str | None,
    name: str | None,
    from_time: str | None,
    to_time: str | None,
) -> list[dict]:
    conditions = ["project_id = :project_id"]
    params: dict = {"project_id": project_id}

    if service:
        conditions.append("service_name = :service")
        params["service"] = service
    if name:
        conditions.append("name = :name")
        params["name"] = name
    if from_time:
        conditions.append("bucket >= :from_time")
        params["from_time"] = from_time
    if to_time:
        conditions.append("bucket <= :to_time")
        params["to_time"] = to_time

    where = " AND ".join(conditions)
    sql = f"""
        SELECT service_name, name, bucket::text AS bucket,
               calls, p50_ns, p95_ns, p99_ns, errors
        FROM span_latency_1h
        WHERE {where}
        ORDER BY bucket DESC
        LIMIT 500
    """

    async with database.get_logs_session() as session:
        result = await session.execute(sa.text(sql), params)
        rows = result.fetchall()

    return [
        {
            "service_name": r.service_name,
            "name": r.name,
            "bucket": r.bucket,
            "calls": r.calls,
            "p50_ns": r.p50_ns,
            "p95_ns": r.p95_ns,
            "p99_ns": r.p99_ns,
            "errors": r.errors,
        }
        for r in rows
    ]


def _row_to_span_dict(row) -> dict:
    return {
        "span_id": row.span_id,
        "trace_id": row.trace_id,
        "parent_span_id": row.parent_span_id or "",
        "project_id": row.project_id,
        "service_name": row.service_name,
        "name": row.name,
        "kind": row.kind,
        "start_time": row.start_time.isoformat(),
        "duration_ns": row.duration_ns,
        "status_code": row.status_code,
        "status_message": row.status_message or "",
        "attributes": row.attributes or "{}",
        "events": row.events or "[]",
        "error_fingerprint": row.error_fingerprint or "",
    }
