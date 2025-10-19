import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import analytics_workers.jobs.usage_stats as usage_stats_job
import pytest


@pytest.mark.asyncio
async def test_generate_usage_stats_empty_database():
    mock_redis = AsyncMock()
    mock_logs_session = AsyncMock()
    mock_auth_session = AsyncMock()

    mock_projects_result = MagicMock()
    mock_projects_result.fetchall.return_value = []
    mock_auth_session.execute.return_value = mock_projects_result

    mock_logs_result = MagicMock()
    mock_logs_result.fetchall.return_value = []
    mock_logs_session.execute.return_value = mock_logs_result

    mock_logs_session.__aenter__ = AsyncMock(return_value=mock_logs_session)
    mock_logs_session.__aexit__ = AsyncMock()
    mock_auth_session.__aenter__ = AsyncMock(return_value=mock_auth_session)
    mock_auth_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch(
            "analytics_workers.database.get_logs_session"
        ) as mock_get_logs_session:
            with patch(
                "analytics_workers.database.get_auth_session"
            ) as mock_get_auth_session:
                mock_get_logs_session.return_value = mock_logs_session
                mock_get_auth_session.return_value = mock_auth_session
                await usage_stats_job.generate_usage_stats()

    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_generate_usage_stats_with_data():
    mock_redis = AsyncMock()
    mock_logs_session = AsyncMock()
    mock_auth_session = AsyncMock()

    mock_projects_result = MagicMock()
    mock_projects_result.fetchall.return_value = [
        (1, 1_000_000),
        (2, 500_000),
    ]
    mock_auth_session.execute.return_value = mock_projects_result

    test_date = date(2025, 10, 19)
    mock_logs_result = MagicMock()
    mock_logs_result.fetchall.return_value = [
        (1, test_date, 847_291),
        (2, test_date, 250_000),
    ]
    mock_logs_session.execute.return_value = mock_logs_result

    mock_logs_session.__aenter__ = AsyncMock(return_value=mock_logs_session)
    mock_logs_session.__aexit__ = AsyncMock()
    mock_auth_session.__aenter__ = AsyncMock(return_value=mock_auth_session)
    mock_auth_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch(
            "analytics_workers.database.get_logs_session"
        ) as mock_get_logs_session:
            with patch(
                "analytics_workers.database.get_auth_session"
            ) as mock_get_auth_session:
                mock_get_logs_session.return_value = mock_logs_session
                mock_get_auth_session.return_value = mock_auth_session
                await usage_stats_job.generate_usage_stats()

    assert mock_redis.setex.call_count == 2

    first_call_args = mock_redis.setex.call_args_list[0][0]
    assert first_call_args[0] == "metrics:usage_stats:1"
    assert first_call_args[1] == 3600

    cached_data = json.loads(first_call_args[2])
    assert len(cached_data) == 1
    assert cached_data[0]["date"] == test_date.isoformat()
    assert cached_data[0]["log_count"] == 847_291
    assert cached_data[0]["daily_quota"] == 1_000_000
    assert cached_data[0]["quota_used_percent"] == 84.73


@pytest.mark.asyncio
async def test_generate_usage_stats_quota_calculations():
    mock_redis = AsyncMock()
    mock_logs_session = AsyncMock()
    mock_auth_session = AsyncMock()

    mock_projects_result = MagicMock()
    mock_projects_result.fetchall.return_value = [(1, 1_000_000)]
    mock_auth_session.execute.return_value = mock_projects_result

    test_date = date(2025, 10, 19)
    mock_logs_result = MagicMock()
    mock_logs_result.fetchall.return_value = [
        (1, test_date, 1_500_000),
    ]
    mock_logs_session.execute.return_value = mock_logs_result

    mock_logs_session.__aenter__ = AsyncMock(return_value=mock_logs_session)
    mock_logs_session.__aexit__ = AsyncMock()
    mock_auth_session.__aenter__ = AsyncMock(return_value=mock_auth_session)
    mock_auth_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch(
            "analytics_workers.database.get_logs_session"
        ) as mock_get_logs_session:
            with patch(
                "analytics_workers.database.get_auth_session"
            ) as mock_get_auth_session:
                mock_get_logs_session.return_value = mock_logs_session
                mock_get_auth_session.return_value = mock_auth_session
                await usage_stats_job.generate_usage_stats()

    cached_data = json.loads(mock_redis.setex.call_args_list[0][0][2])
    assert cached_data[0]["quota_used_percent"] == 150.0


@pytest.mark.asyncio
async def test_generate_usage_stats_multiple_days():
    mock_redis = AsyncMock()
    mock_logs_session = AsyncMock()
    mock_auth_session = AsyncMock()

    mock_projects_result = MagicMock()
    mock_projects_result.fetchall.return_value = [(1, 1_000_000)]
    mock_auth_session.execute.return_value = mock_projects_result

    date1 = date(2025, 10, 19)
    date2 = date(2025, 10, 18)
    date3 = date(2025, 10, 17)

    mock_logs_result = MagicMock()
    mock_logs_result.fetchall.return_value = [
        (1, date1, 800_000),
        (1, date2, 900_000),
        (1, date3, 750_000),
    ]
    mock_logs_session.execute.return_value = mock_logs_result

    mock_logs_session.__aenter__ = AsyncMock(return_value=mock_logs_session)
    mock_logs_session.__aexit__ = AsyncMock()
    mock_auth_session.__aenter__ = AsyncMock(return_value=mock_auth_session)
    mock_auth_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch(
            "analytics_workers.database.get_logs_session"
        ) as mock_get_logs_session:
            with patch(
                "analytics_workers.database.get_auth_session"
            ) as mock_get_auth_session:
                mock_get_logs_session.return_value = mock_logs_session
                mock_get_auth_session.return_value = mock_auth_session
                await usage_stats_job.generate_usage_stats()

    cached_data = json.loads(mock_redis.setex.call_args_list[0][0][2])
    assert len(cached_data) == 3


