import datetime
import hashlib
import json

import analytics_workers.database as database
import analytics_workers.jobs.metric_points_1h_rollup as rollup_job
import pytest
import sqlalchemy as sa

_SUM = 0
_GAUGE = 1
_HISTOGRAM = 2

_DELTA = 1
_CUMULATIVE = 2

# The job only scans back _DEFAULT_LOOKBACK from the watermark, so fixtures have
# to sit inside that window rather than at a fixed calendar date.
_BASE = (
    datetime.datetime.now(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0)
    - datetime.timedelta(hours=3)
)

_INSERT = sa.text("""
    INSERT INTO metric_points
        (project_id, name, type, ts, value, count, sum, bucket_counts,
         explicit_bounds, tags, tags_hash, service_name, temporality)
    VALUES
        (:project_id, :name, :type, :ts, :value, :count, :sum, NULL, NULL,
         CAST(:tags AS jsonb), :tags_hash, 'test-service', :temporality)
""")


def _tags_hash(tags: dict) -> str:
    canonical = json.dumps(tags, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode(), digest_size=8).hexdigest()


async def _insert_point(
    name: str,
    ts: datetime.datetime,
    *,
    metric_type: int = _GAUGE,
    value: float | None = None,
    count: int | None = None,
    total: float | None = None,
    tags: dict | None = None,
    temporality: int | None = None,
) -> None:
    tags = tags or {"region": "eu"}
    async with database.get_logs_session() as session:
        await session.execute(
            _INSERT,
            {
                "project_id": 1,
                "name": name,
                "type": metric_type,
                "ts": ts,
                "value": value,
                "count": count,
                "sum": total,
                "tags": json.dumps(tags),
                "tags_hash": _tags_hash(tags),
                "temporality": temporality,
            },
        )
        await session.commit()


async def _rollup_rows(name: str) -> list:
    async with database.get_logs_session() as session:
        result = await session.execute(
            sa.text("""
                SELECT bucket, count, sum_v, min_v, max_v, avg_v, type, temporality
                FROM metric_points_1h
                WHERE project_id = 1 AND name = :name
                ORDER BY bucket
            """),
            {"name": name},
        )
        return result.fetchall()


@pytest.mark.asyncio
class TestMetricPointsHourlyRollup:
    async def test_aggregates_gauge_points_per_hour(self, test_dbs):
        for minute, value in [(0, 10.0), (30, 20.0), (59, 30.0)]:
            await _insert_point(
                "queue_depth", _BASE + datetime.timedelta(minutes=minute), value=value
            )
        await _insert_point(
            "queue_depth", _BASE + datetime.timedelta(hours=1), value=100.0
        )

        await rollup_job.rollup_metric_points_1h()

        rows = await _rollup_rows("queue_depth")
        assert len(rows) == 2

        first = rows[0]
        assert first.count == 3
        assert first.sum_v == pytest.approx(60.0)
        assert first.min_v == pytest.approx(10.0)
        assert first.max_v == pytest.approx(30.0)
        assert first.avg_v == pytest.approx(20.0)

        assert rows[1].count == 1
        assert rows[1].avg_v == pytest.approx(100.0)

    async def test_separate_tag_combinations_stay_separate_series(self, test_dbs):
        await _insert_point("latency", _BASE, value=10.0, tags={"region": "eu"})
        await _insert_point("latency", _BASE, value=90.0, tags={"region": "us"})

        await rollup_job.rollup_metric_points_1h()

        rows = await _rollup_rows("latency")
        assert len(rows) == 2
        assert sorted(row.avg_v for row in rows) == [10.0, 90.0]

    async def test_histogram_rolls_up_the_mean_of_sum_over_count(self, test_dbs):
        # No `value` column on a histogram point - the rollup has to derive one
        # the same way the raw read path does, or the two disagree at the
        # rollup threshold.
        await _insert_point(
            "request_duration_ms",
            _BASE,
            metric_type=_HISTOGRAM,
            count=4,
            total=200.0,
        )

        await rollup_job.rollup_metric_points_1h()

        rows = await _rollup_rows("request_duration_ms")
        assert rows[0].avg_v == pytest.approx(50.0)
        assert rows[0].type == _HISTOGRAM

    async def test_temporality_is_carried_into_the_rollup(self, test_dbs):
        await _insert_point(
            "orders", _BASE, metric_type=_SUM, value=3.0, temporality=_DELTA
        )
        await _insert_point(
            "requests_total",
            _BASE,
            metric_type=_SUM,
            value=100.0,
            temporality=_CUMULATIVE,
        )

        await rollup_job.rollup_metric_points_1h()

        assert (await _rollup_rows("orders"))[0].temporality == _DELTA
        assert (await _rollup_rows("requests_total"))[0].temporality == _CUMULATIVE

    async def test_second_run_keeps_the_whole_hour_not_just_the_tail(self, test_dbs):
        """A run after the watermark must not overwrite an hour with a partial slice.

        ON CONFLICT replaces a bucket outright, so scanning from the raw
        watermark (a mid-hour timestamp) would rebuild the hour from only the
        points after it - three increments of 2 would read back as the last one
        alone.
        """
        # Two points in the first pass, so the watermark lands on the later of
        # them - strictly inside the hour and strictly after the first point.
        for minutes in (5, 10):
            await _insert_point(
                "orders",
                _BASE + datetime.timedelta(minutes=minutes),
                metric_type=_SUM,
                value=2.0,
                temporality=_DELTA,
            )
        await rollup_job.rollup_metric_points_1h()

        await _insert_point(
            "orders",
            _BASE + datetime.timedelta(minutes=40),
            metric_type=_SUM,
            value=2.0,
            temporality=_DELTA,
        )
        await rollup_job.rollup_metric_points_1h()

        rows = await _rollup_rows("orders")
        assert len(rows) == 1
        # Scanning from the raw watermark would drop the +5 point and report 2.
        assert rows[0].count == 3
        assert rows[0].sum_v == pytest.approx(6.0)

    async def test_rerun_updates_rather_than_duplicating(self, test_dbs):
        await _insert_point("queue_depth", _BASE, value=10.0)
        await rollup_job.rollup_metric_points_1h()

        # A late-arriving point in an hour already rolled up. The watermark is
        # per-job, so reset it to force the same window to be recomputed.
        async with database.get_logs_session() as session:
            await session.execute(
                sa.text("DELETE FROM rollup_job_state WHERE job_name = :name"),
                {"name": rollup_job._JOB_NAME},
            )
            await session.commit()

        await _insert_point(
            "queue_depth", _BASE + datetime.timedelta(minutes=5), value=30.0
        )
        await rollup_job.rollup_metric_points_1h()

        rows = await _rollup_rows("queue_depth")
        assert len(rows) == 1
        assert rows[0].count == 2
        assert rows[0].avg_v == pytest.approx(20.0)
