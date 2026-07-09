import datetime as dt
import json
from unittest.mock import AsyncMock, MagicMock, patch

import analytics_workers.jobs.log_metrics as log_metrics_job
import pytest


def test_5min_bucket_produces_correct_floor():
    """Bucket for 12:37:42 UTC must floor to 12:35:00 (regression: hour count
    was previously crammed into a single 5-minute slot)."""
    ts = dt.datetime(2025, 10, 19, 12, 37, 42, tzinfo=dt.timezone.utc)
    hour_start = ts.replace(minute=0, second=0, microsecond=0)
    bucket = hour_start + dt.timedelta(minutes=(ts.minute // 5) * 5)
    assert bucket == dt.datetime(2025, 10, 19, 12, 35, 0, tzinfo=dt.timezone.utc)


def _mock_session(rows: list[tuple]):
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows
    mock_result.fetchone.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()
    return mock_session


@pytest.mark.asyncio
async def test_aggregate_log_metrics_empty_database():
    mock_redis = AsyncMock()
    mock_session = _mock_session([])

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_session:
            mock_get_session.return_value = mock_session
            await log_metrics_job.aggregate_log_metrics()

    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_aggregate_log_metrics_writes_volume_and_error_caches():
    mock_redis = AsyncMock()
    bucket = dt.datetime(2025, 10, 19, 14, 5, 0, tzinfo=dt.timezone.utc)
    rows = [
        (1, bucket, "error", 42),
        (1, bucket, "critical", 5),
        (1, bucket, "warning", 120),
        (1, bucket, "info", 1000),
        (1, bucket, "debug", 500),
        (2, bucket, "error", 12),
    ]
    mock_session = _mock_session(rows)

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_session:
            mock_get_session.return_value = mock_session
            await log_metrics_job.aggregate_log_metrics()

    cache = {call[0][0]: json.loads(call[0][2]) for call in mock_redis.setex.call_args_list}

    volume = cache["metrics:log_volume:1:1hour"]
    assert len(volume) == 1
    assert volume[0]["timestamp"].startswith("2025-10-19T14:00:00")
    assert volume[0]["error"] == 42
    assert volume[0]["critical"] == 5
    assert volume[0]["warning"] == 120
    assert volume[0]["info"] == 1000
    assert volume[0]["debug"] == 500

    error = cache["metrics:error_rate:1:5min"]
    assert len(error) == 1
    assert error[0]["error_count"] == 42
    assert error[0]["critical_count"] == 5
    assert error[0]["timestamp"].startswith("2025-10-19T14:05:00")

    assert "metrics:log_volume:2:1hour" in cache
    assert "metrics:error_rate:2:5min" in cache


@pytest.mark.asyncio
async def test_error_rate_total_includes_unknown_levels():
    """error_rate total must count every row (parity with old unfiltered scan),
    while log_volume only counts known levels."""
    mock_redis = AsyncMock()
    bucket = dt.datetime(2025, 10, 19, 14, 5, 0, tzinfo=dt.timezone.utc)
    rows = [
        (1, bucket, "error", 10),
        (1, bucket, "info", 90),
        (1, bucket, "trace", 50),
    ]
    mock_session = _mock_session(rows)

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_session:
            mock_get_session.return_value = mock_session
            await log_metrics_job.aggregate_log_metrics()

    error_rate_call = next(
        c
        for c in mock_session.execute.call_args_list
        if "INSERT INTO error_rate_5m" in str(c[0][0])
    )
    params = error_rate_call[0][1][0]
    assert params["errors"] == 10
    assert params["total"] == 150
    assert params["ratio"] == pytest.approx(10 / 150)

    volume_call = next(
        c
        for c in mock_session.execute.call_args_list
        if "INSERT INTO log_volume_5m" in str(c[0][0])
    )
    volume_params = volume_call[0][1]
    assert {p["level"] for p in volume_params} == {"error", "info"}
