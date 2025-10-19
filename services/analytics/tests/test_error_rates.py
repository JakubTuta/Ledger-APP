import json
from unittest.mock import AsyncMock, MagicMock, patch

import analytics_workers.jobs.error_rates as error_rates_job
import pytest


@pytest.mark.asyncio
async def test_aggregate_error_rates_empty_database():
    mock_redis = AsyncMock()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_session:
            mock_get_session.return_value = mock_session
            await error_rates_job.aggregate_error_rates()

    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_aggregate_error_rates_with_data():
    from datetime import datetime, timezone

    mock_redis = AsyncMock()
    mock_session = AsyncMock()
    mock_result = MagicMock()

    test_timestamp = datetime(2025, 10, 19, 14, 30, 0, tzinfo=timezone.utc)
    mock_result.fetchall.return_value = [
        (1, test_timestamp, 42, 5),
        (1, test_timestamp, 38, 3),
        (2, test_timestamp, 12, 1),
    ]
    mock_session.execute.return_value = mock_result
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_session:
            mock_get_session.return_value = mock_session
            await error_rates_job.aggregate_error_rates()

    assert mock_redis.setex.call_count == 2

    first_call_args = mock_redis.setex.call_args_list[0][0]
    assert first_call_args[0] == "metrics:error_rate:1:5min"
    assert first_call_args[1] == 600

    cached_data = json.loads(first_call_args[2])
    assert len(cached_data) == 2
    assert cached_data[0]["error_count"] == 42
    assert cached_data[0]["critical_count"] == 5


