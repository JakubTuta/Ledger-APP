import datetime

import analytics_workers.database as database
import analytics_workers.jobs.alert_evaluator as alert_evaluator
import pytest
import sqlalchemy as sa

_PROJECT_ID = 1

_INSERT_LOGS = sa.text("""
    INSERT INTO logs
        (project_id, timestamp, ingested_at, level, log_type, importance, message,
         status_code, path)
    SELECT
        :pid,
        CAST(:start AS timestamptz) + make_interval(secs => g * :step),
        NOW(),
        CASE WHEN g < :failures AND :http = FALSE THEN 'error' ELSE 'info' END,
        CASE WHEN :http THEN 'endpoint' ELSE 'logger' END,
        'standard',
        'test message',
        CASE WHEN :http THEN
            CASE WHEN g < :failures THEN :failure_status ELSE 200 END
        END,
        CASE WHEN :http THEN '/orders' END
    FROM generate_series(0, :total - 1) AS g
""")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def _insert_logs(
    total: int,
    failures: int,
    *,
    http: bool = False,
    failure_status: int = 500,
    minutes_ago_start: float = 9,
    minutes_ago_end: float = 1,
) -> None:
    """`total` rows spread evenly over the window, the first `failures` of them failing."""
    start = _now() - datetime.timedelta(minutes=minutes_ago_start)
    span_seconds = (minutes_ago_start - minutes_ago_end) * 60
    async with database.get_logs_session() as session:
        await session.execute(
            _INSERT_LOGS,
            {
                "pid": _PROJECT_ID,
                "start": start,
                "step": span_seconds / total,
                "failures": failures,
                "failure_status": failure_status,
                "http": http,
                "total": total,
            },
        )
        await session.commit()


async def _insert_stale_partial_rollup_bucket(total: int, errors: int) -> None:
    """The row the 5-minute rollup job leaves for a bucket it wrote seconds after it opened."""
    now = _now()
    bucket = now.replace(second=0, microsecond=0) - datetime.timedelta(minutes=now.minute % 5)
    async with database.get_logs_session() as session:
        await session.execute(
            sa.text("""
                INSERT INTO error_rate_5m (project_id, bucket, errors, total, ratio)
                VALUES (:pid, :bucket, :errors, :total, :ratio)
            """),
            {
                "pid": _PROJECT_ID,
                "bucket": bucket,
                "errors": errors,
                "total": total,
                "ratio": errors / total,
            },
        )
        await session.execute(
            sa.text("""
                INSERT INTO log_volume_5m (project_id, level, bucket, count)
                VALUES (:pid, 'info', :bucket, :total)
            """),
            {"pid": _PROJECT_ID, "bucket": bucket, "total": total},
        )
        await session.commit()


async def _metric(metric: str) -> float | None:
    async with database.get_logs_session() as session:
        return await alert_evaluator._query_metric(metric, _PROJECT_ID, session)


@pytest.mark.asyncio
class TestErrorRateAll:
    async def test_is_the_rate_over_the_window_not_over_a_stale_rollup_sliver(self, test_dbs):
        await _insert_logs(total=170, failures=3)
        await _insert_stale_partial_rollup_bucket(total=8, errors=1)

        assert await _metric("error_rate_all") == pytest.approx(100 * 3 / 170)

    async def test_ignores_logs_older_than_the_window(self, test_dbs):
        await _insert_logs(total=100, failures=0)
        await _insert_logs(total=100, failures=100, minutes_ago_start=40, minutes_ago_end=30)

        assert await _metric("error_rate_all") == 0

    async def test_is_unknown_when_the_sample_is_too_small_to_judge(self, test_dbs):
        await _insert_logs(total=8, failures=1)

        assert await _metric("error_rate_all") is None

    async def test_is_unknown_when_nothing_was_logged(self, test_dbs):
        assert await _metric("error_rate_all") is None


@pytest.mark.asyncio
class TestHttpErrorRates:
    async def test_5xx_rate_over_enough_requests(self, test_dbs):
        await _insert_logs(total=100, failures=2, http=True, failure_status=500)

        assert await _metric("error_rate_5xx") == pytest.approx(2.0)

    async def test_4xx_rate_over_enough_requests(self, test_dbs):
        await _insert_logs(total=100, failures=5, http=True, failure_status=404)

        assert await _metric("error_rate_4xx") == pytest.approx(5.0)

    async def test_5xx_rate_does_not_count_client_errors(self, test_dbs):
        await _insert_logs(total=100, failures=30, http=True, failure_status=404)

        assert await _metric("error_rate_5xx") == 0

    @pytest.mark.parametrize("metric", ["error_rate_5xx", "error_rate_4xx"])
    async def test_rate_is_unknown_when_too_few_requests_were_made(self, test_dbs, metric):
        await _insert_logs(total=8, failures=1, http=True, failure_status=500)

        assert await _metric(metric) is None


@pytest.mark.asyncio
class TestRequestVolume:
    async def test_counts_logs_in_the_window_not_a_stale_rollup_sliver(self, test_dbs):
        await _insert_logs(total=50, failures=0)
        await _insert_logs(total=500, failures=0, minutes_ago_start=40, minutes_ago_end=30)
        await _insert_stale_partial_rollup_bucket(total=3, errors=0)

        assert await _metric("request_volume") == 50

    async def test_is_zero_when_nothing_was_logged(self, test_dbs):
        assert await _metric("request_volume") == 0
