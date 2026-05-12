import sqlalchemy as sa

import query_service.database as database


async def query_custom_metrics(
    project_id: int,
    name: str,
    tags: str,
    from_time: str | None,
    to_time: str | None,
    agg: str,
    step_seconds: int,
) -> list[dict]:
    agg_col = {
        "sum": "SUM(sum)",
        "avg": "SUM(sum) / NULLIF(SUM(count), 0)",
        "rate": "SUM(count)",
        "p95": "MAX(max_v)",
    }.get(agg, "SUM(sum)")

    step_interval = f"{step_seconds} seconds"
    conditions = [
        "project_id = :project_id",
        "name = :name",
    ]
    params: dict = {"project_id": project_id, "name": name, "step": step_interval}

    if from_time:
        conditions.append("bucket >= :from_time")
        params["from_time"] = from_time
    if to_time:
        conditions.append("bucket <= :to_time")
        params["to_time"] = to_time

    where = " AND ".join(conditions)
    sql = f"""
        SELECT date_trunc('second', bucket) - (
            EXTRACT(EPOCH FROM bucket)::int % :step::int * interval '1 second'
        ) AS rounded_bucket,
        {agg_col} AS value
        FROM custom_metrics_5m
        WHERE {where}
        GROUP BY rounded_bucket
        ORDER BY rounded_bucket ASC
        LIMIT 1000
    """

    async with database.get_logs_session() as session:
        result = await session.execute(sa.text(sql), params)
        rows = result.fetchall()

    return [
        {"bucket": r.rounded_bucket.isoformat(), "value": float(r.value or 0)}
        for r in rows
    ]


async def list_metric_names(project_id: int, prefix: str | None) -> list[str]:
    conditions = ["project_id = :project_id"]
    params: dict = {"project_id": project_id}
    if prefix:
        conditions.append("name LIKE :prefix")
        params["prefix"] = f"{prefix}%"

    where = " AND ".join(conditions)
    sql = f"SELECT DISTINCT name FROM custom_metrics_5m WHERE {where} ORDER BY name LIMIT 500"

    async with database.get_logs_session() as session:
        result = await session.execute(sa.text(sql), params)
        return [r.name for r in result.fetchall()]


async def list_metric_tags(project_id: int, name: str) -> list[dict]:
    sql = """
        SELECT DISTINCT jsonb_object_keys(tags::jsonb) AS key
        FROM custom_metrics_5m
        WHERE project_id = :project_id AND name = :name
        LIMIT 100
    """
    async with database.get_logs_session() as session:
        result = await session.execute(
            sa.text(sql), {"project_id": project_id, "name": name}
        )
        keys = [r.key for r in result.fetchall()]

        tag_entries = []
        for key in keys:
            val_sql = """
                SELECT DISTINCT tags::jsonb ->> :key AS value
                FROM custom_metrics_5m
                WHERE project_id = :project_id AND name = :name
                  AND tags::jsonb ? :key
                LIMIT 100
            """
            val_result = await session.execute(
                sa.text(val_sql),
                {"project_id": project_id, "name": name, "key": key},
            )
            values = [r.value for r in val_result.fetchall() if r.value is not None]
            tag_entries.append({"key": key, "values": values})

    return tag_entries
