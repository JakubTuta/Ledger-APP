import sqlalchemy as sa

import analytics_workers.database as database
import analytics_workers.utils.logging as logging

logger = logging.get_logger("jobs.available_routes")


async def update_available_routes() -> None:
    """
    Update available_routes for all projects.

    This job queries unique endpoint routes from the logs database for each project,
    then updates the projects table in the auth database with the available routes.
    """
    logger.info("Starting available routes update job")

    try:
        project_routes = await _get_project_routes()
        if not project_routes:
            logger.info("No endpoint routes found, skipping project updates")
            return

        await _update_project_routes(project_routes)

        logger.info(
            f"Available routes update completed for {len(project_routes)} projects"
        )

    except Exception as e:
        logger.error(f"Available routes update failed: {e}", exc_info=True)
        raise


async def _get_project_routes() -> dict[int, list[str]]:
    """
    Query unique endpoint routes per project from logs database.

    Returns:
        Dictionary mapping project_id to list of route strings (e.g., "GET /api/v1/users")
    """
    async with database.get_logs_session() as session:
        query = sa.text("""
            SELECT
                project_id,
                CONCAT(
                    (attributes->'endpoint'->>'method'),
                    ' ',
                    (attributes->'endpoint'->>'path')
                ) AS route
            FROM logs
            WHERE
                log_type = 'endpoint'
                AND attributes->'endpoint'->>'method' IS NOT NULL
                AND attributes->'endpoint'->>'path' IS NOT NULL
            GROUP BY
                project_id,
                attributes->'endpoint'->>'method',
                attributes->'endpoint'->>'path'
            ORDER BY
                project_id,
                route
        """)

        result = await session.execute(query)
        rows = result.fetchall()

        project_routes: dict[int, list[str]] = {}
        for row in rows:
            project_id = row[0]
            route = row[1]
            if project_id not in project_routes:
                project_routes[project_id] = []
            project_routes[project_id].append(route)

        logger.info(
            f"Found routes for {len(project_routes)} projects: "
            f"{sum(len(routes) for routes in project_routes.values())} total routes"
        )

        return project_routes


async def _update_project_routes(project_routes: dict[int, list[str]]) -> None:
    """
    Update available_routes column in projects table for matching projects.

    Args:
        project_routes: Dictionary mapping project_id to list of route strings
    """
    async with database.get_auth_session() as session:
        updated_count = 0

        for project_id, routes in project_routes.items():
            update_query = sa.text("""
                UPDATE projects
                SET available_routes = :routes, updated_at = NOW()
                WHERE id = :project_id
                AND (
                    available_routes IS NULL
                    OR available_routes != :routes
                )
            """)

            result = await session.execute(
                update_query,
                {
                    "routes": routes,
                    "project_id": project_id,
                },
            )

            if result.rowcount > 0:
                updated_count += 1

        await session.commit()

        logger.info(f"Updated {updated_count} projects with new available routes")
