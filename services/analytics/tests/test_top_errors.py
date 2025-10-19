import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import analytics_workers.jobs.top_errors as top_errors_job
import pytest


@pytest.mark.asyncio
async def test_compute_top_errors_empty_database():
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
            await top_errors_job.compute_top_errors()

    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_compute_top_errors_with_data():
    mock_redis = AsyncMock()
    mock_session = AsyncMock()
    mock_result = MagicMock()

    first_seen = datetime(2025, 10, 15, 8, 23, 15, tzinfo=timezone.utc)
    last_seen = datetime(2025, 10, 19, 14, 28, 42, tzinfo=timezone.utc)

    mock_result.fetchall.return_value = [
        (
            1,
            "a3f8b9c2d1e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0",
            "psycopg2.OperationalError",
            "could not connect to server",
            1247,
            first_seen,
            last_seen,
            "unresolved",
        ),
        (
            1,
            "b4a9c3d2e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
            "ValueError",
            "invalid literal for int()",
            892,
            first_seen,
            last_seen,
            "unresolved",
        ),
        (
            2,
            "c5b0d4e3f7g8h9i0j1k2l3m4n5o6p7q8r9s0t1u2v3w4x5y6z7a8b9c0d1e2f3",
            "KeyError",
            "missing key in dict",
            543,
            first_seen,
            last_seen,
            "unresolved",
        ),
    ]
    mock_session.execute.return_value = mock_result
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_session:
            mock_get_session.return_value = mock_session
            await top_errors_job.compute_top_errors()

    assert mock_redis.setex.call_count == 2

    first_call_args = mock_redis.setex.call_args_list[0][0]
    assert first_call_args[0] == "metrics:top_errors:1"
    assert first_call_args[1] == 900

    cached_data = json.loads(first_call_args[2])
    assert len(cached_data) == 2
    assert cached_data[0]["error_type"] == "psycopg2.OperationalError"
    assert cached_data[0]["occurrence_count"] == 1247
    assert cached_data[1]["error_type"] == "ValueError"
    assert cached_data[1]["occurrence_count"] == 892


@pytest.mark.asyncio
async def test_compute_top_errors_limits_to_50():
    mock_redis = AsyncMock()
    mock_session = AsyncMock()
    mock_result = MagicMock()

    first_seen = datetime(2025, 10, 15, 8, 23, 15, tzinfo=timezone.utc)
    last_seen = datetime(2025, 10, 19, 14, 28, 42, tzinfo=timezone.utc)

    errors = []
    for i in range(100):
        errors.append(
            (
                1,
                f"fingerprint_{i:064d}",
                f"ErrorType{i}",
                f"Error message {i}",
                1000 - i,
                first_seen,
                last_seen,
                "unresolved",
            )
        )

    mock_result.fetchall.return_value = errors
    mock_session.execute.return_value = mock_result
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_session:
            mock_get_session.return_value = mock_session
            await top_errors_job.compute_top_errors()

    cached_data = json.loads(mock_redis.setex.call_args_list[0][0][2])
    assert len(cached_data) == 50
    assert cached_data[0]["occurrence_count"] == 1000
    assert cached_data[49]["occurrence_count"] == 951


@pytest.mark.asyncio
async def test_compute_top_errors_multiple_projects():
    mock_redis = AsyncMock()
    mock_session = AsyncMock()
    mock_result = MagicMock()

    first_seen = datetime(2025, 10, 15, 8, 23, 15, tzinfo=timezone.utc)
    last_seen = datetime(2025, 10, 19, 14, 28, 42, tzinfo=timezone.utc)

    mock_result.fetchall.return_value = [
        (1, "fp1", "Error1", "msg1", 100, first_seen, last_seen, "unresolved"),
        (2, "fp2", "Error2", "msg2", 200, first_seen, last_seen, "unresolved"),
        (3, "fp3", "Error3", "msg3", 300, first_seen, last_seen, "unresolved"),
    ]
    mock_session.execute.return_value = mock_result
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_session:
            mock_get_session.return_value = mock_session
            await top_errors_job.compute_top_errors()

    assert mock_redis.setex.call_count == 3


