import json

import analytics_workers.config as config
import analytics_workers.database as database
import analytics_workers.redis_client as redis_client
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.error_rates")


async def aggregate_error_rates() -> None:
    settings = config.get_settings()
    redis = redis_client.get_redis()

    try:
        async with database.get_logs_session() as session:
            query = sa.text(
                """
                SELECT
                    project_id,
                    date_trunc('minute', timestamp) +
                        (EXTRACT(minute FROM timestamp)::int / 5) * INTERVAL '5 minutes' as bucket,
                    COUNT(*) FILTER (WHERE level = 'error') as error_count,
                    COUNT(*) FILTER (WHERE level = 'critical') as critical_count
                FROM logs
                WHERE timestamp > NOW() - INTERVAL '24 hours'
                GROUP BY project_id, bucket
                ORDER BY project_id, bucket DESC
            """
            )

            result = await session.execute(query)
            rows = result.fetchall()

            by_project: dict[int, list] = {}
            for row in rows:
                project_id = row[0]
                bucket = row[1]
                error_count = row[2] or 0
                critical_count = row[3] or 0

                if project_id not in by_project:
                    by_project[project_id] = []

                by_project[project_id].append(
                    {
                        "timestamp": bucket.isoformat(),
                        "error_count": error_count,
                        "critical_count": critical_count,
                    }
                )

            for project_id, data in by_project.items():
                cache_key = f"metrics:error_rate:{project_id}:5min"
                cache_value = json.dumps(data)

                await redis.setex(
                    cache_key,
                    settings.ERROR_RATE_TTL,
                    cache_value,
                )

    except Exception as e:
        logger.error(f"Error rate aggregation failed: {e}", exc_info=True)
        raise
