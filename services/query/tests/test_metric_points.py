import datetime
import hashlib
import json

import pytest
import sqlalchemy as sa

import query_service.proto.query_pb2 as query_pb2
import tests.test_base as test_base


def _tags_hash(tags: dict) -> str:
    canonical = json.dumps(tags, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode(), digest_size=8).hexdigest()


class TestMetricPoints(test_base.BaseQueryTest):
    async def _insert_raw_point(
        self,
        project_id: int = 1,
        name: str = "queue.depth",
        type_: int = 1,
        ts: datetime.datetime | None = None,
        value: float | None = None,
        count: int | None = None,
        sum_: float | None = None,
        tags: dict | None = None,
    ) -> None:
        ts = ts or datetime.datetime.now(datetime.timezone.utc)
        tags = tags or {}
        async with self.test_db_manager.session_factory() as session:
            await session.execute(
                sa.text("""
                    INSERT INTO metric_points
                        (project_id, name, type, ts, value, count, sum, tags, tags_hash, service_name)
                    VALUES
                        (:project_id, :name, :type, :ts, :value, :count, :sum, CAST(:tags AS jsonb), :tags_hash, :service_name)
                """),
                {
                    "project_id": project_id,
                    "name": name,
                    "type": type_,
                    "ts": ts,
                    "value": value,
                    "count": count,
                    "sum": sum_,
                    "tags": json.dumps(tags),
                    "tags_hash": _tags_hash(tags),
                    "service_name": "test-service",
                },
            )
            await session.commit()

    async def _insert_rollup_bucket(
        self,
        project_id: int = 1,
        name: str = "queue.depth",
        type_: int = 1,
        bucket: datetime.datetime | None = None,
        count: int = 1,
        sum_v: float = 0.0,
        min_v: float = 0.0,
        max_v: float = 0.0,
        avg_v: float = 0.0,
        tags: dict | None = None,
    ) -> None:
        bucket = bucket or datetime.datetime.now(datetime.timezone.utc)
        tags = tags or {}
        async with self.test_db_manager.session_factory() as session:
            await session.execute(
                sa.text("""
                    INSERT INTO metric_points_1h
                        (project_id, name, type, tags_hash, tags, bucket, count, sum_v, min_v, max_v, avg_v)
                    VALUES
                        (:project_id, :name, :type, :tags_hash, CAST(:tags AS jsonb), :bucket, :count, :sum_v, :min_v, :max_v, :avg_v)
                """),
                {
                    "project_id": project_id,
                    "name": name,
                    "type": type_,
                    "tags_hash": _tags_hash(tags),
                    "tags": json.dumps(tags),
                    "bucket": bucket,
                    "count": count,
                    "sum_v": sum_v,
                    "min_v": min_v,
                    "max_v": max_v,
                    "avg_v": avg_v,
                },
            )
            await session.commit()

    @pytest.mark.asyncio
    async def test_query_metrics_raw_path_gauge_avg(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        await self._insert_raw_point(name="cpu.usage", type_=1, value=10.0, ts=now)
        await self._insert_raw_point(
            name="cpu.usage", type_=1, value=20.0, ts=now + datetime.timedelta(seconds=1)
        )

        response = await self.stub.QueryMetrics(
            query_pb2.QueryMetricsRequest(
                project_id=1,
                name="cpu.usage",
                aggregation="avg",
                from_time=(now - datetime.timedelta(minutes=5)).isoformat(),
                to_time=(now + datetime.timedelta(minutes=5)).isoformat(),
            )
        )

        assert len(response.data) == 1
        assert response.data[0].value == 15.0

    @pytest.mark.asyncio
    async def test_query_metrics_raw_path_histogram_uses_sum_over_count(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        await self._insert_raw_point(
            name="request.duration", type_=2, value=None, count=10, sum_=100.0, ts=now
        )

        response = await self.stub.QueryMetrics(
            query_pb2.QueryMetricsRequest(
                project_id=1,
                name="request.duration",
                aggregation="avg",
                from_time=(now - datetime.timedelta(minutes=5)).isoformat(),
                to_time=(now + datetime.timedelta(minutes=5)).isoformat(),
            )
        )

        assert len(response.data) == 1
        assert response.data[0].value == 10.0

    @pytest.mark.asyncio
    async def test_query_metrics_raw_path_aggregations(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        for i, v in enumerate((5.0, 10.0, 15.0)):
            await self._insert_raw_point(
                name="latency", type_=1, value=v, ts=now + datetime.timedelta(seconds=i)
            )

        for aggregation, expected in [("sum", 30.0), ("min", 5.0), ("max", 15.0), ("count", 3.0)]:
            response = await self.stub.QueryMetrics(
                query_pb2.QueryMetricsRequest(
                    project_id=1,
                    name="latency",
                    aggregation=aggregation,
                    from_time=(now - datetime.timedelta(minutes=5)).isoformat(),
                    to_time=(now + datetime.timedelta(minutes=5)).isoformat(),
                )
            )
            assert response.data[0].value == expected, f"aggregation={aggregation}"

    @pytest.mark.asyncio
    async def test_query_metrics_raw_path_tag_filter(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        await self._insert_raw_point(
            name="requests", type_=1, value=1.0, ts=now, tags={"route": "/health"}
        )
        await self._insert_raw_point(
            name="requests", type_=1, value=100.0, ts=now, tags={"route": "/checkout"}
        )

        request = query_pb2.QueryMetricsRequest(
            project_id=1,
            name="requests",
            aggregation="sum",
            from_time=(now - datetime.timedelta(minutes=5)).isoformat(),
            to_time=(now + datetime.timedelta(minutes=5)).isoformat(),
        )
        request.tags["route"] = "/health"

        response = await self.stub.QueryMetrics(request)

        assert len(response.data) == 1
        assert response.data[0].value == 1.0

    @pytest.mark.asyncio
    async def test_query_metrics_rollup_path_used_for_long_window(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        bucket = now.replace(minute=0, second=0, microsecond=0)

        # Seed only the rollup table - if the raw path were used instead this
        # would return no data, since no rows exist in metric_points.
        await self._insert_rollup_bucket(
            name="cpu.usage", bucket=bucket, count=5, sum_v=50.0, min_v=5.0, max_v=15.0, avg_v=10.0
        )

        response = await self.stub.QueryMetrics(
            query_pb2.QueryMetricsRequest(
                project_id=1,
                name="cpu.usage",
                aggregation="avg",
                from_time=(now - datetime.timedelta(hours=12)).isoformat(),
                to_time=now.isoformat(),
            )
        )

        assert len(response.data) == 1
        assert response.data[0].value == 10.0

    @pytest.mark.asyncio
    async def test_query_metrics_no_data_returns_empty(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        response = await self.stub.QueryMetrics(
            query_pb2.QueryMetricsRequest(
                project_id=1,
                name="nonexistent",
                aggregation="avg",
                from_time=(now - datetime.timedelta(minutes=5)).isoformat(),
                to_time=now.isoformat(),
            )
        )
        assert len(response.data) == 0

    @pytest.mark.asyncio
    async def test_get_metric_series_lists_names_types_and_tag_keys(self):
        bucket = datetime.datetime.now(datetime.timezone.utc).replace(
            minute=0, second=0, microsecond=0
        )
        await self._insert_rollup_bucket(
            name="cpu.usage", type_=1, bucket=bucket, tags={"region": "us"}
        )
        await self._insert_rollup_bucket(
            name="request.duration", type_=2, bucket=bucket, tags={"route": "/health"}
        )

        response = await self.stub.GetMetricSeries(query_pb2.GetMetricSeriesRequest(project_id=1))

        names = {s.name: s for s in response.series}
        assert set(names) == {"cpu.usage", "request.duration"}
        assert names["cpu.usage"].type == 1
        assert "region" in names["cpu.usage"].tag_keys
        assert names["request.duration"].type == 2
        assert "route" in names["request.duration"].tag_keys

    @pytest.mark.asyncio
    async def test_get_metric_series_project_isolation(self):
        bucket = datetime.datetime.now(datetime.timezone.utc)
        await self._insert_rollup_bucket(project_id=1, name="project1.metric", bucket=bucket)
        await self._insert_rollup_bucket(project_id=2, name="project2.metric", bucket=bucket)

        response = await self.stub.GetMetricSeries(query_pb2.GetMetricSeriesRequest(project_id=1))

        names = [s.name for s in response.series]
        assert names == ["project1.metric"]
