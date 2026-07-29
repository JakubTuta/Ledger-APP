import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.available_routes")


async def update_available_routes() -> None:
    start = time.perf_counter()
    try:
        project_routes = await _get_project_routes()
        if not project_routes:
            return

        await _update_project_routes(project_routes)

        elapsed = time.perf_counter() - start
        logger.info(
            f"Available routes update done in {elapsed:.2f}s for {len(project_routes)} projects"
        )

    except Exception as e:
        logger.error(f"Available routes update failed: {e}", exc_info=True)
        raise


async def _get_project_routes() -> dict[int, list[str]]:
    async with database.get_logs_session() as session:
        # The hourly endpoint aggregation already derives (method, path) per
        # project straight from raw logs, so the route list comes from there
        # rather than re-scanning a week of `logs` on every run. It must not
        # come from bottleneck_metrics: that job is seeded by the very column
        # this one writes, so a newly seen route would never be discovered.
        query = sa.text(
            """
            SELECT
                project_id,
                endpoint_method || ' ' || endpoint_path AS route
            FROM aggregated_metrics
            WHERE
                metric_type = 'endpoint'
                AND endpoint_method IS NOT NULL
                AND endpoint_path IS NOT NULL
                AND date >= TO_CHAR(NOW() - INTERVAL '7 days', 'YYYYMMDD')
            GROUP BY project_id, endpoint_method, endpoint_path
            ORDER BY project_id, route
        """
        )

        result = await session.execute(query)
        rows = result.fetchall()

        project_routes: dict[int, list[str]] = {}
        for row in rows:
            project_id = row[0]
            route = row[1]
            if project_id not in project_routes:
                project_routes[project_id] = []
            project_routes[project_id].append(route)

        return project_routes


async def _update_project_routes(project_routes: dict[int, list[str]]) -> None:
    update_query = sa.text(
        """
        UPDATE projects
        SET available_routes = :routes, updated_at = NOW()
        WHERE id = :project_id
          AND (available_routes IS NULL OR available_routes != :routes)
    """
    )
    params = [
        {"project_id": project_id, "routes": routes}
        for project_id, routes in project_routes.items()
    ]

    async with database.get_auth_session() as session:
        await session.execute(update_query, params)
        await session.commit()
