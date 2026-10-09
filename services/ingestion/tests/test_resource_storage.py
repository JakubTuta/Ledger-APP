"""Resources stored once per project, trace context columns, and the new
metric point shapes (exponential histograms, summaries, exemplars)."""

import datetime
import json

import pytest
import sqlalchemy

import ingestion_service.models as models
import ingestion_service.proto.ingestion_pb2 as ingestion_pb2
import ingestion_service.worker as worker_module

from .helpers import create_proto_log
from .test_base import BaseIngestionTest

_RESOURCE_HASH = 1_234_567_890_123
_RESOURCE = {"service.name": "checkout", "telemetry.sdk.language": "python"}


def _log_proto(message: str, **fields) -> ingestion_pb2.LogEntry:
    proto_log = create_proto_log(
        {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "message": message,
            "attributes": {"code.function": "handler"},
        }
    )
    for name, value in fields.items():
        setattr(proto_log, name, value)
    return proto_log


@pytest.mark.asyncio
class TestResourceStorage(BaseIngestionTest):
    async def _ingest_and_store(self, request: ingestion_pb2.IngestLogBatchRequest) -> None:
        # The per-process "already stored" cache would otherwise outlive the
        # TRUNCATE between tests.
        worker_module._resource_upserted_at.clear()
        await self.stub.IngestLogBatch(request)
        payloads = await self.consume_all_payloads(len(request.logs))
        assert len(payloads) == len(request.logs)
        await worker_module.StorageWorker(worker_id=1).process_logs_batch(payloads)

    async def test_resource_is_stored_once_and_rows_reference_it(self):
        await self._ingest_and_store(
            ingestion_pb2.IngestLogBatchRequest(
                project_id=1,
                logs=[
                    _log_proto(
                        f"log {i}",
                        resource_hash=_RESOURCE_HASH,
                        service_name="checkout",
                        trace_id="a" * 32,
                        span_id="b" * 16,
                    )
                    for i in range(3)
                ],
                resources={_RESOURCE_HASH: json.dumps(_RESOURCE)},
            )
        )

        async with self.test_db_manager.session_factory() as session:
            resources = (await session.execute(sqlalchemy.select(models.Resource))).scalars().all()
            logs = (await session.execute(sqlalchemy.select(models.Log))).scalars().all()

        assert [(r.project_id, r.resource_hash, r.attributes) for r in resources] == [
            (1, _RESOURCE_HASH, _RESOURCE)
        ]
        assert len(logs) == 3
        for log in logs:
            assert log.resource_hash == _RESOURCE_HASH
            assert log.service_name == "checkout"
            assert (log.trace_id, log.span_id) == ("a" * 32, "b" * 16)
            assert log.attributes == {"code.function": "handler"}

    async def test_malformed_resource_is_dropped_but_the_log_is_kept(self):
        await self._ingest_and_store(
            ingestion_pb2.IngestLogBatchRequest(
                project_id=1,
                logs=[_log_proto("kept", resource_hash=_RESOURCE_HASH)],
                resources={_RESOURCE_HASH: "[not, an, object"},
            )
        )

        async with self.test_db_manager.session_factory() as session:
            resources = (await session.execute(sqlalchemy.select(models.Resource))).scalars().all()
            (log,) = (await session.execute(sqlalchemy.select(models.Log))).scalars().all()

        assert resources == []
        assert log.message == "kept"
        assert log.resource_hash is None

    async def test_malformed_trace_id_is_dropped_but_the_log_is_kept(self):
        await self._ingest_and_store(
            ingestion_pb2.IngestLogBatchRequest(
                project_id=1, logs=[_log_proto("kept", trace_id="xyz", span_id="b" * 16)]
            )
        )

        async with self.test_db_manager.session_factory() as session:
            (log,) = (await session.execute(sqlalchemy.select(models.Log))).scalars().all()

        assert log.trace_id is None
        assert log.span_id == "b" * 16


@pytest.mark.asyncio
class TestDistributionPointStorage(BaseIngestionTest):
    async def _store(self, point: ingestion_pb2.MetricPoint) -> models.MetricPoint:
        await self.stub.IngestMetricPointsBatch(
            ingestion_pb2.IngestMetricPointsBatchRequest(project_id=1, points=[point])
        )
        payload = await self.consume_one_metric_payload()
        assert payload is not None
        await worker_module.StorageWorker(worker_id=1).process_metric_points_batch([payload])
        async with self.test_db_manager.session_factory() as session:
            return (await session.execute(sqlalchemy.select(models.MetricPoint))).scalar_one()

    def _point(self, metric_type: int, **fields) -> ingestion_pb2.MetricPoint:
        point = ingestion_pb2.MetricPoint(
            name="request.duration",
            type=metric_type,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            tags={"route": "/orders"},
            service_name="checkout",
        )
        for name, value in fields.items():
            if isinstance(value, list):
                getattr(point, name).extend(value)
            else:
                setattr(point, name, value)
        return point

    async def test_exponential_histogram_is_stored(self):
        stored = await self._store(
            self._point(
                ingestion_pb2.EXPONENTIAL_HISTOGRAM,
                count=6,
                sum=21.0,
                scale=1,
                zero_count=1,
                positive_offset=2,
                positive_counts=[2, 3],
            )
        )

        assert stored.type == ingestion_pb2.EXPONENTIAL_HISTOGRAM
        assert stored.exp_histogram == {
            "scale": 1,
            "zero_count": 1,
            "positive": {"offset": 2, "counts": [2, 3]},
            "negative": {"offset": 0, "counts": []},
        }

    async def test_summary_quantiles_are_stored(self):
        stored = await self._store(
            self._point(
                ingestion_pb2.SUMMARY,
                count=40,
                sum=12.5,
                quantiles=[0.5, 0.99],
                quantile_values=[0.2, 1.4],
            )
        )

        assert stored.quantiles == [[0.5, 0.2], [0.99, 1.4]]

    async def test_exemplars_with_a_trace_are_stored(self):
        point = self._point(ingestion_pb2.HISTOGRAM, count=1, bucket_counts=[1.0])
        point.exemplars.add(value=812.0, timestamp="2026-10-09T10:00:00+00:00", trace_id="a" * 32)
        point.exemplars.add(value=3.0, timestamp="2026-10-09T10:00:00+00:00", trace_id="bad")

        stored = await self._store(point)

        assert stored.exemplars == [
            {"v": 812.0, "ts": "2026-10-09T10:00:00+00:00", "trace_id": "a" * 32, "span_id": ""}
        ]
