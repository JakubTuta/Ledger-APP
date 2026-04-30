import datetime
import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.bottleneck_metrics")


async def aggregate_bottleneck_metrics() -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    current_hour_start = now.replace(minute=0, second=0, microsecond=0)
    previous_hour_start = current_hour_start - datetime.timedelta(hours=1)
    previous_hour_end = current_hour_start

    date_str = previous_hour_start.strftime("%Y%m%d")
    hour = previous_hour_start.hour

    start = time.perf_counter()
    logger.info(
        f"Starting bottleneck metrics aggregation for {date_str} hour {hour} "
        f"({previous_hour_start} to {previous_hour_end})"
    )

    try:
        project_routes = await _get_all_project_routes()
        if not project_routes:
            logger.info("No projects with available routes configured")
            return

        route_metrics = await _get_all_route_metrics(previous_hour_start, previous_hour_end)

        await _batch_upsert_bottleneck_metrics(
            project_routes, route_metrics, date_str, hour
        )

        elapsed = time.perf_counter() - start
        logger.info(
            f"Bottleneck metrics done in {elapsed:.2f}s for {len(project_routes)} projects"
        )

    except Exception as e:
        logger.error(f"Bottleneck metrics aggregation failed: {e}", exc_info=True)
        raise


async def _get_all_project_routes() -> dict[int, list[str]]:
    async with database.get_auth_session() as session:
        query = sa.text(
            """
            SELECT id, available_routes
            FROM projects
            WHERE available_routes IS NOT NULL
        """
        )
        result = await session.execute(query)
        rows = result.fetchall()
        return {row[0]: row[1] for row in rows if row[1]}


async def _get_all_route_metrics(
    start_time: datetime.datetime, end_time: datetime.datetime
) -> dict[int, dict[str, dict]]:
    async with database.get_logs_session() as session:
        query = sa.text(
            """
            WITH endpoint_data AS (
                SELECT
                    project_id,
                    ((attributes->'endpoint'->>'method') || ' ' || (attributes->'endpoint'->>'path'))::VARCHAR AS route,
                    (attributes->'endpoint'->>'duration_ms')::FLOAT AS duration_ms
                FROM logs
                WHERE
                    log_type = 'endpoint'
                    AND timestamp >= :start_time
                    AND timestamp < :end_time
                    AND attributes->'endpoint'->>'path' IS NOT NULL
                    AND attributes->'endpoint'->>'method' IS NOT NULL
                    AND attributes->'endpoint'->>'duration_ms' IS NOT NULL
            )
            SELECT
                project_id,
                route,
                COUNT(*) AS log_count,
                ROUND(MIN(duration_ms))::INTEGER AS min_duration_ms,
                ROUND(MAX(duration_ms))::INTEGER AS max_duration_ms,
                AVG(duration_ms) AS avg_duration_ms,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY duration_ms
                ))::INTEGER AS median_duration_ms
            FROM endpoint_data
            GROUP BY project_id, route
        """
        )

        result = await session.execute(
            query, {"start_time": start_time, "end_time": end_time}
        )
        rows = result.fetchall()

        metrics: dict[int, dict[str, dict]] = {}
        for row in rows:
            project_id, route = row[0], row[1]
            if project_id not in metrics:
                metrics[project_id] = {}
            metrics[project_id][route] = {
                "log_count": row[2],
                "min_duration_ms": row[3],
                "max_duration_ms": row[4],
                "avg_duration_ms": float(row[5]),
                "median_duration_ms": row[6],
            }
        return metrics


async def _batch_upsert_bottleneck_metrics(
    project_routes: dict[int, list[str]],
    route_metrics: dict[int, dict[str, dict]],
    date_str: str,
    hour: int,
) -> None:
    params = []
    for project_id, routes in project_routes.items():
        for route in routes:
            project_data = route_metrics.get(project_id, {})
            if route in project_data:
                m = project_data[route]
                params.append(
                    {
                        "project_id": project_id,
                        "date_str": date_str,
                        "hour": hour,
                        "route": route,
                        "log_count": m["log_count"],
                        "min_duration_ms": m["min_duration_ms"],
                        "max_duration_ms": m["max_duration_ms"],
                        "avg_duration_ms": m["avg_duration_ms"],
                        "median_duration_ms": m["median_duration_ms"],
                    }
                )
            else:
                params.append(
                    {
                        "project_id": project_id,
                        "date_str": date_str,
                        "hour": hour,
                        "route": route,
                        "log_count": 0,
                        "min_duration_ms": 0,
                        "max_duration_ms": 0,
                        "avg_duration_ms": 0.0,
                        "median_duration_ms": 0,
                    }
                )

    if not params:
        return

    query = sa.text(
        """
        INSERT INTO bottleneck_metrics (
            project_id,
            date,
            hour,
            route,
            log_count,
            min_duration_ms,
            max_duration_ms,
            avg_duration_ms,
            median_duration_ms
        )
        VALUES (
            :project_id,
            :date_str,
            :hour,
            :route,
            :log_count,
            :min_duration_ms,
            :max_duration_ms,
            :avg_duration_ms,
            :median_duration_ms
        )
        ON CONFLICT (project_id, date, hour, route)
        DO UPDATE SET
            log_count = EXCLUDED.log_count,
            min_duration_ms = EXCLUDED.min_duration_ms,
            max_duration_ms = EXCLUDED.max_duration_ms,
            avg_duration_ms = EXCLUDED.avg_duration_ms,
            median_duration_ms = EXCLUDED.median_duration_ms,
            updated_at = NOW()
    """
    )

    async with database.get_logs_session() as session:
        await session.execute(query, params)
        await session.commit()
