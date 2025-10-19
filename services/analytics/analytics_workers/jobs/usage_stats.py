import json

import sqlalchemy as sa

import analytics_workers.config as config
import analytics_workers.database as database
import analytics_workers.redis_client as redis_client
import analytics_workers.utils.logging as logging

logger = logging.get_logger("jobs.usage_stats")


async def generate_usage_stats() -> None:
    settings = config.get_settings()
    redis = redis_client.get_redis()

    logger.info("Starting usage stats generation job")

    try:
        async with database.get_logs_session() as logs_session:
            async with database.get_auth_session() as auth_session:
                projects_query = sa.text("""
                    SELECT id, daily_quota
                    FROM projects
                """)
                projects_result = await auth_session.execute(projects_query)
                projects_map = {row[0]: row[1] for row in projects_result.fetchall()}

                logs_query = sa.text("""
                    SELECT
                        project_id,
                        DATE(timestamp) as date,
                        COUNT(*) as log_count
                    FROM logs
                    WHERE timestamp > NOW() - INTERVAL '30 days'
                    GROUP BY project_id, DATE(timestamp)
                    ORDER BY project_id, date DESC
                """)

                result = await logs_session.execute(logs_query)
                rows = result.fetchall()

                by_project: dict[int, list] = {}
                for row in rows:
                    project_id = row[0]
                    date = row[1]
                    log_count = row[2]

                    daily_quota = projects_map.get(project_id, 1_000_000)
                    quota_used_percent = (
                        round((log_count / daily_quota * 100), 2)
                        if daily_quota > 0
                        else 0
                    )

                    if project_id not in by_project:
                        by_project[project_id] = []

                    by_project[project_id].append({
                        "date": date.isoformat(),
                        "log_count": log_count,
                        "daily_quota": daily_quota,
                        "quota_used_percent": quota_used_percent,
                    })

                for project_id, usage in by_project.items():
                    cache_key = f"metrics:usage_stats:{project_id}"
                    cache_value = json.dumps(usage)

                    await redis.setex(
                        cache_key,
                        settings.USAGE_STATS_TTL,
                        cache_value,
                    )

                    logger.debug(
                        f"Cached usage stats for project {project_id}: {len(usage)} days"
                    )

                logger.info(
                    f"Usage stats generation completed for {len(by_project)} projects"
                )

    except Exception as e:
        logger.error(f"Usage stats generation failed: {e}", exc_info=True)
        raise
