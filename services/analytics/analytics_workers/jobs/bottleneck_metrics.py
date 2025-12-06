import datetime

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

    logger.info(
        f"Starting bottleneck metrics aggregation for {date_str} hour {hour} "
        f"({previous_hour_start} to {previous_hour_end})"
    )

    try:
        active_project_ids = await _get_active_projects(
            previous_hour_start, previous_hour_end
        )

        if not active_project_ids:
            logger.info("No projects with logs in the previous hour")
            return

        logger.info(
            f"Found {len(active_project_ids)} projects with logs in the previous hour"
        )

        for project_id in active_project_ids:
            await _aggregate_project_bottlenecks(
                project_id, date_str, hour, previous_hour_start, previous_hour_end
            )

        logger.info(
            f"Completed bottleneck metrics aggregation for {len(active_project_ids)} projects"
        )

    except Exception as e:
        logger.error(f"Bottleneck metrics aggregation failed: {e}", exc_info=True)
        raise


async def _get_active_projects(
    start_time: datetime.datetime, end_time: datetime.datetime
) -> list[int]:
    async with database.get_logs_session() as session:
        query = sa.text(
            """
            SELECT DISTINCT project_id
            FROM logs
            WHERE timestamp >= :start_time AND timestamp < :end_time
            ORDER BY project_id
        """
        )

        result = await session.execute(
            query, {"start_time": start_time, "end_time": end_time}
        )
        rows = result.fetchall()
        return [row[0] for row in rows]


async def _aggregate_project_bottlenecks(
    project_id: int,
    date_str: str,
    hour: int,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
) -> None:
    available_routes = await _get_project_routes(project_id)

    if not available_routes:
        logger.warning(
            f"Project {project_id} has no available_routes configured, skipping"
        )
        return

    route_metrics = await _get_route_metrics(
        project_id, start_time, end_time
    )

    await _upsert_bottleneck_metrics(
        project_id, date_str, hour, available_routes, route_metrics
    )

    logger.info(
        f"Aggregated bottleneck metrics for project {project_id}: "
        f"{len(available_routes)} routes ({len(route_metrics)} with data)"
    )


async def _get_project_routes(project_id: int) -> list[str]:
    async with database.get_auth_session() as session:
        query = sa.text(
            """
            SELECT available_routes
            FROM projects
            WHERE id = :project_id
        """
        )

        result = await session.execute(query, {"project_id": project_id})
        row = result.fetchone()

        if row and row[0]:
            return row[0]
        return []


async def _get_route_metrics(
    project_id: int, start_time: datetime.datetime, end_time: datetime.datetime
) -> dict[str, dict]:
    async with database.get_logs_session() as session:
        query = sa.text(
            """
            SELECT
                (attributes->'endpoint'->>'path')::VARCHAR AS route,
                COUNT(*) AS log_count,
                ROUND(MIN((attributes->'endpoint'->>'duration_ms')::FLOAT))::INTEGER AS min_duration_ms,
                ROUND(MAX((attributes->'endpoint'->>'duration_ms')::FLOAT))::INTEGER AS max_duration_ms,
                AVG((attributes->'endpoint'->>'duration_ms')::FLOAT) AS avg_duration_ms,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY (attributes->'endpoint'->>'duration_ms')::FLOAT
                ))::INTEGER AS median_duration_ms
            FROM logs
            WHERE
                project_id = :project_id
                AND log_type = 'endpoint'
                AND timestamp >= :start_time
                AND timestamp < :end_time
                AND attributes->'endpoint'->>'path' IS NOT NULL
                AND attributes->'endpoint'->>'duration_ms' IS NOT NULL
            GROUP BY
                attributes->'endpoint'->>'path'
        """
        )

        result = await session.execute(
            query,
            {
                "project_id": project_id,
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        rows = result.fetchall()

        metrics = {}
        for row in rows:
            route = row[0]
            metrics[route] = {
                "log_count": row[1],
                "min_duration_ms": row[2],
                "max_duration_ms": row[3],
                "avg_duration_ms": row[4],
                "median_duration_ms": row[5],
            }

        return metrics


async def _upsert_bottleneck_metrics(
    project_id: int,
    date_str: str,
    hour: int,
    available_routes: list[str],
    route_metrics: dict[str, dict],
) -> None:
    async with database.get_logs_session() as session:
        for route in available_routes:
            if route in route_metrics:
                metrics = route_metrics[route]
                log_count = metrics["log_count"]
                min_duration_ms = metrics["min_duration_ms"]
                max_duration_ms = metrics["max_duration_ms"]
                avg_duration_ms = metrics["avg_duration_ms"]
                median_duration_ms = metrics["median_duration_ms"]
            else:
                log_count = 0
                min_duration_ms = 0
                max_duration_ms = 0
                avg_duration_ms = 0
                median_duration_ms = 0

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

            await session.execute(
                query,
                {
                    "project_id": project_id,
                    "date_str": date_str,
                    "hour": hour,
                    "route": route,
                    "log_count": log_count,
                    "min_duration_ms": min_duration_ms,
                    "max_duration_ms": max_duration_ms,
                    "avg_duration_ms": avg_duration_ms,
                    "median_duration_ms": median_duration_ms,
                },
            )

        await session.commit()
