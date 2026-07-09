import datetime

import pytest
from ingestion_service import schemas
from ingestion_service.services import queue_service
from ingestion_service.services.queue_service import QueueFullError

import ingestion_service.config as config

from .test_base import BaseIngestionTest


@pytest.mark.asyncio
class TestQueueService(BaseIngestionTest):
    """Test RabbitMQ queue operations."""

    def _make_log(self, project_id: int = 1, message: str = "Test log") -> schemas.EnrichedLogEntry:
        return schemas.EnrichedLogEntry(
            project_id=project_id,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="info",
                log_type="console",
                importance="standard",
                message=message,
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
        )

    async def test_enqueue_single_log(self):
        """Enqueueing a single log publishes one message to the queue."""
        log = self._make_log()

        await queue_service.enqueue_log(log)

        count = await self.get_queue_message_count()
        assert count == 1

    async def test_enqueue_batch_logs(self):
        """A batch under the envelope chunk size publishes as a single envelope message."""
        logs = [self._make_log(message=f"Batch log {i}") for i in range(10)]

        await queue_service.enqueue_logs_batch(logs)

        envelope_count = await self.get_queue_message_count()
        assert envelope_count == 1

        payloads = await self.consume_all_payloads(10)
        assert len(payloads) == 10

    async def test_enqueue_multiple_projects(self):
        """Logs for different projects are packed into per-project envelopes."""
        logs = [
            self._make_log(project_id=pid, message=f"Project {pid} log {i}")
            for pid in [1, 2, 3]
            for i in range(5)
        ]

        await queue_service.enqueue_logs_batch(logs)

        envelope_count = await self.get_queue_message_count()
        assert envelope_count == 3

        payloads = await self.consume_all_payloads(15)
        assert len(payloads) == 15
        assert {p["project_id"] for p in payloads} == {1, 2, 3}

    async def test_envelope_chunk_boundary(self):
        """A batch larger than RABBITMQ_ENVELOPE_MAX_LOGS splits into multiple envelopes."""
        chunk_size = config.settings.RABBITMQ_ENVELOPE_MAX_LOGS
        logs = [self._make_log(message=f"Chunked log {i}") for i in range(chunk_size + 1)]

        await queue_service.enqueue_logs_batch(logs)

        envelope_count = await self.get_queue_message_count()
        assert envelope_count == 2

        payloads = await self.consume_all_payloads(chunk_size + 1)
        assert len(payloads) == chunk_size + 1

    async def test_messagepack_round_trip(self):
        """Payload survives msgpack serialisation through the broker."""
        original = schemas.EnrichedLogEntry(
            project_id=1,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="error",
                log_type="exception",
                importance="critical",
                message="Test error message",
                error_type="ValueError",
                error_message="Invalid value",
                stack_trace="Traceback...",
                attributes={"key1": "value1", "key2": 42, "nested": {"a": 1}},
                environment="production",
                release="v1.2.3",
                sdk_version="2.0.0",
                platform="python",
                platform_version="3.12.0",
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
            error_fingerprint="a" * 64,
        )

        await queue_service.enqueue_log(original)

        unpacked = await self.consume_one_payload()
        assert unpacked is not None
        assert unpacked["message"] == original.log_entry.message
        assert unpacked["level"] == original.log_entry.level
        assert unpacked["error_type"] == original.log_entry.error_type
        assert unpacked["attributes"] == original.log_entry.attributes
        assert unpacked["error_fingerprint"] == original.error_fingerprint
        assert "timestamp" in unpacked
        assert "ingested_at" in unpacked

    async def test_topic_routing(self):
        """Messages are routed via logs.{project_id} key and arrive on the shared queue."""
        log_p1 = self._make_log(project_id=1, message="Project 1 log")
        log_p2 = self._make_log(project_id=2, message="Project 2 log")

        await queue_service.enqueue_log(log_p1)
        await queue_service.enqueue_log(log_p2)

        payloads = await self.consume_all_payloads(2)
        messages = {p["message"] for p in payloads}
        assert "Project 1 log" in messages
        assert "Project 2 log" in messages
        assert {p["project_id"] for p in payloads} == {1, 2}

    async def test_queue_depth(self):
        """get_queue_depth returns the broker's envelope (message) count, not the log count."""
        logs = [self._make_log(message=f"Log {i}") for i in range(25)]
        await queue_service.enqueue_logs_batch(logs)

        depth = await queue_service.get_queue_depth(project_id=1)
        assert depth == 1

    async def test_backpressure_raises_queue_full_error(self):
        """Publishing when queue is at x-max-length raises QueueFullError."""
        max_depth = config.settings.QUEUE_MAX_DEPTH

        log = self._make_log()

        import aio_pika

        async with self.rabbitmq_connection.channel(publisher_confirms=True) as channel:
            exchange = await channel.get_exchange(config.settings.RABBITMQ_EXCHANGE)

            for _ in range(max_depth):
                import msgpack

                await exchange.publish(
                    aio_pika.Message(
                        body=msgpack.packb({"dummy": True}, use_bin_type=True),
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key="logs.1",
                )

        with pytest.raises(QueueFullError):
            await queue_service.enqueue_log(log)

    async def test_complex_attributes_preserved(self):
        """Nested JSONB attributes survive the queue round-trip."""
        log = schemas.EnrichedLogEntry(
            project_id=1,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="info",
                log_type="custom",
                importance="standard",
                message="Complex attributes test",
                attributes={
                    "user": {"id": 123, "email": "test@example.com", "roles": ["admin", "user"]},
                    "request": {"method": "POST", "url": "/api/test"},
                    "metrics": {"duration_ms": 150},
                },
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
        )

        await queue_service.enqueue_log(log)

        unpacked = await self.consume_one_payload()
        assert unpacked is not None
        assert unpacked["attributes"]["user"]["id"] == 123
        assert "admin" in unpacked["attributes"]["user"]["roles"]
        assert unpacked["attributes"]["request"]["method"] == "POST"

    async def test_large_batch_enqueue(self):
        """1000 logs can be enqueued as a single batch, split into envelopes."""
        chunk_size = config.settings.RABBITMQ_ENVELOPE_MAX_LOGS
        logs = [self._make_log(message=f"Batch log {i}") for i in range(1000)]

        await queue_service.enqueue_logs_batch(logs)

        envelope_count = await self.get_queue_message_count()
        assert envelope_count == -(-1000 // chunk_size)

        payloads = await self.consume_all_payloads(1000)
        assert len(payloads) == 1000

    async def test_empty_batch_is_noop(self):
        """Enqueueing an empty batch leaves the queue empty."""
        await queue_service.enqueue_logs_batch([])

        count = await self.get_queue_message_count()
        assert count == 0


@pytest.mark.asyncio
class TestSpansQueueService(BaseIngestionTest):
    """Test RabbitMQ span queue operations (mirrors TestQueueService for logs)."""

    def _make_span(
        self,
        project_id: int = 1,
        span_id: str = "a" * 16,
        trace_id: str = "b" * 32,
        name: str = "GET /test",
        parent_span_id: str | None = None,
    ) -> dict:
        return {
            "span_id": span_id,
            "trace_id": trace_id,
            "parent_span_id": parent_span_id,
            "project_id": project_id,
            "service_name": "test-service",
            "name": name,
            "kind": 0,
            "start_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "duration_ns": 1_000_000,
            "status_code": 0,
            "status_message": "",
            "attributes": {"http.method": "GET"},
            "events": [],
            "error_fingerprint": None,
        }

    async def test_enqueue_spans_envelope(self):
        """A span batch under the chunk size publishes as a single envelope message."""
        spans = [self._make_span(span_id=f"{i:016x}") for i in range(10)]

        await queue_service.enqueue_spans_envelope(1, spans)

        envelope_count = await self.get_queue_message_count(config.settings.RABBITMQ_SPANS_QUEUE)
        assert envelope_count == 1

        payloads = await self.consume_all_span_payloads(10)
        assert len(payloads) == 10

    async def test_spans_envelope_chunk_boundary(self):
        """A span batch larger than RABBITMQ_ENVELOPE_MAX_SPANS splits into multiple envelopes."""
        chunk_size = config.settings.RABBITMQ_ENVELOPE_MAX_SPANS
        spans = [self._make_span(span_id=f"{i:016x}") for i in range(chunk_size + 1)]

        await queue_service.enqueue_spans_envelope(1, spans)

        envelope_count = await self.get_queue_message_count(config.settings.RABBITMQ_SPANS_QUEUE)
        assert envelope_count == 2

        payloads = await self.consume_all_span_payloads(chunk_size + 1)
        assert len(payloads) == chunk_size + 1

    async def test_spans_messagepack_round_trip(self):
        """Span payload (incl. parent_span_id/attributes/events) survives the broker round-trip."""
        span = self._make_span(
            span_id="1" * 16,
            trace_id="2" * 32,
            parent_span_id="3" * 16,
            name="POST /orders",
        )
        span["attributes"] = {"http.method": "POST", "http.status_code": 201}
        span["events"] = [{"name": "retry", "ts": 123, "attrs": {"n": "1"}}]

        await queue_service.enqueue_spans_envelope(1, [span])

        payload = await self.consume_one_span_payload()
        assert payload is not None
        assert payload["span_id"] == "1" * 16
        assert payload["trace_id"] == "2" * 32
        assert payload["parent_span_id"] == "3" * 16
        assert payload["name"] == "POST /orders"
        assert payload["attributes"] == {"http.method": "POST", "http.status_code": 201}
        assert payload["events"] == [{"name": "retry", "ts": 123, "attrs": {"n": "1"}}]

    async def test_spans_topic_routing(self):
        """Spans are routed via spans.{project_id} and land on the dedicated spans queue,
        not the shared logs queue."""
        span = self._make_span(project_id=5)

        await queue_service.enqueue_spans_envelope(5, [span])

        spans_depth = await self.get_queue_message_count(config.settings.RABBITMQ_SPANS_QUEUE)
        logs_depth = await self.get_queue_message_count(config.settings.RABBITMQ_QUEUE)
        assert spans_depth == 1
        assert logs_depth == 0

    async def test_empty_spans_batch_is_noop(self):
        """Enqueueing an empty span batch leaves the spans queue empty."""
        await queue_service.enqueue_spans_envelope(1, [])

        count = await self.get_queue_message_count(config.settings.RABBITMQ_SPANS_QUEUE)
        assert count == 0
