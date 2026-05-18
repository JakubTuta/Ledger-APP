import datetime
import json
import time

import analytics_workers.config as config
import analytics_workers.database as database
import analytics_workers.jobs.rollup_state as rollup_state
import analytics_workers.redis_client as redis_client
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.log_metrics")

_VALID_LEVELS = frozenset({"debug", "info", "warning", "error", "critical"})
_JOB_NAME = "log_metrics_5m"
_DEFAULT_LOOKBACK = datetime.timedelta(days=7)


async def aggregate_log_metrics() -> None:
    settings = config.get_settings()
    redis = redis_client.get_redis()
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as session:
            last_bucket = await rollup_state.get_last_bucket(
                session, _JOB_NAME, _DEFAULT_LOOKBACK
            )

            query = sa.text(
                """
                SELECT
                    project_id,
                    date_trunc('hour', timestamp) +
                        (EXTRACT(minute FROM timestamp)::int / 5) * INTERVAL '5 minutes' as bucket,
                    level,
                    COUNT(*) as count
                FROM logs
                WHERE timestamp >= :since
                GROUP BY project_id, bucket, level
                ORDER BY project_id, bucket DESC
            """
            )

            result = await session.execute(query, {"since": last_bucket})
            rows = result.fetchall()

            volume_5m_rows: list[dict] = []
            error_rate_rows: list[dict] = []
            hourly_volume: dict[tuple[int, datetime.datetime], dict] = {}
            error_by_project: dict[int, list] = {}
            error_acc: dict[tuple[int, datetime.datetime], dict] = {}
            max_bucket: datetime.datetime | None = None

            for project_id, bucket, level, count in rows:
                if max_bucket is None or bucket > max_bucket:
                    max_bucket = bucket

                if level in _VALID_LEVELS:
                    volume_5m_rows.append(
                        {
                            "project_id": project_id,
                            "level": level,
                            "bucket": bucket,
                            "count": count,
                        }
                    )

                    hour_bucket = bucket.replace(minute=0, second=0, microsecond=0)
                    hkey = (project_id, hour_bucket)
                    if hkey not in hourly_volume:
                        hourly_volume[hkey] = {
                            "timestamp": hour_bucket.isoformat(),
                            "debug": 0,
                            "info": 0,
                            "warning": 0,
                            "error": 0,
                            "critical": 0,
                        }
                    hourly_volume[hkey][level] += count

                ekey = (project_id, bucket)
                if ekey not in error_acc:
                    error_acc[ekey] = {
                        "error_only": 0,
                        "critical": 0,
                        "errors": 0,
                        "total": 0,
                    }
                acc = error_acc[ekey]
                acc["total"] += count
                if level == "error":
                    acc["error_only"] += count
                    acc["errors"] += count
                elif level == "critical":
                    acc["critical"] += count
                    acc["errors"] += count

            volume_by_project: dict[int, list] = {}
            for (project_id, _hour), data in hourly_volume.items():
                volume_by_project.setdefault(project_id, []).append(data)

            for (project_id, bucket), acc in error_acc.items():
                ratio = acc["errors"] / acc["total"] if acc["total"] > 0 else 0.0
                error_by_project.setdefault(project_id, []).append(
                    {
                        "timestamp": bucket.isoformat(),
                        "error_count": acc["error_only"],
                        "critical_count": acc["critical"],
                    }
                )
                error_rate_rows.append(
                    {
                        "project_id": project_id,
                        "bucket": bucket,
                        "errors": acc["errors"],
                        "total": acc["total"],
                        "ratio": ratio,
                    }
                )

            for project_id, data in volume_by_project.items():
                await redis.setex(
                    f"metrics:log_volume:{project_id}:1hour",
                    settings.ANALYTICS_LOG_VOLUME_TTL,
                    json.dumps(data),
                )

            for project_id, data in error_by_project.items():
                await redis.setex(
                    f"metrics:error_rate:{project_id}:5min",
                    settings.ANALYTICS_ERROR_RATE_TTL,
                    json.dumps(data),
                )

            if volume_5m_rows:
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO log_volume_5m (project_id, level, bucket, count)
                        VALUES (:project_id, :level, :bucket, :count)
                        ON CONFLICT (project_id, level, bucket)
                        DO UPDATE SET count = EXCLUDED.count
                        """
                    ),
                    volume_5m_rows,
                )

            if error_rate_rows:
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO error_rate_5m (project_id, bucket, errors, total, ratio)
                        VALUES (:project_id, :bucket, :errors, :total, :ratio)
                        ON CONFLICT (project_id, bucket)
                        DO UPDATE SET
                            errors = EXCLUDED.errors,
                            total  = EXCLUDED.total,
                            ratio  = EXCLUDED.ratio
                        """
                    ),
                    error_rate_rows,
                )

            if max_bucket is not None:
                await rollup_state.set_last_bucket(session, _JOB_NAME, max_bucket)

            await session.commit()

        elapsed = time.perf_counter() - start
        logger.info(
            f"Log metrics aggregation done in {elapsed:.2f}s "
            f"for {len(volume_by_project)} volume / {len(error_by_project)} error projects"
        )

    except Exception as e:
        logger.error(f"Log metrics aggregation failed: {e}", exc_info=True)
        raise
