import datetime
import hashlib
import json

import pytest
import sqlalchemy as sa

import query_service.database as database
import query_service.proto.query_pb2 as query_pb2
import tests.test_base as test_base

_SUM = 0
_GAUGE = 1
_HISTOGRAM = 2

_DELTA = 1
_CUMULATIVE = 2

_INSERT = sa.text("""
    INSERT INTO metric_points
        (project_id, name, type, ts, value, count, sum, bucket_counts,
         explicit_bounds, tags, tags_hash, service_name, temporality)
    VALUES
        (:project_id, :name, :type, :ts, :value, :count, :sum,
         CAST(:bucket_counts AS jsonb), CAST(:explicit_bounds AS jsonb),
         CAST(:tags AS jsonb), :tags_hash, :service_name, :temporality)
""")

_INSERT_ROLLUP = sa.text("""
    INSERT INTO metric_points_1h
        (project_id, name, type, tags_hash, tags, bucket, count, sum_v,
         min_v, max_v, avg_v, temporality)
    VALUES
        (:project_id, :name, :type, :tags_hash, CAST(:tags AS jsonb), :bucket,
         :count, :sum_v, :min_v, :max_v, :avg_v, :temporality)
""")


def _tags_hash(tags: dict) -> str:
    canonical = json.dumps(tags, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode(), digest_size=8).hexdigest()


class MetricPointFixtures(test_base.BaseQueryTest):
    async def _insert_point(
        self,
        name: str,
        ts: datetime.datetime,
        *,
        project_id: int = 1,
        metric_type: int = _GAUGE,
        value: float | None = None,
        count: int | None = None,
        total: float | None = None,
        bucket_counts: list | None = None,
        explicit_bounds: list | None = None,
        tags: dict | None = None,
        temporality: int | None = None,
    ) -> None:
        tags = tags or {}
        async with database.get_logs_session() as session:
            await session.execute(
                _INSERT,
                {
                    "project_id": project_id,
                    "name": name,
                    "type": metric_type,
                    "ts": ts,
                    "value": value,
                    "count": count,
                    "sum": total,
                    "bucket_counts": json.dumps(bucket_counts)
                    if bucket_counts is not None
                    else None,
                    "explicit_bounds": json.dumps(explicit_bounds)
                    if explicit_bounds is not None
                    else None,
                    "tags": json.dumps(tags),
                    "tags_hash": _tags_hash(tags),
                    "service_name": "test-service",
                    "temporality": temporality,
                },
            )
            await session.commit()

    async def _insert_rollup(
        self,
        name: str,
        bucket: datetime.datetime,
        *,
        project_id: int = 1,
        metric_type: int = _GAUGE,
        count: int = 0,
        sum_v: float = 0.0,
        min_v: float | None = None,
        max_v: float | None = None,
        avg_v: float | None = None,
        tags: dict | None = None,
    ) -> None:
        tags = tags or {}
        async with database.get_logs_session() as session:
            await session.execute(
                _INSERT_ROLLUP,
                {
                    "project_id": project_id,
                    "name": name,
                    "type": metric_type,
                    "tags_hash": _tags_hash(tags),
                    "tags": json.dumps(tags),
                    "bucket": bucket,
                    "count": count,
                    "sum_v": sum_v,
                    "min_v": min_v,
                    "max_v": max_v,
                    "avg_v": avg_v,
                    "temporality": None,
                },
            )
            await session.commit()


class TestListMetricNames(MetricPointFixtures):
    @pytest.mark.asyncio
    async def test_lists_names_with_type_tag_keys_and_series_count(self):
        now = datetime.datetime.now(datetime.timezone.utc)

        await self._insert_point(
            "queue_depth", now, value=5, tags={"queue": "emails"}, metric_type=_GAUGE
        )
        await self._insert_point(
            "queue_depth", now, value=9, tags={"queue": "billing"}, metric_type=_GAUGE
        )
        await self._insert_point(
            "orders_processed",
            now,
            value=3,
            tags={"region": "eu"},
            metric_type=_SUM,
            temporality=_DELTA,
        )

        response = await self.stub.ListMetricNames(
            query_pb2.ListMetricNamesRequest(
                project_id=1,
                from_time=(now - datetime.timedelta(hours=1)).isoformat(),
                to_time=(now + datetime.timedelta(minutes=1)).isoformat(),
            )
        )

        by_name = {metric.name: metric for metric in response.metrics}
        assert set(by_name) == {"queue_depth", "orders_processed"}

        assert by_name["queue_depth"].series_count == 2
        assert list(by_name["queue_depth"].tag_keys) == ["queue"]
        assert by_name["queue_depth"].type == _GAUGE

        assert by_name["orders_processed"].temporality == _DELTA
        assert by_name["orders_processed"].last_seen != ""

    @pytest.mark.asyncio
    async def test_excludes_other_projects(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        await self._insert_point("mine", now, value=1)
        await self._insert_point("theirs", now, value=1, project_id=2)

        response = await self.stub.ListMetricNames(
            query_pb2.ListMetricNamesRequest(project_id=1)
        )

        assert [metric.name for metric in response.metrics] == ["mine"]

    @pytest.mark.asyncio
    async def test_untagged_metric_reports_no_tag_keys(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        await self._insert_point("bare", now, value=1, tags={})

        response = await self.stub.ListMetricNames(
            query_pb2.ListMetricNamesRequest(project_id=1)
        )

        assert list(response.metrics[0].tag_keys) == []


class TestGetMetricTags(MetricPointFixtures):
    @pytest.mark.asyncio
    async def test_returns_keys_with_sample_values(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        for region, route in [("eu", "/a"), ("us", "/a"), ("eu", "/b")]:
            await self._insert_point(
                "latency", now, value=1, tags={"region": region, "route": route}
            )

        response = await self.stub.GetMetricTags(
            query_pb2.GetMetricTagsRequest(project_id=1, name="latency")
        )

        by_key = {entry.key: entry for entry in response.keys}
        assert set(by_key) == {"region", "route"}
        assert set(by_key["region"].values) == {"eu", "us"}
        assert set(by_key["route"].values) == {"/a", "/b"}
        assert by_key["region"].truncated is False

    @pytest.mark.asyncio
    async def test_caps_values_per_key_and_reports_truncation(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        for index in range(6):
            await self._insert_point(
                "latency",
                now - datetime.timedelta(seconds=index),
                value=1,
                tags={"user": f"u{index}"},
            )

        response = await self.stub.GetMetricTags(
            query_pb2.GetMetricTagsRequest(project_id=1, name="latency", max_values_per_key=3)
        )

        entry = response.keys[0]
        assert entry.key == "user"
        assert len(entry.values) == 3
        assert entry.truncated is True


class TestQueryMetricSeriesNumeric(MetricPointFixtures):
    @pytest.mark.asyncio
    async def test_gauge_avg_buckets_by_interval(self):
        base = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=datetime.timezone.utc)
        for offset, value in [(0, 10.0), (30, 20.0), (300, 60.0)]:
            await self._insert_point(
                "queue_depth", base + datetime.timedelta(seconds=offset), value=value
            )

        response = await self.stub.QueryMetricSeries(
            query_pb2.QueryMetricSeriesRequest(
                project_id=1,
                name="queue_depth",
                aggregation="avg",
                interval="5m",
                from_time=base.isoformat(),
                to_time=(base + datetime.timedelta(minutes=10)).isoformat(),
            )
        )

        assert len(response.series) == 1
        points = response.series[0].points
        assert [point.value for point in points] == [15.0, 60.0]
        assert response.interval == "5m"
        assert response.downsampled is False

    @pytest.mark.asyncio
    async def test_group_by_tag_splits_series(self):
        base = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=datetime.timezone.utc)
        await self._insert_point("latency", base, value=10.0, tags={"region": "eu"})
        await self._insert_point("latency", base, value=30.0, tags={"region": "us"})

        response = await self.stub.QueryMetricSeries(
            query_pb2.QueryMetricSeriesRequest(
                project_id=1,
                name="latency",
                aggregation="avg",
                interval="5m",
                group_by=["region"],
                from_time=base.isoformat(),
                to_time=(base + datetime.timedelta(minutes=5)).isoformat(),
            )
        )

        by_region = {
            series.tags["region"]: series.points[0].value for series in response.series
        }
        assert by_region == {"eu": 10.0, "us": 30.0}

    @pytest.mark.asyncio
    async def test_tag_filter_narrows_to_one_series(self):
        base = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=datetime.timezone.utc)
        await self._insert_point("latency", base, value=10.0, tags={"region": "eu"})
        await self._insert_point("latency", base, value=30.0, tags={"region": "us"})

        request = query_pb2.QueryMetricSeriesRequest(
            project_id=1,
            name="latency",
            aggregation="avg",
            interval="5m",
            from_time=base.isoformat(),
            to_time=(base + datetime.timedelta(minutes=5)).isoformat(),
        )
        request.tag_filters["region"] = "eu"

        response = await self.stub.QueryMetricSeries(request)

        assert len(response.series) == 1
        assert response.series[0].points[0].value == 10.0

    @pytest.mark.asyncio
    async def test_delta_counter_sums_within_bucket(self):
        base = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=datetime.timezone.utc)
        for offset, value in [(0, 2.0), (60, 3.0), (120, 5.0)]:
            await self._insert_point(
                "orders",
                base + datetime.timedelta(seconds=offset),
                value=value,
                metric_type=_SUM,
                temporality=_DELTA,
            )

        response = await self.stub.QueryMetricSeries(
            query_pb2.QueryMetricSeriesRequest(
                project_id=1,
                name="orders",
                aggregation="sum",
                interval="5m",
                from_time=base.isoformat(),
                to_time=(base + datetime.timedelta(minutes=5)).isoformat(),
            )
        )

        assert response.series[0].points[0].value == 10.0
        assert response.temporality == _DELTA

    @pytest.mark.asyncio
    async def test_cumulative_counter_is_differenced_not_summed(self):
        base = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=datetime.timezone.utc)
        # A running total: 10 -> 14 -> 20 is an increase of 10 across the window,
        # not the 44 a naive SUM of the stored values would report.
        for offset, value in [(0, 10.0), (60, 14.0), (120, 20.0)]:
            await self._insert_point(
                "requests_total",
                base + datetime.timedelta(seconds=offset),
                value=value,
                metric_type=_SUM,
                temporality=_CUMULATIVE,
            )

        response = await self.stub.QueryMetricSeries(
            query_pb2.QueryMetricSeriesRequest(
                project_id=1,
                name="requests_total",
                aggregation="sum",
                interval="5m",
                from_time=base.isoformat(),
                to_time=(base + datetime.timedelta(minutes=5)).isoformat(),
            )
        )

        assert response.temporality == _CUMULATIVE
        assert response.series[0].points[0].value == 10.0

    @pytest.mark.asyncio
    async def test_counter_reset_counts_post_reset_value_as_increase(self):
        base = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=datetime.timezone.utc)
        # Process restarts after 20: the counter drops to 3, and that 3 is the
        # traffic since the reset rather than a negative increase.
        for offset, value in [(0, 10.0), (60, 20.0), (120, 3.0), (180, 7.0)]:
            await self._insert_point(
                "requests_total",
                base + datetime.timedelta(seconds=offset),
                value=value,
                metric_type=_SUM,
                temporality=_CUMULATIVE,
            )

        response = await self.stub.QueryMetricSeries(
            query_pb2.QueryMetricSeriesRequest(
                project_id=1,
                name="requests_total",
                aggregation="sum",
                interval="5m",
                from_time=base.isoformat(),
                to_time=(base + datetime.timedelta(minutes=5)).isoformat(),
            )
        )

        # 10 (first point, no predecessor -> 0) + 10 + 3 + 4
        assert response.series[0].points[0].value == 17.0

    @pytest.mark.asyncio
    async def test_rejects_unknown_aggregation(self):
        import grpc

        base = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=datetime.timezone.utc)
        await self._insert_point("queue_depth", base, value=1.0)

        with pytest.raises(grpc.RpcError) as exc_info:
            await self.stub.QueryMetricSeries(
                query_pb2.QueryMetricSeriesRequest(
                    project_id=1, name="queue_depth", aggregation="median"
                )
            )

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT


class TestQueryMetricSeriesHistogram(MetricPointFixtures):
    @pytest.mark.asyncio
    async def test_quantile_interpolated_from_buckets(self):
        base = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=datetime.timezone.utc)
        await self._insert_point(
            "request_duration_ms",
            base,
            metric_type=_HISTOGRAM,
            count=10,
            total=340.0,
            bucket_counts=[2, 5, 2, 1],
            explicit_bounds=[10, 50, 100],
            temporality=_DELTA,
        )

        response = await self.stub.QueryMetricSeries(
            query_pb2.QueryMetricSeriesRequest(
                project_id=1,
                name="request_duration_ms",
                aggregation="p50",
                interval="5m",
                from_time=base.isoformat(),
                to_time=(base + datetime.timedelta(minutes=5)).isoformat(),
            )
        )

        assert response.type == _HISTOGRAM
        # target 5 falls in the (10, 50] bucket, 3/5 of the way through it
        assert response.series[0].points[0].value == pytest.approx(34.0)

    @pytest.mark.asyncio
    async def test_distribution_returned_alongside_series(self):
        base = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=datetime.timezone.utc)
        for offset in (0, 60):
            await self._insert_point(
                "request_duration_ms",
                base + datetime.timedelta(seconds=offset),
                metric_type=_HISTOGRAM,
                count=4,
                total=100.0,
                bucket_counts=[1, 2, 1, 0],
                explicit_bounds=[10, 50, 100],
            )

        response = await self.stub.QueryMetricSeries(
            query_pb2.QueryMetricSeriesRequest(
                project_id=1,
                name="request_duration_ms",
                aggregation="avg",
                interval="5m",
                from_time=base.isoformat(),
                to_time=(base + datetime.timedelta(minutes=5)).isoformat(),
            )
        )

        assert len(response.histograms) == 1
        histogram = response.histograms[0]
        assert histogram.count == 8
        assert histogram.sum == pytest.approx(200.0)
        # element-wise sum of the two points' bucket_counts
        assert [bucket.count for bucket in histogram.buckets] == [2.0, 4.0, 2.0, 0.0]
        assert histogram.buckets[-1].upper_bound == float("inf")

    @pytest.mark.asyncio
    async def test_avg_uses_sum_over_count(self):
        base = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=datetime.timezone.utc)
        await self._insert_point(
            "request_duration_ms",
            base,
            metric_type=_HISTOGRAM,
            count=4,
            total=200.0,
            bucket_counts=[1, 2, 1, 0],
            explicit_bounds=[10, 50, 100],
        )

        response = await self.stub.QueryMetricSeries(
            query_pb2.QueryMetricSeriesRequest(
                project_id=1,
                name="request_duration_ms",
                aggregation="avg",
                interval="5m",
                from_time=base.isoformat(),
                to_time=(base + datetime.timedelta(minutes=5)).isoformat(),
            )
        )

        assert response.series[0].points[0].value == pytest.approx(50.0)


class TestQueryMetricSeriesRollup(MetricPointFixtures):
    @pytest.mark.asyncio
    async def test_long_window_reads_the_hourly_rollup(self):
        base = datetime.datetime(2026, 8, 1, 0, 0, tzinfo=datetime.timezone.utc)
        for hour, (count, total) in enumerate([(2, 20.0), (4, 60.0)]):
            await self._insert_rollup(
                "queue_depth",
                base + datetime.timedelta(hours=hour),
                count=count,
                sum_v=total,
                min_v=5.0,
                max_v=25.0,
                avg_v=total / count,
            )
        # A raw point the rollup does not contain - if the query read the raw
        # table instead, this value would show up in the result.
        await self._insert_point("queue_depth", base, value=999.0)

        response = await self.stub.QueryMetricSeries(
            query_pb2.QueryMetricSeriesRequest(
                project_id=1,
                name="queue_depth",
                aggregation="avg",
                interval="1h",
                from_time=base.isoformat(),
                to_time=(base + datetime.timedelta(days=5)).isoformat(),
            )
        )

        assert response.downsampled is True
        assert [point.value for point in response.series[0].points] == [10.0, 15.0]

    @pytest.mark.asyncio
    async def test_percentile_over_long_window_stays_on_raw_points(self):
        base = datetime.datetime(2026, 8, 1, 0, 0, tzinfo=datetime.timezone.utc)
        await self._insert_rollup("queue_depth", base, count=1, sum_v=1.0, avg_v=1.0)
        await self._insert_point("queue_depth", base, value=42.0)

        response = await self.stub.QueryMetricSeries(
            query_pb2.QueryMetricSeriesRequest(
                project_id=1,
                name="queue_depth",
                aggregation="p95",
                interval="1h",
                from_time=base.isoformat(),
                to_time=(base + datetime.timedelta(days=5)).isoformat(),
            )
        )

        assert response.downsampled is False
        assert response.series[0].points[0].value == pytest.approx(42.0)
