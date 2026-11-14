import datetime
import json

import ledger_common.redis_client as redis_client
import query_service.schemas as schemas


async def get_usage_stats(
    project_id: int,
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
) -> schemas.UsageStatsResponse:
    redis = redis_client.get_redis()

    cache_key = f"metrics:usage_stats:{project_id}"

    cached_data = await redis.get(cache_key)

    if not cached_data:
        return schemas.UsageStatsResponse(project_id=project_id, usage=[])

    cached_dict = json.loads(cached_data)

    if isinstance(cached_dict, dict) and "usage" in cached_dict:
        data = cached_dict["usage"]
        default_logs_daily_quota = cached_dict.get(
            "logs_daily_quota", cached_dict.get("daily_quota", 0)
        )
    elif isinstance(cached_dict, dict) and "data" in cached_dict:
        data = cached_dict["data"]
        default_logs_daily_quota = cached_dict.get(
            "logs_daily_quota", cached_dict.get("daily_quota", 0)
        )
    else:
        data = cached_dict if isinstance(cached_dict, list) else []
        default_logs_daily_quota = 0

    usage_stats = []
    for item in data:
        usage_date = datetime.date.fromisoformat(item["date"])

        if start_date and usage_date < start_date:
            continue
        if end_date and usage_date > end_date:
            continue

        # Cache items written before the logs/spans/metrics split only have the
        # bare `daily_quota`/`quota_used_percent` keys - fall back to those so
        # old-shape entries (until the next analytics job run) still render.
        logs_daily_quota = item.get(
            "logs_daily_quota", item.get("daily_quota", default_logs_daily_quota)
        )
        logs_quota_used_percent = item.get(
            "logs_quota_used_percent", item.get("quota_used_percent", 0)
        )

        usage_stats.append(
            schemas.UsageStatsData(
                date=usage_date,
                log_count=item["log_count"],
                span_count=item.get("span_count", 0),
                metric_point_count=item.get("metric_point_count", 0),
                logs_daily_quota=logs_daily_quota,
                spans_daily_quota=item.get("spans_daily_quota", 0),
                metrics_daily_quota=item.get("metrics_daily_quota", 0),
                logs_quota_used_percent=logs_quota_used_percent,
                spans_quota_used_percent=item.get("spans_quota_used_percent", 0.0),
                metrics_quota_used_percent=item.get("metrics_quota_used_percent", 0.0),
            )
        )

    return schemas.UsageStatsResponse(project_id=project_id, usage=usage_stats)
