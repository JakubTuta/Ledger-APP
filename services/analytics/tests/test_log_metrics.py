import datetime as dt
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


async def _run(rows: list[tuple]) -> AsyncMock:
    mock_session = _mock_session(rows)
    with patch("analytics_workers.database.get_logs_session", return_value=mock_session):
        await log_metrics_job.aggregate_log_metrics()
    return mock_session


def _volume_insert_params(mock_session: AsyncMock) -> list[dict]:
    call = next(
        c
        for c in mock_session.execute.call_args_list
        if "INSERT INTO log_volume_5m" in str(c[0][0])
    )
    return call[0][1]


@pytest.mark.asyncio
async def test_aggregate_log_metrics_empty_database_writes_nothing():
    mock_session = await _run([])

    assert not any(
        "INSERT INTO log_volume_5m" in str(c[0][0]) for c in mock_session.execute.call_args_list
    )


@pytest.mark.asyncio
async def test_aggregate_log_metrics_writes_one_row_per_project_level_bucket():
    bucket = dt.datetime(2025, 10, 19, 14, 5, 0, tzinfo=dt.timezone.utc)
    rows = [
        (1, bucket, "error", 42),
        (1, bucket, "critical", 5),
        (1, bucket, "info", 1000),
        (2, bucket, "error", 12),
    ]

    params = _volume_insert_params(await _run(rows))

    assert {(p["project_id"], p["level"]): p["count"] for p in params} == {
        (1, "error"): 42,
        (1, "critical"): 5,
        (1, "info"): 1000,
        (2, "error"): 12,
    }
    assert all(p["bucket"] == bucket for p in params)


@pytest.mark.asyncio
async def test_unknown_levels_are_not_written_to_the_volume_rollup():
    bucket = dt.datetime(2025, 10, 19, 14, 5, 0, tzinfo=dt.timezone.utc)
    rows = [(1, bucket, "error", 10), (1, bucket, "info", 90), (1, bucket, "trace", 50)]

    params = _volume_insert_params(await _run(rows))

    assert {p["level"] for p in params} == {"error", "info"}
