import json
import time

import analytics_workers.config as config
import analytics_workers.database as database
import analytics_workers.redis_client as redis_client
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.usage_stats")


async def generate_usage_stats() -> None:
    settings = config.get_settings()
    redis = redis_client.get_redis()
    start = time.perf_counter()

    try:
        projects_map = await _fetch_projects()
        log_rows = await _fetch_log_counts()
        span_rows = await _fetch_span_counts()
        metric_rows = await _fetch_metric_point_counts()

        # Union of (project_id, date) keys across all three signals - a
        # spans-only day (no logs that day) must still produce an entry with
        # log_count: 0, not be silently dropped.
        counts: dict[tuple[int, object], dict[str, int]] = {}
        for project_id, date, log_count in log_rows:
            counts.setdefault((project_id, date), {})["log_count"] = log_count
        for project_id, date, span_count in span_rows:
            counts.setdefault((project_id, date), {})["span_count"] = span_count
        for project_id, date, metric_point_count in metric_rows:
            counts.setdefault((project_id, date), {})["metric_point_count"] = metric_point_count

        def _percent(count: int, quota: int) -> float:
            return round((count / quota * 100), 2) if quota > 0 else 0

        by_project: dict[int, list] = {}
        upsert_params: list[dict] = []

        for (project_id, date), signal_counts in counts.items():
            quotas = projects_map.get(
                project_id,
                {
                    "logs_daily_quota": settings.DEFAULT_LOGS_DAILY_QUOTA,
                    "spans_daily_quota": settings.DEFAULT_SPANS_DAILY_QUOTA,
                    "metrics_daily_quota": settings.DEFAULT_METRICS_DAILY_QUOTA,
                },
            )
            log_count = signal_counts.get("log_count", 0)
            span_count = signal_counts.get("span_count", 0)
            metric_point_count = signal_counts.get("metric_point_count", 0)

            logs_daily_quota = quotas["logs_daily_quota"]
            spans_daily_quota = quotas["spans_daily_quota"]
            metrics_daily_quota = quotas["metrics_daily_quota"]

            by_project.setdefault(project_id, []).append(
                {
                    "date": date.isoformat(),
                    "log_count": log_count,
                    "span_count": span_count,
                    "metric_point_count": metric_point_count,
                    "logs_daily_quota": logs_daily_quota,
                    "spans_daily_quota": spans_daily_quota,
                    "metrics_daily_quota": metrics_daily_quota,
                    "logs_quota_used_percent": _percent(log_count, logs_daily_quota),
                    "spans_quota_used_percent": _percent(span_count, spans_daily_quota),
                    "metrics_quota_used_percent": _percent(metric_point_count, metrics_daily_quota),
                }
            )

            upsert_params.append(
                {
                    "project_id": project_id,
                    "date": date,
                    "log_count": log_count,
                    "span_count": span_count,
                    "metric_point_count": metric_point_count,
                }
            )

        if upsert_params:
            await _batch_upsert_daily_usage(upsert_params)

        for project_id, usage in by_project.items():
            cache_key = f"metrics:usage_stats:{project_id}"
            await redis.setex(
                cache_key,
                settings.ANALYTICS_USAGE_STATS_TTL,
                json.dumps(usage),
            )

        elapsed = time.perf_counter() - start
        logger.info(f"Usage stats generation done in {elapsed:.2f}s for {len(by_project)} projects")

    except Exception as e:
        logger.error(f"Usage stats generation failed: {e}", exc_info=True)
        raise


async def _fetch_projects() -> dict[int, dict[str, int]]:
    async with database.get_auth_session() as session:
        result = await session.execute(
            sa.text(
                "SELECT id, logs_daily_quota, spans_daily_quota, metrics_daily_quota FROM projects"
            )
        )
        return {
            row[0]: {
                "logs_daily_quota": row[1],
                "spans_daily_quota": row[2],
                "metrics_daily_quota": row[3],
            }
            for row in result.fetchall()
        }


async def _fetch_log_counts() -> list[tuple]:
    async with database.get_logs_session() as session:
        query = sa.text(
            """
            SELECT
                project_id,
                DATE(timestamp) as date,
                COUNT(*) as log_count
            FROM logs
            WHERE timestamp > NOW() - INTERVAL '30 days'
            GROUP BY project_id, DATE(timestamp)
            ORDER BY project_id, date DESC
        """
        )
        result = await session.execute(query)
        return result.fetchall()


async def _fetch_span_counts() -> list[tuple]:
    async with database.get_logs_session() as session:
        query = sa.text(
            """
            SELECT
                project_id,
                DATE(start_time) as date,
                COUNT(*) as span_count
            FROM spans
            WHERE start_time > NOW() - INTERVAL '30 days'
            GROUP BY project_id, DATE(start_time)
            ORDER BY project_id, date DESC
        """
        )
        result = await session.execute(query)
        return result.fetchall()


async def _fetch_metric_point_counts() -> list[tuple]:
    async with database.get_logs_session() as session:
        query = sa.text(
            """
            SELECT
                project_id,
                DATE(ts) as date,
                COUNT(*) as metric_point_count
            FROM metric_points
            WHERE ts > NOW() - INTERVAL '30 days'
            GROUP BY project_id, DATE(ts)
            ORDER BY project_id, date DESC
        """
        )
        result = await session.execute(query)
        return result.fetchall()


async def _batch_upsert_daily_usage(params: list[dict]) -> None:
    upsert_query = sa.text(
        """
        INSERT INTO daily_usage (
            project_id, date, logs_ingested, logs_queried, storage_bytes,
            spans_ingested, metric_points_ingested, created_at, updated_at
        )
        VALUES (
            :project_id, :date, :log_count, 0, 0,
            :span_count, :metric_point_count, NOW(), NOW()
        )
        ON CONFLICT (project_id, date)
        DO UPDATE SET
            logs_ingested = EXCLUDED.logs_ingested,
            spans_ingested = EXCLUDED.spans_ingested,
            metric_points_ingested = EXCLUDED.metric_points_ingested,
            updated_at = NOW()
    """
    )
    async with database.get_auth_session() as session:
        await session.execute(upsert_query, params)
        await session.commit()
