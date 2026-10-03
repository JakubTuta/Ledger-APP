import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import analytics_workers.database as database
import analytics_workers.jobs.usage_stats as usage_stats_job
import pytest
import sqlalchemy as sa


def _empty_result() -> MagicMock:
    result = MagicMock()
    result.fetchall.return_value = []
    return result


def _result(rows) -> MagicMock:
    result = MagicMock()
    result.fetchall.return_value = list(rows)
    return result


def _auth_session(project_rows, persisted_rows=()) -> AsyncMock:
    """
    Auth-session mock that dispatches on the statement text rather than on call
    order: the job reads `projects` for quotas and `daily_usage` for the counts
    a previous run persisted, then upserts back into `daily_usage`.
    """
    session = AsyncMock()

    async def execute(query, params=None):
        sql = str(getattr(query, "text", query))
        if "FROM projects" in sql:
            return _result(project_rows)
        if "FROM daily_usage" in sql:
            return _result(persisted_rows)
        return _empty_result()

    session.execute = AsyncMock(side_effect=execute)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_generate_usage_stats_empty_database():
    mock_redis = AsyncMock()
    mock_logs_session = AsyncMock()
    mock_auth_session = _auth_session([])

    mock_logs_session.execute.return_value = _empty_result()

    mock_logs_session.__aenter__ = AsyncMock(return_value=mock_logs_session)
    mock_logs_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_logs_session:
            with patch("analytics_workers.database.get_auth_session") as mock_get_auth_session:
                mock_get_logs_session.return_value = mock_logs_session
                mock_get_auth_session.return_value = mock_auth_session
                await usage_stats_job.generate_usage_stats()

    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_generate_usage_stats_with_data():
    mock_redis = AsyncMock()
    mock_logs_session = AsyncMock()
    mock_auth_session = _auth_session(
        [
            (1, 1_000_000, 3_000_000, 1_000_000),
            (2, 500_000, 1_500_000, 500_000),
        ]
    )

    test_date = date(2025, 10, 19)
    mock_logs_result = MagicMock()
    mock_logs_result.fetchall.return_value = [
        (1, test_date, 847_291),
        (2, test_date, 250_000),
    ]
    mock_logs_session.execute.side_effect = [
        mock_logs_result,
        _empty_result(),
        _empty_result(),
    ]

    mock_logs_session.__aenter__ = AsyncMock(return_value=mock_logs_session)
    mock_logs_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_logs_session:
            with patch("analytics_workers.database.get_auth_session") as mock_get_auth_session:
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
    assert cached_data[0]["span_count"] == 0
    assert cached_data[0]["metric_point_count"] == 0
    assert cached_data[0]["logs_daily_quota"] == 1_000_000
    assert cached_data[0]["spans_daily_quota"] == 3_000_000
    assert cached_data[0]["metrics_daily_quota"] == 1_000_000
    assert cached_data[0]["logs_quota_used_percent"] == 84.73
    assert cached_data[0]["spans_quota_used_percent"] == 0
    assert cached_data[0]["metrics_quota_used_percent"] == 0


@pytest.mark.asyncio
async def test_generate_usage_stats_quota_calculations():
    mock_redis = AsyncMock()
    mock_logs_session = AsyncMock()
    mock_auth_session = _auth_session([(1, 1_000_000, 3_000_000, 1_000_000)])

    test_date = date(2025, 10, 19)
    mock_logs_result = MagicMock()
    mock_logs_result.fetchall.return_value = [
        (1, test_date, 1_500_000),
    ]
    mock_logs_session.execute.side_effect = [
        mock_logs_result,
        _empty_result(),
        _empty_result(),
    ]

    mock_logs_session.__aenter__ = AsyncMock(return_value=mock_logs_session)
    mock_logs_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_logs_session:
            with patch("analytics_workers.database.get_auth_session") as mock_get_auth_session:
                mock_get_logs_session.return_value = mock_logs_session
                mock_get_auth_session.return_value = mock_auth_session
                await usage_stats_job.generate_usage_stats()

    cached_data = json.loads(mock_redis.setex.call_args_list[0][0][2])
    assert cached_data[0]["logs_quota_used_percent"] == 150.0


@pytest.mark.asyncio
async def test_generate_usage_stats_multiple_days():
    mock_redis = AsyncMock()
    mock_logs_session = AsyncMock()
    mock_auth_session = _auth_session([(1, 1_000_000, 3_000_000, 1_000_000)])

    date1 = date(2025, 10, 19)
    date2 = date(2025, 10, 18)
    date3 = date(2025, 10, 17)

    mock_logs_result = MagicMock()
    mock_logs_result.fetchall.return_value = [
        (1, date1, 800_000),
        (1, date2, 900_000),
        (1, date3, 750_000),
    ]
    mock_logs_session.execute.side_effect = [
        mock_logs_result,
        _empty_result(),
        _empty_result(),
    ]

    mock_logs_session.__aenter__ = AsyncMock(return_value=mock_logs_session)
    mock_logs_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_logs_session:
            with patch("analytics_workers.database.get_auth_session") as mock_get_auth_session:
                mock_get_logs_session.return_value = mock_logs_session
                mock_get_auth_session.return_value = mock_auth_session
                await usage_stats_job.generate_usage_stats()

    cached_data = json.loads(mock_redis.setex.call_args_list[0][0][2])
    assert len(cached_data) == 3


@pytest.mark.asyncio
async def test_generate_usage_stats_spans_only_day_yields_zero_log_count():
    """A day with spans but no logs must still produce a usage entry with
    log_count: 0, not be silently dropped - regression test for the union-of-
    signals merge logic."""
    mock_redis = AsyncMock()
    mock_logs_session = AsyncMock()
    mock_auth_session = _auth_session([(1, 1_000_000, 3_000_000, 1_000_000)])

    test_date = date(2025, 10, 19)

    mock_spans_result = MagicMock()
    mock_spans_result.fetchall.return_value = [(1, test_date, 4_567)]

    mock_logs_session.execute.side_effect = [
        _empty_result(),
        mock_spans_result,
        _empty_result(),
    ]

    mock_logs_session.__aenter__ = AsyncMock(return_value=mock_logs_session)
    mock_logs_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_logs_session:
            with patch("analytics_workers.database.get_auth_session") as mock_get_auth_session:
                mock_get_logs_session.return_value = mock_logs_session
                mock_get_auth_session.return_value = mock_auth_session
                await usage_stats_job.generate_usage_stats()

    cached_data = json.loads(mock_redis.setex.call_args_list[0][0][2])
    assert len(cached_data) == 1
    assert cached_data[0]["log_count"] == 0
    assert cached_data[0]["span_count"] == 4_567


@pytest.mark.asyncio
async def test_generate_usage_stats_keeps_persisted_counts_outside_recompute_window():
    """
    Spans and metric points are only recomputed for the last couple of days, so
    an older day's counts must come from what a previous run persisted rather
    than being reset to 0.
    """
    mock_redis = AsyncMock()
    mock_logs_session = AsyncMock()

    old_date = date(2025, 10, 1)
    mock_auth_session = _auth_session(
        [(1, 1_000_000, 3_000_000, 1_000_000)],
        persisted_rows=[(1, old_date, 500, 4_567, 89)],
    )

    # log_volume_1d still covers the full 30 days; spans/metric points do not.
    mock_logs_session.execute.side_effect = [
        _result([(1, old_date, 500)]),
        _empty_result(),
        _empty_result(),
    ]

    mock_logs_session.__aenter__ = AsyncMock(return_value=mock_logs_session)
    mock_logs_session.__aexit__ = AsyncMock()

    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        with patch("analytics_workers.database.get_logs_session") as mock_get_logs_session:
            with patch("analytics_workers.database.get_auth_session") as mock_get_auth_session:
                mock_get_logs_session.return_value = mock_logs_session
                mock_get_auth_session.return_value = mock_auth_session
                await usage_stats_job.generate_usage_stats()

    cached_data = json.loads(mock_redis.setex.call_args_list[0][0][2])
    assert len(cached_data) == 1
    assert cached_data[0]["log_count"] == 500
    assert cached_data[0]["span_count"] == 4_567
    assert cached_data[0]["metric_point_count"] == 89


async def _seed_project(auth_session) -> int:
    result = await auth_session.execute(
        sa.text("""
            INSERT INTO accounts
                (email, password_hash, name, plan, status, email_verified, created_at, updated_at)
            VALUES
                ('usage@example.com', 'x', 'Usage Owner', 'free', 'active', TRUE, NOW(), NOW())
            RETURNING id
        """)
    )
    account_id = result.scalar()

    result = await auth_session.execute(
        sa.text("""
            INSERT INTO projects
                (account_id, name, slug, environment, retention_days, logs_daily_quota,
                 spans_daily_quota, metrics_daily_quota, created_at, updated_at)
            VALUES
                (:account_id, 'Usage Project', 'usage-project', 'production', 30, 100000,
                 300000, 100000, NOW(), NOW())
            RETURNING id
        """),
        {"account_id": account_id},
    )
    project_id = result.scalar()
    await auth_session.commit()
    return project_id


@pytest.mark.asyncio
async def test_generate_usage_stats_caches_counts_read_from_the_real_rollup(test_dbs):
    """
    SUM() over the BIGINT rollup column reaches Python as Decimal, which json
    cannot encode. The job used to raise on every run, so the cache was never
    written and the usage history stayed empty. Mocked rows are plain ints and
    could never catch it, hence a real database here.
    """
    async with database.get_auth_session() as auth_session:
        project_id = await _seed_project(auth_session)

    day = (datetime.now(timezone.utc) - timedelta(days=3)).date()
    async with database.get_logs_session() as logs_session:
        await logs_session.execute(
            sa.text(
                "INSERT INTO log_volume_1d (project_id, level, bucket, count) "
                "VALUES (:p, 'info', :d, 700), (:p, 'error', :d, 42)"
            ),
            {"p": project_id, "d": day},
        )
        await logs_session.commit()

    mock_redis = AsyncMock()
    with patch("analytics_workers.redis_client.get_redis", return_value=mock_redis):
        await usage_stats_job.generate_usage_stats()

    cache_key, _ttl, payload = mock_redis.setex.call_args[0]
    assert cache_key == f"metrics:usage_stats:{project_id}"

    [entry] = json.loads(payload)
    assert entry["date"] == day.isoformat()
    assert entry["log_count"] == 742
    assert entry["logs_quota_used_percent"] == 0.74
