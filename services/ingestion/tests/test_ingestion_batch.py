import datetime

import pytest

import ingestion_service.proto.ingestion_pb2 as ingestion_pb2

from .helpers import create_proto_log
from .test_base import BaseIngestionTest


@pytest.mark.asyncio
class TestBatchLogIngestion(BaseIngestionTest):
    """Test batch log ingestion endpoint."""

    async def test_ingest_small_batch(self):
        """Test ingesting a small batch of logs."""
        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "console",
                "importance": "standard",
                "message": f"Batch log {i}",
            }
            for i in range(10)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 10
        print("✅ Small batch (10 logs) ingested successfully")

    async def test_ingest_medium_batch(self):
        """Test ingesting a medium-sized batch."""
        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "console",
                "importance": "standard",
                "message": f"Batch log {i}",
            }
            for i in range(100)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 100
        print("✅ Medium batch (100 logs) ingested successfully")

    async def test_ingest_large_batch(self):
        """Test ingesting a large batch."""
        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "logger",
                "importance": "standard",
                "message": f"Large batch log {i}",
            }
            for i in range(1000)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 1000
        print("✅ Large batch (1000 logs) ingested successfully")

    async def test_batch_with_mixed_levels(self):
        """Test batch with different log levels."""
        levels = ["debug", "info", "warning", "error", "critical"]
        logs = []

        for i in range(50):
            logs.append(
                {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "level": levels[i % len(levels)],
                    "log_type": "logger",
                    "importance": "standard",
                    "message": f"Log {i} with level {levels[i % len(levels)]}",
                }
            )

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 50
        print("✅ Batch with mixed levels ingested successfully")

    async def test_batch_with_mixed_types(self):
        """Test batch with different log types."""
        log_types = ["console", "logger", "network", "database", "custom"]
        logs = []

        for i in range(25):
            logs.append(
                {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "level": "info",
                    "log_type": log_types[i % len(log_types)],
                    "importance": "standard",
                    "message": f"Log {i} of type {log_types[i % len(log_types)]}",
                }
            )

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 25
        print("✅ Batch with mixed types ingested successfully")

    async def test_batch_with_exceptions(self):
        """Test batch containing exception logs."""
        logs = []

        for i in range(20):
            log = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "console",
                "importance": "standard",
                "message": f"Regular log {i}",
            }

            if i % 5 == 0:
                log = {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "level": "error",
                    "log_type": "exception",
                    "importance": "high",
                    "message": f"Exception {i}",
                    "error_type": "ValueError",
                    "error_message": f"Value error {i}",
                    "stack_trace": f"Traceback for error {i}",
                    "platform": "python",
                }

            logs.append(log)

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 20
        print("✅ Batch with exceptions ingested successfully")

    async def test_batch_with_attributes(self):
        """Test batch logs with custom attributes."""
        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "custom",
                "importance": "standard",
                "message": f"Log {i}",
                "attributes": {
                    "user_id": i,
                    "session_id": f"session_{i}",
                    "action": "page_view",
                    "duration_ms": i * 10,
                },
            }
            for i in range(30)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 30
        print("✅ Batch with attributes ingested successfully")

    async def test_batch_performance_100(self):
        """Test batch ingestion performance with 100 logs."""
        import time

        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "logger",
                "importance": "standard",
                "message": f"Performance test log {i}",
                "attributes": {"index": i, "batch": "performance_test"},
            }
            for i in range(100)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        start = time.time()
        response = await self.stub.IngestLogBatch(request)
        duration = time.time() - start

        assert response.success is True
        assert duration < 1.0
        print(f"✅ 100 logs ingested in {duration:.3f}s")

    async def test_batch_performance_500(self):
        """Test batch ingestion performance with 500 logs."""
        import time

        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "logger",
                "importance": "standard",
                "message": f"Performance test log {i}",
            }
            for i in range(500)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        start = time.time()
        response = await self.stub.IngestLogBatch(request)
        duration = time.time() - start

        assert response.success is True
        assert duration < 2.0
        print(f"✅ 500 logs ingested in {duration:.3f}s")

    async def test_batch_with_future_timestamps(self):
        """Test batch with some future timestamps within tolerance."""
        base_time = datetime.datetime.now(datetime.timezone.utc)
        logs = []

        for i in range(10):
            timestamp = base_time + datetime.timedelta(seconds=i * 10)
            logs.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "level": "info",
                    "log_type": "console",
                    "importance": "standard",
                    "message": f"Log {i}",
                }
            )

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        print("✅ Batch with sequential timestamps ingested successfully")

    async def test_batch_with_environment_tags(self):
        """Test batch with environment and release tags."""
        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "logger",
                "importance": "standard",
                "message": f"Deployment log {i}",
                "environment": "production",
                "release": "v1.5.0",
                "sdk_version": "2.0.0",
            }
            for i in range(20)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 20
        print("✅ Batch with environment tags ingested successfully")

    async def test_batch_network_logs(self):
        """Test batch of network/API logs."""
        methods = ["GET", "POST", "PUT", "DELETE"]
        status_codes = [200, 201, 400, 404, 500]

        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "network",
                "importance": "standard",
                "message": f"API request {i}",
                "attributes": {
                    "method": methods[i % len(methods)],
                    "url": f"/api/v1/resource/{i}",
                    "status_code": status_codes[i % len(status_codes)],
                    "duration_ms": 50 + (i % 200),
                },
            }
            for i in range(40)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 40
        print("✅ Batch of network logs ingested successfully")

    async def test_batch_database_logs(self):
        """Test batch of database query logs."""
        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "debug",
                "log_type": "database",
                "importance": "low",
                "message": f"Database query {i}",
                "attributes": {
                    "query_type": "SELECT" if i % 2 == 0 else "INSERT",
                    "table": f"table_{i % 5}",
                    "duration_ms": 5 + (i % 20),
                    "rows_affected": i % 10,
                },
            }
            for i in range(50)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 50
        print("✅ Batch of database logs ingested successfully")

    async def test_batch_all_importance_levels(self):
        """Test batch with all importance levels."""
        importance_levels = ["critical", "high", "standard", "low"]
        logs = []

        for i in range(40):
            logs.append(
                {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "level": "info",
                    "log_type": "logger",
                    "importance": importance_levels[i % len(importance_levels)],
                    "message": f"Log {i} with {importance_levels[i % len(importance_levels)]} importance",
                }
            )

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 40
        print("✅ Batch with all importance levels ingested successfully")

    async def test_batch_with_platform_info(self):
        """Test batch with different platform information."""
        platforms = [
            ("python", "3.12.0"),
            ("nodejs", "20.10.0"),
            ("java", "17.0.5"),
            ("go", "1.21.0"),
        ]

        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "logger",
                "importance": "standard",
                "message": f"Log from {platforms[i % len(platforms)][0]}",
                "platform": platforms[i % len(platforms)][0],
                "platform_version": platforms[i % len(platforms)][1],
            }
            for i in range(20)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 20
        print("✅ Batch with platform info ingested successfully")

    async def test_batch_response_format(self):
        """Test that batch response has correct format."""
        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "console",
                "importance": "standard",
                "message": "Test log",
            }
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 1
        print("✅ Batch response format is correct")

    async def test_max_batch_size_boundary(self):
        """Test batch at maximum allowed size."""
        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "console",
                "importance": "standard",
                "message": f"Log {i}",
            }
            for i in range(1000)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 1000
        print("✅ Maximum batch size (1000) ingested successfully")

    async def test_concurrent_batch_ingestions(self):
        """Test multiple concurrent batch ingestions."""
        import asyncio

        async def ingest_batch(batch_num):
            logs = [
                {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "level": "info",
                    "log_type": "console",
                    "importance": "standard",
                    "message": f"Batch {batch_num} log {i}",
                }
                for i in range(50)
            ]
            proto_logs = [create_proto_log(log) for log in logs]
            request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)
            return await self.stub.IngestLogBatch(request)

        tasks = [ingest_batch(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert all(r.success is True for r in results)
        total_queued = sum(r.queued for r in results)
        assert total_queued == 500
        print("✅ 10 concurrent batches (500 logs total) ingested successfully")

    async def test_queue_depth_endpoint(self):
        """Test queue depth check endpoint."""
        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "console",
                "importance": "standard",
                "message": f"Queue test log {i}",
            }
            for i in range(25)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        await self.stub.IngestLogBatch(request)

        depth_request = ingestion_pb2.QueueDepthRequest(project_id=1)
        response = await self.stub.GetQueueDepth(depth_request)

        assert response.depth >= 0
        print("✅ Queue depth endpoint accessible")
