import datetime

import msgpack
import pytest
import sqlalchemy
from ingestion_service import models, schemas
from ingestion_service.services import queue_service
from ingestion_service.worker import StorageWorker

from .test_base import BaseIngestionTest


@pytest.mark.asyncio
class TestStorageWorker(BaseIngestionTest):
    """Test storage worker operations."""

    async def test_worker_processes_single_log(self):
        """Test worker processes a single log from queue."""
        log = schemas.EnrichedLogEntry(
            project_id=1,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="info",
                log_type="console",
                importance="standard",
                message="Test worker log",
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
        )

        await queue_service.enqueue_log(log)

        worker = StorageWorker(worker_id=1)

        queue_key = f"queue:logs:1"
        raw_data = await self.redis.brpop(queue_key, timeout=1)

        if raw_data:
            _, payload = raw_data
            unpacked = msgpack.unpackb(payload, raw=False)

            await worker.process_logs_batch([unpacked])

            async with self.test_db_manager.session_factory() as session:
                result = await session.execute(sqlalchemy.select(models.Log))
                logs = result.scalars().all()

                assert len(logs) == 1
                assert logs[0].message == "Test worker log"
                print("✅ Worker processed single log successfully")

    async def test_worker_processes_batch(self):
        """Test worker processes multiple logs in batch."""
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
            for i in range(10)
        ]

        await queue_service.enqueue_logs_batch(logs)

        worker = StorageWorker(worker_id=1)

        queue_key = f"queue:logs:1"
        log_dicts = []

        for _ in range(10):
            raw_data = await self.redis.brpop(queue_key, timeout=1)
            if raw_data:
                _, payload = raw_data
                unpacked = msgpack.unpackb(payload, raw=False)
                log_dicts.append(unpacked)

        await worker.process_logs_batch(log_dicts)

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(models.Log))
            stored_logs = result.scalars().all()

            assert len(stored_logs) == 10
            print("✅ Worker processed 10 logs in batch successfully")

    async def test_worker_creates_error_group(self):
        """Test worker creates error group for exception logs."""
        log = schemas.EnrichedLogEntry(
            project_id=1,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="error",
                log_type="exception",
                importance="high",
                message="Test error",
                error_type="ValueError",
                error_message="Invalid value",
                stack_trace="Traceback...",
                platform="python",
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
            error_fingerprint="a" * 64,
        )

        await queue_service.enqueue_log(log)

        worker = StorageWorker(worker_id=1)

        queue_key = f"queue:logs:1"
        raw_data = await self.redis.brpop(queue_key, timeout=1)
        _, payload = raw_data
        unpacked = msgpack.unpackb(payload, raw=False)

        await worker.process_logs_batch([unpacked])

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(models.ErrorGroup))
            error_groups = result.scalars().all()

            assert len(error_groups) == 1
            assert error_groups[0].fingerprint == "a" * 64
            assert error_groups[0].occurrence_count == 1
            print("✅ Worker created error group successfully")

    async def test_worker_updates_error_group_count(self):
        """Test worker increments error group count for duplicate errors."""
        fingerprint = "b" * 64

        log1 = schemas.EnrichedLogEntry(
            project_id=1,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="error",
                log_type="exception",
                importance="high",
                message="Test error 1",
                error_type="ValueError",
                error_message="Invalid value",
                stack_trace="Traceback...",
                platform="python",
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
            error_fingerprint=fingerprint,
        )

        log2 = schemas.EnrichedLogEntry(
            project_id=1,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="error",
                log_type="exception",
                importance="high",
                message="Test error 2",
                error_type="ValueError",
                error_message="Invalid value",
                stack_trace="Traceback...",
                platform="python",
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
            error_fingerprint=fingerprint,
        )

        await queue_service.enqueue_logs_batch([log1, log2])

        worker = StorageWorker(worker_id=1)

        queue_key = f"queue:logs:1"
        log_dicts = []
        for _ in range(2):
            raw_data = await self.redis.brpop(queue_key, timeout=1)
            _, payload = raw_data
            log_dicts.append(msgpack.unpackb(payload, raw=False))

        await worker.process_logs_batch(log_dicts)

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(
                sqlalchemy.select(models.ErrorGroup).where(models.ErrorGroup.fingerprint == fingerprint)
            )
            error_group = result.scalar_one()

            assert error_group.occurrence_count == 2
            print("✅ Worker incremented error group count successfully")

    async def test_worker_preserves_attributes(self):
        """Test worker preserves JSONB attributes."""
        attributes = {
            "user_id": 123,
            "action": "purchase",
            "items": [{"id": 1, "price": 29.99}, {"id": 2, "price": 49.99}],
        }

        log = schemas.EnrichedLogEntry(
            project_id=1,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="info",
                log_type="custom",
                importance="standard",
                message="Test attributes",
                attributes=attributes,
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
        )

        await queue_service.enqueue_log(log)

        worker = StorageWorker(worker_id=1)

        queue_key = f"queue:logs:1"
        raw_data = await self.redis.brpop(queue_key, timeout=1)
        _, payload = raw_data
        unpacked = msgpack.unpackb(payload, raw=False)

        await worker.process_logs_batch([unpacked])

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(models.Log))
            stored_log = result.scalar_one()

            assert stored_log.attributes == attributes
            assert stored_log.attributes["user_id"] == 123
            assert len(stored_log.attributes["items"]) == 2
            print("✅ Worker preserved JSONB attributes successfully")

    async def test_worker_stores_all_fields(self):
        """Test worker stores all log fields correctly."""
        now = datetime.datetime.now(datetime.timezone.utc)

        log = schemas.EnrichedLogEntry(
            project_id=123,
            log_entry=schemas.LogEntry(
                timestamp=now,
                level="warning",
                log_type="network",
                importance="high",
                message="Network request failed",
                environment="production",
                release="v2.0.0",
                sdk_version="1.5.0",
                platform="nodejs",
                platform_version="20.10.0",
                attributes={"url": "https://api.example.com", "status": 500},
            ),
            ingested_at=now,
        )

        await queue_service.enqueue_log(log)

        worker = StorageWorker(worker_id=1)

        queue_key = f"queue:logs:123"
        raw_data = await self.redis.brpop(queue_key, timeout=1)
        _, payload = raw_data
        unpacked = msgpack.unpackb(payload, raw=False)

        await worker.process_logs_batch([unpacked])

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(models.Log))
            stored_log = result.scalar_one()

            assert stored_log.project_id == 123
            assert stored_log.level == "warning"
            assert stored_log.log_type == "network"
            assert stored_log.importance == "high"
            assert stored_log.message == "Network request failed"
            assert stored_log.environment == "production"
            assert stored_log.release == "v2.0.0"
            assert stored_log.sdk_version == "1.5.0"
            assert stored_log.platform == "nodejs"
            assert stored_log.platform_version == "20.10.0"
            print("✅ Worker stored all fields correctly")

    async def test_worker_bulk_insert_performance(self):
        """Test worker bulk insert performance."""
        import time

        logs = [
            schemas.EnrichedLogEntry(
                project_id=1,
                log_entry=schemas.LogEntry(
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    level="info",
                    log_type="logger",
                    importance="standard",
                    message=f"Performance test log {i}",
                ),
                ingested_at=datetime.datetime.now(datetime.timezone.utc),
            )
            for i in range(100)
        ]

        await queue_service.enqueue_logs_batch(logs)

        worker = StorageWorker(worker_id=1)

        queue_key = f"queue:logs:1"
        log_dicts = []
        for _ in range(100):
            raw_data = await self.redis.brpop(queue_key, timeout=1)
            if raw_data:
                _, payload = raw_data
                log_dicts.append(msgpack.unpackb(payload, raw=False))

        start = time.time()
        await worker.process_logs_batch(log_dicts)
        duration = time.time() - start

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(sqlalchemy.func.count(models.Log.id)))
            count = result.scalar()

            assert count == 100
            assert duration < 1.0
            print(f"✅ Worker inserted 100 logs in {duration:.3f}s")

    async def test_worker_handles_different_projects(self):
        """Test worker correctly separates logs by project."""
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

        worker = StorageWorker(worker_id=1)

        log_dicts = []
        for project_id in [1, 2]:
            queue_key = f"queue:logs:{project_id}"
            raw_data = await self.redis.brpop(queue_key, timeout=1)
            if raw_data:
                _, payload = raw_data
                log_dicts.append(msgpack.unpackb(payload, raw=False))

        await worker.process_logs_batch(log_dicts)

        async with self.test_db_manager.session_factory() as session:
            result1 = await session.execute(sqlalchemy.select(models.Log).where(models.Log.project_id == 1))
            result2 = await session.execute(sqlalchemy.select(models.Log).where(models.Log.project_id == 2))

            logs1 = result1.scalars().all()
            logs2 = result2.scalars().all()

            assert len(logs1) == 1
            assert len(logs2) == 1
            assert logs1[0].message == "Project 1 log"
            assert logs2[0].message == "Project 2 log"
            print("✅ Worker handled different projects correctly")

    async def test_worker_error_group_isolation(self):
        """Test error groups are isolated by project."""
        fingerprint = "c" * 64

        log1 = schemas.EnrichedLogEntry(
            project_id=1,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="error",
                log_type="exception",
                importance="high",
                message="Error in project 1",
                error_type="TestError",
                error_message="Test",
                stack_trace="Traceback...",
                platform="python",
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
            error_fingerprint=fingerprint,
        )

        log2 = schemas.EnrichedLogEntry(
            project_id=2,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level="error",
                log_type="exception",
                importance="high",
                message="Error in project 2",
                error_type="TestError",
                error_message="Test",
                stack_trace="Traceback...",
                platform="python",
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
            error_fingerprint=fingerprint,
        )

        await queue_service.enqueue_log(log1)
        await queue_service.enqueue_log(log2)

        worker = StorageWorker(worker_id=1)

        log_dicts = []
        for project_id in [1, 2]:
            queue_key = f"queue:logs:{project_id}"
            raw_data = await self.redis.brpop(queue_key, timeout=1)
            if raw_data:
                _, payload = raw_data
                log_dicts.append(msgpack.unpackb(payload, raw=False))

        await worker.process_logs_batch(log_dicts)

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(models.ErrorGroup))
            error_groups = result.scalars().all()

            assert len(error_groups) == 2
            project_ids = {eg.project_id for eg in error_groups}
            assert project_ids == {1, 2}
            print("✅ Error groups correctly isolated by project")

    async def test_worker_large_batch_processing(self):
        """Test worker processes large batch efficiently."""
        logs = [
            schemas.EnrichedLogEntry(
                project_id=1,
                log_entry=schemas.LogEntry(
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    level="info",
                    log_type="logger",
                    importance="standard",
                    message=f"Large batch log {i}",
                ),
                ingested_at=datetime.datetime.now(datetime.timezone.utc),
            )
            for i in range(500)
        ]

        await queue_service.enqueue_logs_batch(logs)

        worker = StorageWorker(worker_id=1)

        queue_key = f"queue:logs:1"
        log_dicts = []
        while True:
            raw_data = await self.redis.brpop(queue_key, timeout=1)
            if raw_data:
                _, payload = raw_data
                log_dicts.append(msgpack.unpackb(payload, raw=False))
            else:
                break

        assert len(log_dicts) == 500, f"Expected 500 logs in queue, got {len(log_dicts)}"

        await worker.process_logs_batch(log_dicts)

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(sqlalchemy.func.count(models.Log.id)))
            count = result.scalar()

            assert count == 500
            print("Worker processed 500 logs successfully")
