import datetime
import hashlib
import json
import time

import msgpack
import pytest
import sqlalchemy
from ingestion_service import models
from ingestion_service.services import queue_service
from ingestion_service.worker import StorageWorker

from .test_base import BaseIngestionTest


class _FakeMessage:
    def __init__(self, body: bytes):
        self.body = body


def _tags_hash(tags: dict) -> str:
    canonical = json.dumps(tags, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode(), digest_size=8).hexdigest()


def _make_metric_point_dict(
    project_id: int = 1,
    name: str = "queue.depth",
    type_: int = 1,
    ts: datetime.datetime | None = None,
    value: float | None = 42.0,
    count: int | None = None,
    sum_: float | None = None,
    bucket_counts: list | None = None,
    explicit_bounds: list | None = None,
    tags: dict | None = None,
    service_name: str = "test-service",
) -> dict:
    ts = ts or datetime.datetime.now(datetime.timezone.utc)
    tags = tags if tags is not None else {"region": "us"}
    return {
        "project_id": project_id,
        "name": name,
        "type": type_,
        "ts": ts.isoformat(),
        "value": value,
        "count": count,
        "sum": sum_,
        "bucket_counts": bucket_counts,
        "explicit_bounds": explicit_bounds,
        "tags": tags,
        "tags_hash": _tags_hash(tags),
        "service_name": service_name,
    }


@pytest.mark.asyncio
class TestMetricPointsStorageWorker(BaseIngestionTest):
    """Test the metric points consumer/COPY-insert worker path (mirrors
    TestSpansStorageWorker for spans)."""

    def test_decode_metrics_message_unwraps_envelope(self):
        """_decode_metrics_message expands a metrics envelope into its
        constituent point dicts."""
        envelope = {
            "v": 1,
            "project_id": 7,
            "points": [
                {"name": "a"},
                {"name": "b"},
            ],
        }
        message = _FakeMessage(msgpack.packb(envelope, use_bin_type=True))

        points = StorageWorker._decode_metrics_message(message)

        assert len(points) == 2
        assert points[0]["project_id"] == 7
        assert points[1]["project_id"] == 7
        assert points[0]["name"] == "a"

    def test_decode_metrics_message_rejects_malformed_envelope(self):
        """A payload without a 'points' key must raise so the caller nacks the
        message instead of silently mis-ingesting it."""
        malformed_payload = {"project_id": 3, "name": "not an envelope"}
        message = _FakeMessage(msgpack.packb(malformed_payload, use_bin_type=True))

        with pytest.raises(ValueError):
            StorageWorker._decode_metrics_message(message)

    async def test_worker_processes_single_gauge_point(self):
        """Worker COPY-inserts a single gauge metric point into the database."""
        point = _make_metric_point_dict(name="single.gauge", type_=1, value=99.5)
        await queue_service.enqueue_metrics_envelope(1, [point])

        payload = await self.consume_one_metric_payload()
        assert payload is not None

        worker = StorageWorker(worker_id=1)
        await worker.process_metric_points_batch([payload])

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(models.MetricPoint))
            points = result.scalars().all()
            assert len(points) == 1
            assert points[0].name == "single.gauge"
            assert points[0].value == 99.5
            assert points[0].type == 1

    async def test_worker_processes_metric_point_batch(self):
        """Worker bulk COPY-inserts multiple metric point payloads."""
        points = [_make_metric_point_dict(name=f"metric.{i}") for i in range(10)]
        await queue_service.enqueue_metrics_envelope(1, points)

        payloads = await self.consume_all_metric_payloads(10)
        assert len(payloads) == 10

        worker = StorageWorker(worker_id=1)
        await worker.process_metric_points_batch(payloads)

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(
                sqlalchemy.select(sqlalchemy.func.count()).select_from(models.MetricPoint)
            )
            count = result.scalar()
            assert count == 10

    async def test_worker_preserves_histogram_fields(self):
        """Worker preserves count/sum/bucket_counts/explicit_bounds for
        histogram-type points exactly."""
        point = _make_metric_point_dict(
            name="request.duration",
            type_=2,
            value=None,
            count=10,
            sum_=55.0,
            bucket_counts=[2.0, 5.0, 3.0],
            explicit_bounds=[1.0, 5.0],
            tags={"route": "/health"},
        )
        await queue_service.enqueue_metrics_envelope(1, [point])

        payload = await self.consume_one_metric_payload()
        assert payload is not None

        worker = StorageWorker(worker_id=1)
        await worker.process_metric_points_batch([payload])

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(
                sqlalchemy.select(models.MetricPoint).where(
                    models.MetricPoint.name == "request.duration"
                )
            )
            stored = result.scalar_one()
            assert stored.type == 2
            assert stored.count == 10
            assert stored.sum == 55.0
            assert stored.bucket_counts == [2.0, 5.0, 3.0]
            assert stored.explicit_bounds == [1.0, 5.0]
            assert stored.tags == {"route": "/health"}

    async def test_worker_dedupes_metric_point_on_conflict(self):
        """Reprocessing the same (project_id, name, tags_hash, ts) primary key
        inserts only one row (ON CONFLICT DO NOTHING)."""
        fixed_ts = datetime.datetime.now(datetime.timezone.utc)
        point = _make_metric_point_dict(name="redelivered.metric", ts=fixed_ts)
        await queue_service.enqueue_metrics_envelope(1, [point])

        payload = await self.consume_one_metric_payload()
        assert payload is not None

        worker = StorageWorker(worker_id=1)
        await worker.process_metric_points_batch([payload])
        await worker.process_metric_points_batch([payload])

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(
                sqlalchemy.select(models.MetricPoint).where(
                    models.MetricPoint.name == "redelivered.metric"
                )
            )
            points = result.scalars().all()
            assert len(points) == 1

    async def test_worker_handles_different_projects(self):
        """Worker correctly stores metric points from multiple projects."""
        point1 = _make_metric_point_dict(project_id=1, name="project1.metric")
        point2 = _make_metric_point_dict(project_id=2, name="project2.metric")
        await queue_service.enqueue_metrics_envelope(1, [point1])
        await queue_service.enqueue_metrics_envelope(2, [point2])

        payloads = await self.consume_all_metric_payloads(2)
        assert len(payloads) == 2

        worker = StorageWorker(worker_id=1)
        await worker.process_metric_points_batch(payloads)

        async with self.test_db_manager.session_factory() as session:
            result1 = await session.execute(
                sqlalchemy.select(models.MetricPoint).where(models.MetricPoint.project_id == 1)
            )
            result2 = await session.execute(
                sqlalchemy.select(models.MetricPoint).where(models.MetricPoint.project_id == 2)
            )
            points1 = result1.scalars().all()
            points2 = result2.scalars().all()
            assert len(points1) == 1
            assert len(points2) == 1
            assert points1[0].name == "project1.metric"
            assert points2[0].name == "project2.metric"

    async def test_worker_bulk_metric_point_insert_performance(self):
        """Worker inserts 100 metric points in under 1 second."""
        points = [_make_metric_point_dict(name=f"perf.metric.{i}") for i in range(100)]
        await queue_service.enqueue_metrics_envelope(1, points)

        payloads = await self.consume_all_metric_payloads(100)
        assert len(payloads) == 100

        worker = StorageWorker(worker_id=1)
        start = time.time()
        await worker.process_metric_points_batch(payloads)
        duration = time.time() - start

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(
                sqlalchemy.select(sqlalchemy.func.count()).select_from(models.MetricPoint)
            )
            count = result.scalar()
            assert count == 100
            assert duration < 1.0
