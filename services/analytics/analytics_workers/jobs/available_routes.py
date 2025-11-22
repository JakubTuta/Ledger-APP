import json

import sqlalchemy as sa

import analytics_workers.database as database
import analytics_workers.utils.logging as logging

logger = logging.get_logger("jobs.available_routes")


async def update_available_routes() -> None:
    """
    Update available_routes for all dashboard panels.

    This job queries unique endpoint routes from the logs database for each project,
    then updates the user_dashboards panels in the auth database to include the
    available routes for each panel's associated project.
    """
    logger.info("Starting available routes update job")

    try:
        project_routes = await _get_project_routes()
        if not project_routes:
            logger.info("No endpoint routes found, skipping panel updates")
            return

        await _update_panel_routes(project_routes)

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


async def _update_panel_routes(project_routes: dict[int, list[str]]) -> None:
    """
    Update available_routes in all dashboard panels for matching projects.

    Args:
        project_routes: Dictionary mapping project_id to list of route strings
    """
    async with database.get_auth_session() as session:
        select_query = sa.text("""
            SELECT id, panels FROM user_dashboards
        """)

        result = await session.execute(select_query)
        dashboards = result.fetchall()

        updated_count = 0
        for dashboard_id, panels in dashboards:
            if not panels:
                continue

            updated = False
            updated_panels = []

            for panel in panels:
                project_id_str = panel.get("project_id", "")
                try:
                    project_id = int(project_id_str)
                except (ValueError, TypeError):
                    updated_panels.append(panel)
                    continue

                routes = project_routes.get(project_id, [])
                current_routes = panel.get("available_routes", [])

                if set(routes) != set(current_routes):
                    panel["available_routes"] = routes
                    updated = True

                updated_panels.append(panel)

            if updated:
                update_query = sa.text("""
                    UPDATE user_dashboards
                    SET panels = :panels, updated_at = NOW()
                    WHERE id = :dashboard_id
                """)

                await session.execute(
                    update_query,
                    {
                        "panels": json.dumps(updated_panels),
                        "dashboard_id": dashboard_id,
                    },
                )
                updated_count += 1

        await session.commit()

        logger.info(f"Updated {updated_count} dashboards with new available routes")
