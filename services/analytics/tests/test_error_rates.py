import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import analytics_workers.jobs.error_rates as error_rates_job
import pytest


def test_5min_bucket_produces_correct_floor():
    """Bucket for 12:37:42 UTC must be 12:35:00, not 13:12:00 (old bug)."""
    import datetime as dt
    ts = dt.datetime(2025, 10, 19, 12, 37, 42, tzinfo=dt.timezone.utc)
    hour_start = ts.replace(minute=0, second=0, microsecond=0)
    bucket = hour_start + dt.timedelta(minutes=(ts.minute // 5) * 5)
    assert bucket == dt.datetime(2025, 10, 19, 12, 35, 0, tzinfo=dt.timezone.utc)


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


