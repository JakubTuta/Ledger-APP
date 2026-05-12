import datetime
import json

import sqlalchemy as sa

import query_service.database as database
import query_service.redis_client as redis_client
import query_service.schemas as schemas

_6H = datetime.timedelta(hours=6)
_7D = datetime.timedelta(days=7)


async def get_error_rate(
    project_id: int,
    interval: str = "5min",
    start_time: datetime.datetime | None = None,
    end_time: datetime.datetime | None = None,
) -> schemas.ErrorRateResponse:
    if start_time and end_time:
        return await _get_error_rate_from_db(project_id, start_time, end_time)
    return await _get_error_rate_from_redis(project_id, interval, start_time, end_time)


async def _get_error_rate_from_redis(
    project_id: int,
    interval: str,
    start_time: datetime.datetime | None,
    end_time: datetime.datetime | None,
) -> schemas.ErrorRateResponse:
    redis = redis_client.get_redis()
    cache_key = f"metrics:error_rate:{project_id}:{interval}"
    cached_data = await redis.get(cache_key)

    if not cached_data:
        return schemas.ErrorRateResponse(project_id=project_id, interval=interval, data=[])

    cached_dict = json.loads(cached_data)

    if isinstance(cached_dict, dict) and "data" in cached_dict:
        data = cached_dict["data"]
    else:
        data = cached_dict if isinstance(cached_dict, list) else []

    error_rate_data = [
        schemas.ErrorRateData(
            timestamp=datetime.datetime.fromisoformat(item["timestamp"]),
            error_count=item["error_count"],
            critical_count=item["critical_count"],
        )
        for item in data
    ]

    if start_time or end_time:
        error_rate_data = [
            item for item in error_rate_data
            if (not start_time or item.timestamp >= start_time)
            and (not end_time or item.timestamp <= end_time)
        ]

    return schemas.ErrorRateResponse(
        project_id=project_id, interval=interval, data=error_rate_data
    )


async def _get_error_rate_from_db(
    project_id: int,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
) -> schemas.ErrorRateResponse:
    async with database.get_logs_session() as session:
        result = await session.execute(
            sa.text(
                """
                SELECT bucket, errors, total, ratio
                FROM error_rate_5m
                WHERE project_id = :pid
                  AND bucket >= :start
                  AND bucket <= :end
                ORDER BY bucket
                """
            ),
            {"pid": project_id, "start": start_time, "end": end_time},
        )
        rows = result.fetchall()

    data = [
        schemas.ErrorRateData(
            timestamp=row[0],
            error_count=row[1],
            critical_count=0,
        )
        for row in rows
    ]
    return schemas.ErrorRateResponse(project_id=project_id, interval="5min", data=data)


async def get_log_volume(
    project_id: int,
    interval: str = "1hour",
    start_time: datetime.datetime | None = None,
    end_time: datetime.datetime | None = None,
) -> schemas.LogVolumeResponse:
    if start_time and end_time:
        return await _get_log_volume_from_db(project_id, start_time, end_time)
    return await _get_log_volume_from_redis(project_id, interval, start_time, end_time)


async def _get_log_volume_from_redis(
    project_id: int,
    interval: str,
    start_time: datetime.datetime | None,
    end_time: datetime.datetime | None,
) -> schemas.LogVolumeResponse:
    redis = redis_client.get_redis()
    cache_key = f"metrics:log_volume:{project_id}:{interval}"
    cached_data = await redis.get(cache_key)

    if not cached_data:
        return schemas.LogVolumeResponse(project_id=project_id, interval=interval, data=[])

    cached_dict = json.loads(cached_data)

    if isinstance(cached_dict, dict) and "data" in cached_dict:
        data = cached_dict["data"]
    else:
        data = cached_dict if isinstance(cached_dict, list) else []

    log_volume_data = [
        schemas.LogVolumeData(
            timestamp=datetime.datetime.fromisoformat(item["timestamp"]),
            debug=item.get("debug", 0),
            info=item.get("info", 0),
            warning=item.get("warning", 0),
            error=item.get("error", 0),
            critical=item.get("critical", 0),
        )
        for item in data
    ]

    if start_time or end_time:
        log_volume_data = [
            item for item in log_volume_data
            if (not start_time or item.timestamp >= start_time)
            and (not end_time or item.timestamp <= end_time)
        ]

    return schemas.LogVolumeResponse(
        project_id=project_id, interval=interval, data=log_volume_data
    )


async def _get_log_volume_from_db(
    project_id: int,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
) -> schemas.LogVolumeResponse:
    span = end_time - start_time
    if span <= _6H:
        table = "log_volume_5m"
        resolved_interval = "5min"
    elif span <= _7D:
        table = "log_volume_1h"
        resolved_interval = "1hour"
    else:
        table = "log_volume_1d"
        resolved_interval = "1day"

    if table == "log_volume_1d":
        bucket_col = "bucket::timestamptz AS bucket"
        start_cast = ":start::date"
        end_cast = ":end::date"
    else:
        bucket_col = "bucket"
        start_cast = ":start"
        end_cast = ":end"

    async with database.get_logs_session() as session:
        result = await session.execute(
            sa.text(
                f"""
                SELECT {bucket_col},
                    SUM(count) FILTER (WHERE level = 'debug')    AS debug,
                    SUM(count) FILTER (WHERE level = 'info')     AS info,
                    SUM(count) FILTER (WHERE level = 'warning')  AS warning,
                    SUM(count) FILTER (WHERE level = 'error')    AS error,
                    SUM(count) FILTER (WHERE level = 'critical') AS critical
                FROM {table}
                WHERE project_id = :pid
                  AND bucket >= {start_cast}
                  AND bucket <= {end_cast}
                GROUP BY bucket
                ORDER BY bucket
                """
            ),
            {"pid": project_id, "start": start_time, "end": end_time},
        )
        rows = result.fetchall()

    data = [
        schemas.LogVolumeData(
            timestamp=row[0],
            debug=row[1] or 0,
            info=row[2] or 0,
            warning=row[3] or 0,
            error=row[4] or 0,
            critical=row[5] or 0,
        )
        for row in rows
    ]
    return schemas.LogVolumeResponse(
        project_id=project_id, interval=resolved_interval, data=data
    )


async def get_top_errors(
    project_id: int,
    limit: int = 10,
    start_time: datetime.datetime | None = None,
    end_time: datetime.datetime | None = None,
    status: str | None = None,
) -> schemas.TopErrorsResponse:
    redis = redis_client.get_redis()

    cache_key = f"metrics:top_errors:{project_id}"

    cached_data = await redis.get(cache_key)

    if not cached_data:
        return schemas.TopErrorsResponse(project_id=project_id, errors=[])

    cached_dict = json.loads(cached_data)

    if isinstance(cached_dict, dict) and "errors" in cached_dict:
        data = cached_dict["errors"]
    elif isinstance(cached_dict, dict) and "data" in cached_dict:
        data = cached_dict["data"]
    else:
        data = cached_dict if isinstance(cached_dict, list) else []

    errors = []
    for item in data:
        first_seen = datetime.datetime.fromisoformat(item["first_seen"])
        last_seen = datetime.datetime.fromisoformat(item["last_seen"])

        if start_time and last_seen < start_time:
            continue
        if end_time and first_seen > end_time:
            continue
        if status and item["status"] != status:
            continue

        errors.append(
            schemas.TopErrorData(
                fingerprint=item["fingerprint"],
                error_type=item["error_type"],
                error_message=item.get("error_message"),
                occurrence_count=item["occurrence_count"],
                first_seen=first_seen,
                last_seen=last_seen,
                status=item["status"],
                sample_log_id=item.get("sample_log_id"),
            )
        )

    errors = errors[:limit]

    return schemas.TopErrorsResponse(project_id=project_id, errors=errors)


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
        daily_quota = cached_dict.get("daily_quota", 0)
    elif isinstance(cached_dict, dict) and "data" in cached_dict:
        data = cached_dict["data"]
        daily_quota = cached_dict.get("daily_quota", 0)
    else:
        data = cached_dict if isinstance(cached_dict, list) else []
        daily_quota = 0

    usage_stats = []
    for item in data:
        usage_date = datetime.date.fromisoformat(item["date"])

        if start_date and usage_date < start_date:
            continue
        if end_date and usage_date > end_date:
            continue

        item_daily_quota = item.get("daily_quota", daily_quota)

        usage_stats.append(
            schemas.UsageStatsData(
                date=usage_date,
                log_count=item["log_count"],
                daily_quota=item_daily_quota,
                quota_used_percent=item["quota_used_percent"],
            )
        )

    return schemas.UsageStatsResponse(project_id=project_id, usage=usage_stats)
