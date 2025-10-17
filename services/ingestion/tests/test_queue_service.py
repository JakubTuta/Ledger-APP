import datetime

import msgpack
import pytest
from ingestion_service import schemas
from ingestion_service.services import queue_service
from ingestion_service.services.queue_service import QueueFullError

from .test_base import BaseIngestionTest


@pytest.mark.asyncio
class TestQueueService(BaseIngestionTest):
    """Test Redis queue operations."""

    async def test_enqueue_single_log(self):
        """Test enqueueing a single log."""
        log = schemas.EnrichedLogEntry(
            project_id=1,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="info",
                log_type="console",
                importance="standard",
                message="Test log",
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
        )

        await queue_service.enqueue_log(log)

        queue_key = f"queue:logs:{log.project_id}"
        queue_length = await self.redis.llen(queue_key)

        assert queue_length == 1
        print("✅ Single log enqueued successfully")

    async def test_enqueue_batch_logs(self):
        """Test enqueueing multiple logs in batch."""
        logs = [
            schemas.EnrichedLogEntry(
                project_id=1,
                log_entry=schemas.LogEntry(
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    level="info",
                    log_type="console",
                    importance="standard",
                    message=f"Test log {i}",
                ),
                ingested_at=datetime.datetime.now(datetime.timezone.utc),
            )
            for i in range(10)
        ]

        await queue_service.enqueue_logs_batch(logs)

        queue_key = f"queue:logs:1"
        queue_length = await self.redis.llen(queue_key)

        assert queue_length == 10
        print("✅ Batch logs enqueued successfully")

    async def test_enqueue_multiple_projects(self):
        """Test enqueueing logs for multiple projects."""
        logs = []
        for project_id in [1, 2, 3]:
            for i in range(5):
                logs.append(
                    schemas.EnrichedLogEntry(
                        project_id=project_id,
                        log_entry=schemas.LogEntry(
                            timestamp=datetime.datetime.now(datetime.timezone.utc),
                            level="info",
                            log_type="console",
                            importance="standard",
                            message=f"Project {project_id} log {i}",
                        ),
                        ingested_at=datetime.datetime.now(datetime.timezone.utc),
                    )
                )

        await queue_service.enqueue_logs_batch(logs)

        for project_id in [1, 2, 3]:
            queue_key = f"queue:logs:{project_id}"
            queue_length = await self.redis.llen(queue_key)
            assert queue_length == 5

        print("✅ Logs for multiple projects enqueued correctly")

    async def test_dequeue_log(self):
        """Test dequeueing a log."""
        log = schemas.EnrichedLogEntry(
            project_id=1,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="info",
                log_type="console",
                importance="standard",
                message="Test log",
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
        )

        await queue_service.enqueue_log(log)

        queue_key = f"queue:logs:1"
        raw_data = await self.redis.brpop(queue_key, timeout=1)

        assert raw_data is not None
        _, payload = raw_data
        unpacked = msgpack.unpackb(payload, raw=False)

        assert unpacked["message"] == "Test log"
        assert unpacked["level"] == "info"
        print("✅ Log dequeued and deserialized successfully")

    async def test_queue_depth_check(self):
        """Test checking queue depth."""
        project_id = 1

        logs = [
            schemas.EnrichedLogEntry(
                project_id=project_id,
                log_entry=schemas.LogEntry(
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    level="info",
                    log_type="console",
                    importance="standard",
                    message=f"Test log {i}",
                ),
                ingested_at=datetime.datetime.now(datetime.timezone.utc),
            )
            for i in range(25)
        ]

        await queue_service.enqueue_logs_batch(logs)

        depth = await queue_service.get_queue_depth(project_id)

        assert depth == 25
        print(f"✅ Queue depth correctly reported: {depth}")

    async def test_backpressure_check(self):
        """Test backpressure detection when queue is full."""
        project_id = 1

        import ingestion_service.config as config
        max_depth = config.settings.QUEUE_MAX_DEPTH

        queue_key = f"queue:logs:{project_id}"
        await self.redis.lpush(queue_key, *[b"dummy"] * max_depth)

        log = schemas.EnrichedLogEntry(
            project_id=project_id,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="info",
                log_type="console",
                importance="standard",
                message="Test log",
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
        )

        with pytest.raises(QueueFullError):
            await queue_service.enqueue_log(log)

        print("✅ Backpressure correctly detected")

    async def test_messagepack_serialization(self):
        """Test MessagePack serialization preserves data."""
        original_log = schemas.EnrichedLogEntry(
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

        await queue_service.enqueue_log(original_log)

        queue_key = f"queue:logs:1"
        raw_data = await self.redis.brpop(queue_key, timeout=1)
        _, payload = raw_data
        unpacked = msgpack.unpackb(payload, raw=False)

        assert unpacked["message"] == original_log.log_entry.message
        assert unpacked["level"] == original_log.log_entry.level
        assert unpacked["error_type"] == original_log.log_entry.error_type
        assert unpacked["attributes"] == original_log.log_entry.attributes
        assert unpacked["error_fingerprint"] == original_log.error_fingerprint
        print("✅ MessagePack serialization preserves all data")

    async def test_queue_fifo_order(self):
        """Test that queue maintains FIFO order."""
        logs = [
            schemas.EnrichedLogEntry(
                project_id=1,
                log_entry=schemas.LogEntry(
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    level="info",
                    log_type="console",
                    importance="standard",
                    message=f"Log {i}",
                ),
                ingested_at=datetime.datetime.now(datetime.timezone.utc),
            )
            for i in range(5)
        ]

        await queue_service.enqueue_logs_batch(logs)

        queue_key = f"queue:logs:1"
        messages = []
        for _ in range(5):
            raw_data = await self.redis.brpop(queue_key, timeout=1)
            _, payload = raw_data
            unpacked = msgpack.unpackb(payload, raw=False)
            messages.append(unpacked["message"])

        assert messages == ["Log 0", "Log 1", "Log 2", "Log 3", "Log 4"]
        print("✅ Queue maintains FIFO order")

    async def test_empty_queue_operations(self):
        """Test operations on empty queue."""
        project_id = 999

        depth = await queue_service.get_queue_depth(project_id)
        assert depth == 0

        queue_key = f"queue:logs:{project_id}"
        result = await self.redis.brpop(queue_key, timeout=1)
        assert result is None

        print("✅ Empty queue operations handled correctly")

    async def test_large_batch_enqueue(self):
        """Test enqueueing large batch of logs."""
        logs = [
            schemas.EnrichedLogEntry(
                project_id=1,
                log_entry=schemas.LogEntry(
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    level="info",
                    log_type="console",
                    importance="standard",
                    message=f"Batch log {i}",
                ),
                ingested_at=datetime.datetime.now(datetime.timezone.utc),
            )
            for i in range(1000)
        ]

        await queue_service.enqueue_logs_batch(logs)

        queue_key = f"queue:logs:1"
        queue_length = await self.redis.llen(queue_key)

        assert queue_length == 1000
        print("✅ Large batch (1000 logs) enqueued successfully")

    async def test_queue_with_complex_attributes(self):
        """Test queue with complex nested attributes."""
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
                    "request": {"method": "POST", "url": "/api/test", "headers": {"Content-Type": "application/json"}},
                    "metrics": {"duration_ms": 150, "db_queries": 5, "cache_hits": 3},
                },
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
        )

        await queue_service.enqueue_log(log)

        queue_key = f"queue:logs:1"
        raw_data = await self.redis.brpop(queue_key, timeout=1)
        _, payload = raw_data
        unpacked = msgpack.unpackb(payload, raw=False)

        assert unpacked["attributes"]["user"]["id"] == 123
        assert "admin" in unpacked["attributes"]["user"]["roles"]
        assert unpacked["attributes"]["request"]["method"] == "POST"
        print("✅ Complex nested attributes preserved")

    async def test_queue_isolation_between_projects(self):
        """Test that queues are isolated between projects."""
        log1 = schemas.EnrichedLogEntry(
            project_id=1,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="info",
                log_type="console",
                importance="standard",
                message="Project 1 log",
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
        )

        log2 = schemas.EnrichedLogEntry(
            project_id=2,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="info",
                log_type="console",
                importance="standard",
                message="Project 2 log",
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
        )

        await queue_service.enqueue_log(log1)
        await queue_service.enqueue_log(log2)

        queue1_key = f"queue:logs:1"
        queue2_key = f"queue:logs:2"

        raw_data1 = await self.redis.brpop(queue1_key, timeout=1)
        raw_data2 = await self.redis.brpop(queue2_key, timeout=1)

        _, payload1 = raw_data1
        _, payload2 = raw_data2

        unpacked1 = msgpack.unpackb(payload1, raw=False)
        unpacked2 = msgpack.unpackb(payload2, raw=False)

        assert unpacked1["message"] == "Project 1 log"
        assert unpacked2["message"] == "Project 2 log"
        print("✅ Queues properly isolated between projects")

    async def test_timestamp_serialization(self):
        """Test that timestamps are correctly serialized and can be deserialized."""
        now = datetime.datetime.now(datetime.timezone.utc)

        log = schemas.EnrichedLogEntry(
            project_id=1,
            log_entry=schemas.LogEntry(
                timestamp=now,
                level="info",
                log_type="console",
                importance="standard",
                message="Timestamp test",
            ),
            ingested_at=now,
        )

        await queue_service.enqueue_log(log)

        queue_key = f"queue:logs:1"
        raw_data = await self.redis.brpop(queue_key, timeout=1)
        _, payload = raw_data
        unpacked = msgpack.unpackb(payload, raw=False)

        assert "timestamp" in unpacked
        assert "ingested_at" in unpacked
        print("✅ Timestamps serialized correctly")
