import json
import time

import analytics_workers.config as config
import analytics_workers.database as database
import analytics_workers.redis_client as redis_client
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.error_rates")


async def aggregate_error_rates() -> None:
    settings = config.get_settings()
    redis = redis_client.get_redis()
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            query = sa.text(
                """
                SELECT
                    project_id,
                    date_trunc('hour', timestamp) +
                        (EXTRACT(minute FROM timestamp)::int / 5) * INTERVAL '5 minutes' as bucket,
                    COUNT(*) FILTER (WHERE level IN ('error', 'critical')) as error_count,
                    COUNT(*) FILTER (WHERE level = 'error') as error_only_count,
                    COUNT(*) FILTER (WHERE level = 'critical') as critical_count,
                    COUNT(*) as total_count
                FROM logs
                WHERE timestamp > NOW() - INTERVAL '24 hours'
                GROUP BY project_id, bucket
                ORDER BY project_id, bucket DESC
            """
            )

            result = await session.execute(query)
            rows = result.fetchall()

            by_project: dict[int, list] = {}
            rollup_rows = []

            for row in rows:
                project_id = row[0]
                bucket = row[1]
                error_count = row[2]
                error_only_count = row[3]
                critical_count = row[4]
                total_count = row[5]
                ratio = error_count / total_count if total_count > 0 else 0.0

                if project_id not in by_project:
                    by_project[project_id] = []

                by_project[project_id].append(
                    {
                        "timestamp": bucket.isoformat(),
                        "error_count": error_only_count,
                        "critical_count": critical_count,
                    }
                )

                rollup_rows.append(
                    {
                        "project_id": project_id,
                        "bucket": bucket,
                        "errors": error_count,
                        "total": total_count,
                        "ratio": ratio,
                    }
                )

            for project_id, data in by_project.items():
                cache_key = f"metrics:error_rate:{project_id}:5min"
                cache_value = json.dumps(data)

                await redis.setex(
                    cache_key,
                    settings.ANALYTICS_ERROR_RATE_TTL,
                    cache_value,
                )

            if rollup_rows:
                upsert_query = sa.text(
                    """
                    INSERT INTO error_rate_5m (project_id, bucket, errors, total, ratio)
                    VALUES (:project_id, :bucket, :errors, :total, :ratio)
                    ON CONFLICT (project_id, bucket)
                    DO UPDATE SET
                        errors = EXCLUDED.errors,
                        total  = EXCLUDED.total,
                        ratio  = EXCLUDED.ratio
                    """
                )
                await session.execute(upsert_query, rollup_rows)
                await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(
            f"Error rate aggregation done in {elapsed:.2f}s for {len(by_project)} projects"
        )

    except Exception as e:
        logger.error(f"Error rate aggregation failed: {e}", exc_info=True)
        raise
