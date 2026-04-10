import datetime
import time

import pytest
import sqlalchemy
from ingestion_service import models, schemas
from ingestion_service.services import queue_service
from ingestion_service.worker import StorageWorker

from .test_base import BaseIngestionTest


@pytest.mark.asyncio
class TestStorageWorker(BaseIngestionTest):
    """Test storage worker operations."""

    def _make_log(
        self,
        project_id: int = 1,
        message: str = "Test log",
        level: str = "info",
        log_type: str = "console",
    ) -> schemas.EnrichedLogEntry:
        return schemas.EnrichedLogEntry(
            project_id=project_id,
            log_entry=schemas.LogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                level=level,
                log_type=log_type,
                importance="standard",
                message=message,
            ),
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
        )

    async def test_worker_processes_single_log(self):
        """Worker inserts a single log payload into the database."""
        log = self._make_log(message="Test worker log")
        await queue_service.enqueue_log(log)

        payload = await self.consume_one_payload()
        assert payload is not None

        worker = StorageWorker(worker_id=1)
        await worker.process_logs_batch([payload])

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(models.Log))
            logs = result.scalars().all()
            assert len(logs) == 1
            assert logs[0].message == "Test worker log"

    async def test_worker_processes_batch(self):
        """Worker bulk-inserts multiple log payloads."""
        logs = [self._make_log(message=f"Batch log {i}") for i in range(10)]
        await queue_service.enqueue_logs_batch(logs)

        payloads = await self.consume_all_payloads(10)
        assert len(payloads) == 10

        worker = StorageWorker(worker_id=1)
        await worker.process_logs_batch(payloads)

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(models.Log))
            stored = result.scalars().all()
            assert len(stored) == 10

    async def test_worker_creates_error_group(self):
        """Worker creates an error group for exception logs with fingerprint."""
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

        payload = await self.consume_one_payload()
        assert payload is not None

        worker = StorageWorker(worker_id=1)
        await worker.process_logs_batch([payload])

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(models.ErrorGroup))
            error_groups = result.scalars().all()
            assert len(error_groups) == 1
            assert error_groups[0].fingerprint == "a" * 64
            assert error_groups[0].occurrence_count == 1

    async def test_worker_updates_error_group_count(self):
        """Worker increments occurrence_count for duplicate fingerprints."""
        fingerprint = "b" * 64
        logs = [
            schemas.EnrichedLogEntry(
                project_id=1,
                log_entry=schemas.LogEntry(
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    level="error",
                    log_type="exception",
                    importance="high",
                    message=f"Test error {i}",
                    error_type="ValueError",
                    error_message="Invalid value",
                    stack_trace="Traceback...",
                    platform="python",
                ),
                ingested_at=datetime.datetime.now(datetime.timezone.utc),
                error_fingerprint=fingerprint,
            )
            for i in range(2)
        ]
        await queue_service.enqueue_logs_batch(logs)

        payloads = await self.consume_all_payloads(2)
        assert len(payloads) == 2

        worker = StorageWorker(worker_id=1)
        await worker.process_logs_batch(payloads)

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(
                sqlalchemy.select(models.ErrorGroup).where(
                    models.ErrorGroup.fingerprint == fingerprint
                )
            )
            error_group = result.scalar_one()
            assert error_group.occurrence_count == 2

    async def test_worker_preserves_attributes(self):
        """Worker preserves JSONB attributes exactly."""
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

        payload = await self.consume_one_payload()
        assert payload is not None

        worker = StorageWorker(worker_id=1)
        await worker.process_logs_batch([payload])

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(models.Log))
            stored_log = result.scalar_one()
            assert stored_log.attributes == attributes
            assert stored_log.attributes["user_id"] == 123
            assert len(stored_log.attributes["items"]) == 2

    async def test_worker_stores_all_fields(self):
        """Worker stores every log field in the database correctly."""
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

        payload = await self.consume_one_payload()
        assert payload is not None

        worker = StorageWorker(worker_id=1)
        await worker.process_logs_batch([payload])

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(models.Log))
            stored = result.scalar_one()
            assert stored.project_id == 123
            assert stored.level == "warning"
            assert stored.log_type == "network"
            assert stored.importance == "high"
            assert stored.message == "Network request failed"
            assert stored.environment == "production"
            assert stored.release == "v2.0.0"
            assert stored.sdk_version == "1.5.0"
            assert stored.platform == "nodejs"
            assert stored.platform_version == "20.10.0"

    async def test_worker_bulk_insert_performance(self):
        """Worker inserts 100 logs in under 1 second."""
        logs = [self._make_log(message=f"Perf log {i}") for i in range(100)]
        await queue_service.enqueue_logs_batch(logs)

        payloads = await self.consume_all_payloads(100)
        assert len(payloads) == 100

        worker = StorageWorker(worker_id=1)
        start = time.time()
        await worker.process_logs_batch(payloads)
        duration = time.time() - start

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(
                sqlalchemy.select(sqlalchemy.func.count(models.Log.id))
            )
            count = result.scalar()
            assert count == 100
            assert duration < 1.0

    async def test_worker_handles_different_projects(self):
        """Worker correctly stores logs from multiple projects."""
        log1 = self._make_log(project_id=1, message="Project 1 log")
        log2 = self._make_log(project_id=2, message="Project 2 log")
        await queue_service.enqueue_logs_batch([log1, log2])

        payloads = await self.consume_all_payloads(2)
        assert len(payloads) == 2

        worker = StorageWorker(worker_id=1)
        await worker.process_logs_batch(payloads)

        async with self.test_db_manager.session_factory() as session:
            result1 = await session.execute(
                sqlalchemy.select(models.Log).where(models.Log.project_id == 1)
            )
            result2 = await session.execute(
                sqlalchemy.select(models.Log).where(models.Log.project_id == 2)
            )
            logs1 = result1.scalars().all()
            logs2 = result2.scalars().all()
            assert len(logs1) == 1
            assert len(logs2) == 1
            assert logs1[0].message == "Project 1 log"
            assert logs2[0].message == "Project 2 log"

    async def test_worker_error_group_isolation_by_project(self):
        """Error groups with the same fingerprint are isolated by project_id."""
        fingerprint = "c" * 64
        logs = [
            schemas.EnrichedLogEntry(
                project_id=pid,
                log_entry=schemas.LogEntry(
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    level="error",
                    log_type="exception",
                    importance="high",
                    message=f"Error in project {pid}",
                    error_type="TestError",
                    error_message="Test",
                    stack_trace="Traceback...",
                    platform="python",
                ),
                ingested_at=datetime.datetime.now(datetime.timezone.utc),
                error_fingerprint=fingerprint,
            )
            for pid in [1, 2]
        ]
        await queue_service.enqueue_logs_batch(logs)

        payloads = await self.consume_all_payloads(2)
        assert len(payloads) == 2

        worker = StorageWorker(worker_id=1)
        await worker.process_logs_batch(payloads)

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(models.ErrorGroup))
            error_groups = result.scalars().all()
            assert len(error_groups) == 2
            assert {eg.project_id for eg in error_groups} == {1, 2}

    async def test_worker_large_batch_processing(self):
        """Worker processes 500 logs in a single batch."""
        logs = [self._make_log(message=f"Large batch log {i}") for i in range(500)]
        await queue_service.enqueue_logs_batch(logs)

        payloads = await self.consume_all_payloads(500)
        assert len(payloads) == 500

        worker = StorageWorker(worker_id=1)
        await worker.process_logs_batch(payloads)

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(
                sqlalchemy.select(sqlalchemy.func.count(models.Log.id))
            )
            count = result.scalar()
            assert count == 500
