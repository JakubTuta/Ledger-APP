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
        """Enqueueing a batch publishes one message per log."""
        logs = [self._make_log(message=f"Batch log {i}") for i in range(10)]

        await queue_service.enqueue_logs_batch(logs)

        count = await self.get_queue_message_count()
        assert count == 10

    async def test_enqueue_multiple_projects(self):
        """Logs for different projects all land in the shared queue."""
        logs = [
            self._make_log(project_id=pid, message=f"Project {pid} log {i}")
            for pid in [1, 2, 3]
            for i in range(5)
        ]

        await queue_service.enqueue_logs_batch(logs)

        count = await self.get_queue_message_count()
        assert count == 15

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
        """get_queue_depth returns the total message count in the shared queue."""
        logs = [self._make_log(message=f"Log {i}") for i in range(25)]
        await queue_service.enqueue_logs_batch(logs)

        depth = await queue_service.get_queue_depth(project_id=1)
        assert depth == 25

    async def test_backpressure_raises_queue_full_error(self):
        """Publishing when queue is at x-max-length raises QueueFullError."""
        max_depth = config.settings.QUEUE_MAX_DEPTH

        log = self._make_log()

        import aio_pika
        async with self.rabbitmq_connection.channel() as channel:
            await channel.confirm_delivery()
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
        """1000 logs can be enqueued as a single batch."""
        logs = [self._make_log(message=f"Batch log {i}") for i in range(1000)]

        await queue_service.enqueue_logs_batch(logs)

        count = await self.get_queue_message_count()
        assert count == 1000

    async def test_empty_batch_is_noop(self):
        """Enqueueing an empty batch leaves the queue empty."""
        await queue_service.enqueue_logs_batch([])

        count = await self.get_queue_message_count()
        assert count == 0
