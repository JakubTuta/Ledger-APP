import datetime
import json

import analytics_workers.config as config
import analytics_workers.database as database
import analytics_workers.redis_client as redis_client
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.log_volumes")


async def aggregate_log_volumes() -> None:
    settings = config.get_settings()
    redis = redis_client.get_redis()

    try:
        async with database.get_logs_session() as session:
            query = sa.text(
                """
                SELECT
                    project_id,
                    date_trunc('hour', timestamp) as bucket,
                    level,
                    COUNT(*) as count
                FROM logs
                WHERE timestamp > NOW() - INTERVAL '7 days'
                GROUP BY project_id, bucket, level
                ORDER BY project_id, bucket DESC
            """
            )

            result = await session.execute(query)
            rows = result.fetchall()

            aggregated: dict[tuple[int, datetime.datetime], dict] = {}

            for row in rows:
                project_id = row[0]
                bucket = row[1]
                level = row[2]
                count = row[3]

                key = (project_id, bucket)
                if key not in aggregated:
                    aggregated[key] = {
                        "timestamp": bucket.isoformat(),
                        "debug": 0,
                        "info": 0,
                        "warning": 0,
                        "error": 0,
                        "critical": 0,
                    }

                aggregated[key][level] = count

            by_project: dict[int, list] = {}
            for (project_id, bucket), data in aggregated.items():
                if project_id not in by_project:
                    by_project[project_id] = []
                by_project[project_id].append(data)

            for project_id, data in by_project.items():
                cache_key = f"metrics:log_volume:{project_id}:1hour"
                cache_value = json.dumps(data)

                await redis.setex(
                    cache_key,
                    settings.LOG_VOLUME_TTL,
                    cache_value,
                )

    except Exception as e:
        logger.error(f"Log volume aggregation failed: {e}", exc_info=True)
        raise
