import json
import time

import analytics_workers.config as config
import analytics_workers.database as database
import analytics_workers.redis_client as redis_client
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.top_errors")


async def compute_top_errors() -> None:
    settings = config.get_settings()
    redis = redis_client.get_redis()
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            query = sa.text(
                """
                SELECT
                    project_id,
                    fingerprint,
                    error_type,
                    error_message,
                    occurrence_count,
                    first_seen,
                    last_seen,
                    status
                FROM (
                    SELECT
                        project_id,
                        fingerprint,
                        error_type,
                        error_message,
                        occurrence_count,
                        first_seen,
                        last_seen,
                        status,
                        ROW_NUMBER() OVER (
                            PARTITION BY project_id
                            ORDER BY occurrence_count DESC
                        ) AS rn
                    FROM error_groups
                    WHERE status = 'unresolved'
                      AND last_seen > NOW() - INTERVAL '24 hours'
                ) ranked
                WHERE rn <= :limit
                ORDER BY project_id, occurrence_count DESC
            """
            )

            result = await session.execute(
                query, {"limit": settings.ANALYTICS_TOP_ERRORS_LIMIT}
            )
            rows = result.fetchall()

            by_project: dict[int, list] = {}
            for row in rows:
                project_id = row[0]

                if project_id not in by_project:
                    by_project[project_id] = []

                by_project[project_id].append(
                    {
                        "fingerprint": row[1],
                        "error_type": row[2],
                        "error_message": row[3],
                        "occurrence_count": row[4],
                        "first_seen": row[5].isoformat(),
                        "last_seen": row[6].isoformat(),
                        "status": row[7],
                    }
                )

            for project_id, errors in by_project.items():
                cache_key = f"metrics:top_errors:{project_id}"
                cache_value = json.dumps(errors)

                await redis.setex(
                    cache_key,
                    settings.ANALYTICS_TOP_ERRORS_TTL,
                    cache_value,
                )

        elapsed = time.perf_counter() - start
        logger.info(
            f"Top errors computation done in {elapsed:.2f}s for {len(by_project)} projects"
        )

    except Exception as e:
        logger.error(f"Top errors computation failed: {e}", exc_info=True)
        raise
