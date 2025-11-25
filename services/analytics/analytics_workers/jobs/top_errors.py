import json

import analytics_workers.config as config
import analytics_workers.database as database
import analytics_workers.redis_client as redis_client
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.top_errors")


async def compute_top_errors() -> None:
    settings = config.get_settings()
    redis = redis_client.get_redis()

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
                FROM error_groups
                WHERE status = 'unresolved'
                  AND last_seen > NOW() - INTERVAL '24 hours'
                ORDER BY project_id, occurrence_count DESC
            """
            )

            result = await session.execute(query)
            rows = result.fetchall()

            by_project: dict[int, list] = {}
            for row in rows:
                project_id = row[0]
                fingerprint = row[1]
                error_type = row[2]
                error_message = row[3]
                occurrence_count = row[4]
                first_seen = row[5]
                last_seen = row[6]
                status = row[7]

                if project_id not in by_project:
                    by_project[project_id] = []

                by_project[project_id].append(
                    {
                        "fingerprint": fingerprint,
                        "error_type": error_type,
                        "error_message": error_message,
                        "occurrence_count": occurrence_count,
                        "first_seen": first_seen.isoformat(),
                        "last_seen": last_seen.isoformat(),
                        "status": status,
                    }
                )

            for project_id, errors in by_project.items():
                cache_key = f"metrics:top_errors:{project_id}"
                top_50 = errors[:50]
                cache_value = json.dumps(top_50)

                await redis.setex(
                    cache_key,
                    settings.ANALYTICS_TOP_ERRORS_TTL,
                    cache_value,
                )

    except Exception as e:
        logger.error(f"Top errors computation failed: {e}", exc_info=True)
        raise
