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
_EXPONENTIAL_HISTOGRAM = 3
_SUMMARY = 4

_DELTA = 1
_CUMULATIVE = 2

_INSERT = sa.text("""
    INSERT INTO metric_points
        (project_id, name, type, ts, value, count, sum, bucket_counts,
         explicit_bounds, tags, tags_hash, service_name, temporality,
         exp_histogram, quantiles, exemplars)
    VALUES
        (:project_id, :name, :type, :ts, :value, :count, :sum,
         CAST(:bucket_counts AS jsonb), CAST(:explicit_bounds AS jsonb),
         CAST(:tags AS jsonb), :tags_hash, :service_name, :temporality,
         CAST(:exp_histogram AS jsonb), CAST(:quantiles AS jsonb),
         CAST(:exemplars AS jsonb))
""")

_INSERT_ROLLUP = sa.text("""
    INSERT INTO metric_points_1h
        (project_id, name, type, tags_hash, tags, bucket, count, sum_v,
         min_v, max_v, avg_v, temporality)
    VALUES
        (:project_id, :name, :type, :tags_hash, CAST(:tags AS jsonb), :bucket,
         :count, :sum_v, :min_v, :max_v, :avg_v, :temporality)
""")


def _json_or_none(value) -> str | None:
    return json.dumps(value) if value is not None else None


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
        exp_histogram: dict | None = None,
        quantiles: list | None = None,
        exemplars: list | None = None,
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
                    "exp_histogram": _json_or_none(exp_histogram),
                    "quantiles": _json_or_none(quantiles),
                    "exemplars": _json_or_none(exemplars),
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

        response = await self.stub.ListMetricNames(query_pb2.ListMetricNamesRequest(project_id=1))

        assert [metric.name for metric in response.metrics] == ["mine"]

    @pytest.mark.asyncio
    async def test_untagged_metric_reports_no_tag_keys(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        await self._insert_point("bare", now, value=1, tags={})

        response = await self.stub.ListMetricNames(query_pb2.ListMetricNamesRequest(project_id=1))

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

        by_region = {series.tags["region"]: series.points[0].value for series in response.series}
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


class TestQueryMetricSeriesDistributions(MetricPointFixtures):
    base = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=datetime.timezone.utc)

    async def _series(
        self, name: str, aggregation: str, **extra
    ) -> query_pb2.QueryMetricSeriesResponse:
        return await self.stub.QueryMetricSeries(
            query_pb2.QueryMetricSeriesRequest(
                project_id=1,
                name=name,
                aggregation=aggregation,
                interval="5m",
                from_time=self.base.isoformat(),
                to_time=(self.base + datetime.timedelta(minutes=5)).isoformat(),
                **extra,
            )
        )

    @pytest.mark.asyncio
    async def test_cumulative_histogram_is_differenced_not_summed(self):
        # Running totals 2 then 8: the window saw 6 requests, not 10.
        for offset, (count, total, counts) in enumerate(
            [(2, 20.0, [1, 1, 0, 0]), (8, 200.0, [3, 4, 1, 0])]
        ):
            await self._insert_point(
                "request_duration_ms",
                self.base + datetime.timedelta(seconds=60 * offset),
                metric_type=_HISTOGRAM,
                count=count,
                total=total,
                bucket_counts=counts,
                explicit_bounds=[10, 50, 100],
                temporality=_CUMULATIVE,
            )

        count = await self._series("request_duration_ms", "count")
        avg = await self._series("request_duration_ms", "avg")

        assert count.series[0].points[0].value == 6.0
        assert avg.series[0].points[0].value == pytest.approx(30.0)
        assert [b.count for b in count.histograms[0].buckets] == [2.0, 3.0, 1.0, 0.0]

    @pytest.mark.asyncio
    async def test_exponential_histogram_quantile(self):
        # scale 0: bucket i covers (2**i, 2**(i+1)]
        await self._insert_point(
            "request_duration_ms",
            self.base,
            metric_type=_EXPONENTIAL_HISTOGRAM,
            count=4,
            total=14.0,
            exp_histogram={
                "scale": 0,
                "zero_count": 0,
                "positive": {"offset": 0, "counts": [1, 2, 1]},
                "negative": {"offset": 0, "counts": []},
            },
            temporality=_DELTA,
        )

        response = await self._series("request_duration_ms", "p50")

        assert response.type == _EXPONENTIAL_HISTOGRAM
        # target 2 of 4: halfway through the (2, 4] bucket
        assert response.series[0].points[0].value == pytest.approx(3.0)
        assert [
            (b.lower_bound, b.upper_bound, b.count) for b in response.histograms[0].buckets
        ] == [
            (1.0, 2.0, 1.0),
            (2.0, 4.0, 2.0),
            (4.0, 8.0, 1.0),
        ]

    @pytest.mark.asyncio
    async def test_exponential_histograms_of_different_scales_merge(self):
        for offset, (scale, counts) in enumerate([(1, [1, 1]), (0, [2])]):
            await self._insert_point(
                "request_duration_ms",
                self.base + datetime.timedelta(seconds=60 * offset),
                metric_type=_EXPONENTIAL_HISTOGRAM,
                count=sum(counts),
                total=6.0,
                exp_histogram={
                    "scale": scale,
                    "zero_count": 0,
                    # scale 1 buckets 2 and 3 are exactly scale 0 bucket 1, (2, 4]
                    "positive": {"offset": 2 if scale == 1 else 1, "counts": counts},
                    "negative": {"offset": 0, "counts": []},
                },
                temporality=_DELTA,
            )

        response = await self._series("request_duration_ms", "max")

        assert [
            (b.lower_bound, b.upper_bound, b.count) for b in response.histograms[0].buckets
        ] == [(2.0, 4.0, 4.0)]
        assert response.series[0].points[0].value == pytest.approx(4.0)

    @pytest.mark.asyncio
    async def test_summary_reports_the_clients_quantiles(self):
        for offset, p99 in enumerate([1.0, 3.0]):
            await self._insert_point(
                "gc_pause_seconds",
                self.base + datetime.timedelta(seconds=60 * offset),
                metric_type=_SUMMARY,
                count=10 * (offset + 1),
                total=2.0 * (offset + 1),
                quantiles=[[0.5, 0.2], [0.99, p99]],
                temporality=_CUMULATIVE,
            )

        p99 = await self._series("gc_pause_seconds", "p99")
        p95 = await self._series("gc_pause_seconds", "p95")

        # The first cumulative point only anchors the second.
        assert p99.series[0].points[0].value == pytest.approx(3.0)
        # A quantile the client does not report has no value to chart.
        assert p95.series[0].points == []
        assert p99.histograms == []

    @pytest.mark.asyncio
    async def test_p90_is_supported(self):
        await self._insert_point(
            "request_duration_ms",
            self.base,
            metric_type=_HISTOGRAM,
            count=10,
            total=100.0,
            bucket_counts=[10, 0],
            explicit_bounds=[10],
            temporality=_DELTA,
        )

        response = await self._series("request_duration_ms", "p90")

        assert response.series[0].points[0].value == pytest.approx(9.0)

    @pytest.mark.asyncio
    async def test_exemplars_come_back_largest_first_per_series(self):
        await self._insert_point(
            "request_duration_ms",
            self.base,
            metric_type=_HISTOGRAM,
            count=2,
            total=900.0,
            bucket_counts=[1, 1],
            explicit_bounds=[100],
            tags={"route": "/orders"},
            exemplars=[
                {"v": 12.0, "ts": self.base.isoformat(), "trace_id": "a" * 32, "span_id": ""},
                {"v": 888.0, "ts": self.base.isoformat(), "trace_id": "b" * 32, "span_id": ""},
            ],
        )

        response = await self._series("request_duration_ms", "p50", group_by=["route"])

        assert [(e.value, e.trace_id, dict(e.tags)) for e in response.exemplars] == [
            (888.0, "b" * 32, {"route": "/orders"}),
            (12.0, "a" * 32, {"route": "/orders"}),
        ]
