import datetime
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


def _make_span_dict(
    project_id: int = 1,
    span_id: str = "a" * 16,
    trace_id: str = "b" * 32,
    name: str = "GET /test",
    parent_span_id: str | None = None,
    start_time: datetime.datetime | None = None,
    attributes: dict | None = None,
    events: list | None = None,
    status_code: int = 0,
    duration_ns: int = 1_000_000,
) -> dict:
    ts = start_time or datetime.datetime.now(datetime.timezone.utc)
    return {
        "span_id": span_id,
        "trace_id": trace_id,
        "parent_span_id": parent_span_id,
        "project_id": project_id,
        "service_name": "test-service",
        "name": name,
        "kind": 0,
        "start_time": ts.isoformat(),
        "duration_ns": duration_ns,
        "status_code": status_code,
        "status_message": "",
        "attributes": attributes if attributes is not None else {"http.method": "GET"},
        "events": events if events is not None else [],
        "error_fingerprint": None,
    }


@pytest.mark.asyncio
class TestSpansStorageWorker(BaseIngestionTest):
    """Test the spans consumer/COPY-insert worker path (mirrors TestStorageWorker for logs)."""

    def test_decode_spans_message_unwraps_envelope(self):
        """_decode_spans_message expands a spans envelope into its constituent span dicts."""
        envelope = {
            "v": 1,
            "project_id": 7,
            "spans": [
                {"span_id": "a" * 16},
                {"span_id": "b" * 16},
            ],
        }
        message = _FakeMessage(msgpack.packb(envelope, use_bin_type=True))

        spans = StorageWorker._decode_spans_message(message)

        assert len(spans) == 2
        assert spans[0]["project_id"] == 7
        assert spans[1]["project_id"] == 7
        assert spans[0]["span_id"] == "a" * 16

    def test_decode_spans_message_rejects_malformed_envelope(self):
        """A payload without a 'spans' key must raise so the caller nacks the
        message instead of silently mis-ingesting it."""
        malformed_payload = {"project_id": 3, "span_id": "not an envelope"}
        message = _FakeMessage(msgpack.packb(malformed_payload, use_bin_type=True))

        with pytest.raises(ValueError):
            StorageWorker._decode_spans_message(message)

    async def test_worker_processes_single_span(self):
        """Worker COPY-inserts a single span payload into the database."""
        span = _make_span_dict(span_id="1" * 16, trace_id="2" * 32, name="Single span")
        await queue_service.enqueue_spans_envelope(1, [span])

        payload = await self.consume_one_span_payload()
        assert payload is not None

        worker = StorageWorker(worker_id=1)
        await worker.process_spans_batch([payload])

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(models.Span))
            spans = result.scalars().all()
            assert len(spans) == 1
            assert spans[0].span_id == "1" * 16
            assert spans[0].trace_id == "2" * 32
            assert spans[0].name == "Single span"

    async def test_worker_processes_span_batch(self):
        """Worker bulk COPY-inserts multiple span payloads (row count assertion)."""
        spans = [_make_span_dict(span_id=f"{i:016x}", name=f"Batch span {i}") for i in range(10)]
        await queue_service.enqueue_spans_envelope(1, spans)

        payloads = await self.consume_all_span_payloads(10)
        assert len(payloads) == 10

        worker = StorageWorker(worker_id=1)
        await worker.process_spans_batch(payloads)

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(
                sqlalchemy.select(sqlalchemy.func.count()).select_from(models.Span)
            )
            count = result.scalar()
            assert count == 10

    async def test_worker_preserves_span_fields(self):
        """Worker preserves parent_span_id, attributes and events (JSON) exactly."""
        attributes = {
            "http.method": "POST",
            "http.status_code": 500,
            "nested": {"a": 1, "b": [1, 2, 3]},
        }
        events = [
            {"name": "exception", "ts": 1700000000000000000, "attrs": {"type": "ValueError"}},
            {"name": "retry", "ts": 1700000000100000000, "attrs": {"n": "2"}},
        ]
        span = _make_span_dict(
            span_id="3" * 16,
            trace_id="4" * 32,
            parent_span_id="5" * 16,
            name="Span with events",
            attributes=attributes,
            events=events,
            status_code=2,
        )
        await queue_service.enqueue_spans_envelope(1, [span])

        payload = await self.consume_one_span_payload()
        assert payload is not None

        worker = StorageWorker(worker_id=1)
        await worker.process_spans_batch([payload])

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(
                sqlalchemy.select(models.Span).where(models.Span.span_id == "3" * 16)
            )
            stored = result.scalar_one()
            assert stored.parent_span_id == "5" * 16
            assert stored.attributes == attributes
            assert stored.attributes["nested"]["b"] == [1, 2, 3]
            assert stored.events == events
            assert stored.status_code == 2

    async def test_worker_dedupes_span_on_conflict(self):
        """Reprocessing the same (span_id, start_time) pair inserts only one row
        (ON CONFLICT (span_id, start_time) DO NOTHING)."""
        fixed_start = datetime.datetime.now(datetime.timezone.utc)
        span = _make_span_dict(
            span_id="6" * 16, trace_id="7" * 32, name="Redelivered span", start_time=fixed_start
        )
        await queue_service.enqueue_spans_envelope(1, [span])

        payload = await self.consume_one_span_payload()
        assert payload is not None

        worker = StorageWorker(worker_id=1)
        await worker.process_spans_batch([payload])
        await worker.process_spans_batch([payload])

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(
                sqlalchemy.select(models.Span).where(models.Span.span_id == "6" * 16)
            )
            spans = result.scalars().all()
            assert len(spans) == 1

    async def test_worker_handles_different_projects(self):
        """Worker correctly stores spans from multiple projects."""
        span1 = _make_span_dict(project_id=1, span_id="8" * 16, name="Project 1 span")
        span2 = _make_span_dict(project_id=2, span_id="9" * 16, name="Project 2 span")
        await queue_service.enqueue_spans_envelope(1, [span1])
        await queue_service.enqueue_spans_envelope(2, [span2])

        payloads = await self.consume_all_span_payloads(2)
        assert len(payloads) == 2

        worker = StorageWorker(worker_id=1)
        await worker.process_spans_batch(payloads)

        async with self.test_db_manager.session_factory() as session:
            result1 = await session.execute(
                sqlalchemy.select(models.Span).where(models.Span.project_id == 1)
            )
            result2 = await session.execute(
                sqlalchemy.select(models.Span).where(models.Span.project_id == 2)
            )
            spans1 = result1.scalars().all()
            spans2 = result2.scalars().all()
            assert len(spans1) == 1
            assert len(spans2) == 1
            assert spans1[0].name == "Project 1 span"
            assert spans2[0].name == "Project 2 span"

    async def test_worker_bulk_span_insert_performance(self):
        """Worker inserts 100 spans in under 1 second."""
        spans = [_make_span_dict(span_id=f"{i:016x}", name=f"Perf span {i}") for i in range(100)]
        await queue_service.enqueue_spans_envelope(1, spans)

        payloads = await self.consume_all_span_payloads(100)
        assert len(payloads) == 100

        worker = StorageWorker(worker_id=1)
        start = time.time()
        await worker.process_spans_batch(payloads)
        duration = time.time() - start

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(
                sqlalchemy.select(sqlalchemy.func.count()).select_from(models.Span)
            )
            count = result.scalar()
            assert count == 100
            assert duration < 1.0
