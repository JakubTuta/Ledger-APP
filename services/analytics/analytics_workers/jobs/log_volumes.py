import datetime
import json
import time

import analytics_workers.config as config
import analytics_workers.database as database
import analytics_workers.redis_client as redis_client
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.log_volumes")

_VALID_LEVELS = frozenset({"debug", "info", "warning", "error", "critical"})


async def aggregate_log_volumes() -> None:
    settings = config.get_settings()
    redis = redis_client.get_redis()
    start = time.perf_counter()

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
                  AND level IN ('debug', 'info', 'warning', 'error', 'critical')
                GROUP BY project_id, bucket, level
                ORDER BY project_id, bucket DESC
            """
            )

            result = await session.execute(query)
            rows = result.fetchall()

            aggregated: dict[tuple[int, datetime.datetime], dict] = {}
            rollup_rows: list[dict] = []

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

                if level in _VALID_LEVELS:
                    aggregated[key][level] = count

                rollup_rows.append(
                    {
                        "project_id": project_id,
                        "level": level,
                        "bucket": bucket,
                        "count": count,
                    }
                )

            by_project: dict[int, list] = {}
            for (project_id, _bucket), data in aggregated.items():
                if project_id not in by_project:
                    by_project[project_id] = []
                by_project[project_id].append(data)

            for project_id, data in by_project.items():
                cache_key = f"metrics:log_volume:{project_id}:1hour"
                cache_value = json.dumps(data)

                await redis.setex(
                    cache_key,
                    settings.ANALYTICS_LOG_VOLUME_TTL,
                    cache_value,
                )

            if rollup_rows:
                upsert_query = sa.text(
                    """
                    INSERT INTO log_volume_5m (project_id, level, bucket, count)
                    SELECT
                        project_id,
                        level,
                        date_trunc('hour', bucket) +
                            (EXTRACT(minute FROM bucket)::int / 5) * INTERVAL '5 minutes',
                        SUM(count)
                    FROM (
                        SELECT
                            :project_id AS project_id,
                            :level AS level,
                            :bucket AS bucket,
                            :count AS count
                    ) sub
                    GROUP BY project_id, level,
                        date_trunc('hour', bucket) +
                            (EXTRACT(minute FROM bucket)::int / 5) * INTERVAL '5 minutes'
                    ON CONFLICT (project_id, level, bucket)
                    DO UPDATE SET count = EXCLUDED.count
                    """
                )
                for row_data in rollup_rows:
                    await session.execute(
                        sa.text(
                            """
                            INSERT INTO log_volume_5m (project_id, level, bucket, count)
                            VALUES (
                                :project_id,
                                :level,
                                date_trunc('hour', :bucket::timestamptz) +
                                    (EXTRACT(minute FROM :bucket::timestamptz)::int / 5) * INTERVAL '5 minutes',
                                :count
                            )
                            ON CONFLICT (project_id, level, bucket)
                            DO UPDATE SET count = EXCLUDED.count
                            """
                        ),
                        row_data,
                    )
                await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(
            f"Log volume aggregation done in {elapsed:.2f}s for {len(by_project)} projects"
        )

    except Exception as e:
        logger.error(f"Log volume aggregation failed: {e}", exc_info=True)
        raise
