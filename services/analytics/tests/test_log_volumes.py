import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import analytics_workers.jobs.log_volumes as log_volumes_job
import pytest


@pytest.mark.asyncio
async def test_aggregate_log_volumes_empty_database():
    mock_redis = AsyncMock()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_session.execute.return_value = mock_result
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_session:
            mock_get_session.return_value = mock_session
            await log_volumes_job.aggregate_log_volumes()

    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_aggregate_log_volumes_with_data():
    mock_redis = AsyncMock()
    mock_session = AsyncMock()
    mock_result = MagicMock()

    test_timestamp = datetime(2025, 10, 19, 14, 0, 0, tzinfo=timezone.utc)
    mock_result.fetchall.return_value = [
        (1, test_timestamp, "error", 42),
        (1, test_timestamp, "critical", 5),
        (1, test_timestamp, "warning", 120),
        (1, test_timestamp, "info", 1000),
        (1, test_timestamp, "debug", 500),
        (2, test_timestamp, "error", 12),
    ]
    mock_session.execute.return_value = mock_result
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_session:
            mock_get_session.return_value = mock_session
            await log_volumes_job.aggregate_log_volumes()

    assert mock_redis.setex.call_count == 2

    first_call_args = mock_redis.setex.call_args_list[0][0]
    assert first_call_args[0] == "metrics:log_volume:1:1hour"
    assert first_call_args[1] == 600

    cached_data = json.loads(first_call_args[2])
    assert len(cached_data) == 1
    assert cached_data[0]["error"] == 42
    assert cached_data[0]["critical"] == 5
    assert cached_data[0]["warning"] == 120
    assert cached_data[0]["info"] == 1000
    assert cached_data[0]["debug"] == 500


@pytest.mark.asyncio
async def test_aggregate_log_volumes_multiple_buckets():
    mock_redis = AsyncMock()
    mock_session = AsyncMock()
    mock_result = MagicMock()

    timestamp1 = datetime(2025, 10, 19, 14, 0, 0, tzinfo=timezone.utc)
    timestamp2 = datetime(2025, 10, 19, 13, 0, 0, tzinfo=timezone.utc)

    mock_result.fetchall.return_value = [
        (1, timestamp1, "error", 42),
        (1, timestamp1, "info", 1000),
        (1, timestamp2, "error", 38),
        (1, timestamp2, "info", 950),
    ]
    mock_session.execute.return_value = mock_result
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_session:
            mock_get_session.return_value = mock_session
            await log_volumes_job.aggregate_log_volumes()

    cached_data = json.loads(mock_redis.setex.call_args_list[0][0][2])
    assert len(cached_data) == 2


