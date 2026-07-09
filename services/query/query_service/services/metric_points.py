import datetime

import sqlalchemy as sa

import query_service.database as database

_VALID_AGGREGATIONS = {"avg", "sum", "min", "max", "count"}

# Ranges longer than this read from the metric_points_1h rollup (cheap, one row
# per project/name/tag-set/hour) instead of scanning raw metric_points. Shorter
# / unbounded-recent windows read raw so very recent data (which the rollup
# job hasn't caught up to yet) is still visible.
_ROLLUP_THRESHOLD = datetime.timedelta(hours=6)


def _parse_iso(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


async def get_metric_series(project_id: int) -> list[dict]:
    sql = """
        SELECT name, MIN(type) AS type,
               COALESCE(array_agg(DISTINCT key) FILTER (WHERE key IS NOT NULL), ARRAY[]::text[]) AS tag_keys
        FROM metric_points_1h
        LEFT JOIN LATERAL jsonb_object_keys(tags) AS key ON true
        WHERE project_id = :project_id
        GROUP BY name
        ORDER BY name
        LIMIT 500
    """
    async with database.get_logs_session() as session:
        result = await session.execute(sa.text(sql), {"project_id": project_id})
        rows = result.fetchall()

    return [{"name": r.name, "type": r.type or 0, "tag_keys": list(r.tag_keys or [])} for r in rows]


async def query_metrics(
    project_id: int,
    name: str,
    tags: dict[str, str] | None,
    aggregation: str,
    from_time: str | None,
    to_time: str | None,
) -> list[dict]:
    aggregation = aggregation if aggregation in _VALID_AGGREGATIONS else "avg"

    from_dt = _parse_iso(from_time) if from_time else None
    to_dt = _parse_iso(to_time) if to_time else datetime.datetime.now(datetime.timezone.utc)

    use_rollup = bool(from_dt) and (to_dt - from_dt) >= _ROLLUP_THRESHOLD

    conditions = ["project_id = :project_id", "name = :name"]
    params: dict = {"project_id": project_id, "name": name}

    if from_dt:
        params["from_time"] = from_dt
    if to_dt:
        params["to_time"] = to_dt

    tags_condition = ""
    if tags:
        tags_condition = " AND tags @> CAST(:tags AS jsonb)"
        import json as _json

        params["tags"] = _json.dumps(tags)

    if use_rollup:
        agg_column = {
            "avg": "avg_v",
            "sum": "sum_v",
            "min": "min_v",
            "max": "max_v",
            "count": "count",
        }[aggregation]

        time_conditions = list(conditions)
        if from_dt:
            time_conditions.append("bucket >= :from_time")
        if to_dt:
            time_conditions.append("bucket <= :to_time")
        where = " AND ".join(time_conditions) + tags_condition

        sql = f"""
            SELECT bucket AS ts, {agg_column} AS value
            FROM metric_points_1h
            WHERE {where}
            ORDER BY bucket ASC
            LIMIT 5000
        """
    else:
        time_conditions = list(conditions)
        if from_dt:
            time_conditions.append("ts >= :from_time")
        if to_dt:
            time_conditions.append("ts <= :to_time")
        where = " AND ".join(time_conditions) + tags_condition

        agg_expr = {
            "avg": "AVG(effective_value)",
            "sum": "SUM(effective_value)",
            "min": "MIN(effective_value)",
            "max": "MAX(effective_value)",
            "count": "COUNT(*)",
        }[aggregation]

        sql = f"""
            SELECT date_trunc('minute', ts) AS ts, {agg_expr} AS value
            FROM (
                SELECT ts,
                       COALESCE(value, CASE WHEN type = 2 AND count > 0 THEN sum / count END) AS effective_value
                FROM metric_points
                WHERE {where}
            ) points
            GROUP BY date_trunc('minute', ts)
            ORDER BY 1 ASC
            LIMIT 5000
        """

    async with database.get_logs_session() as session:
        result = await session.execute(sa.text(sql), params)
        rows = result.fetchall()

    return [
        {
            "bucket": r.ts.isoformat() if hasattr(r.ts, "isoformat") else str(r.ts),
            "value": float(r.value) if r.value is not None else 0.0,
        }
        for r in rows
    ]
