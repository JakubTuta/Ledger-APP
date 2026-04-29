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
        query = sa.text(
            """
            SELECT
                project_id,
                (attributes->'endpoint'->>'path') AS route
            FROM logs
            WHERE
                log_type = 'endpoint'
                AND attributes->'endpoint'->>'path' IS NOT NULL
                AND timestamp > NOW() - INTERVAL '7 days'
            GROUP BY
                project_id,
                attributes->'endpoint'->>'path'
            ORDER BY
                project_id,
                route
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
    async with database.get_auth_session() as session:
        updated_count = 0

        for project_id, routes in project_routes.items():
            update_query = sa.text(
                """
                UPDATE projects
                SET available_routes = :routes, updated_at = NOW()
                WHERE id = :project_id
                AND (
                    available_routes IS NULL
                    OR available_routes != :routes
                )
            """
            )

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
