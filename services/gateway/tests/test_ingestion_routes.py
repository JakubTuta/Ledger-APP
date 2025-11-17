import datetime

import grpc
import pytest

import gateway_service.proto.ingestion_pb2 as ingestion_pb2
import tests.test_base as test_base


@pytest.mark.asyncio
class TestIngestionRoutes(test_base.BaseGatewayTest):
    async def test_ingest_single_log_success(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "console",
            "importance": "standard",
            "message": "Test log message",
        }

        response = await self.client.post(
            "/api/v1/ingest/single",
            json=log_entry,
            headers={"Authorization": "Bearer test_api_key_123"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 1
        assert data["rejected"] == 0
        assert data["message"] == "Log accepted for processing"

    async def test_ingest_single_log_with_all_fields(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "error",
            "log_type": "exception",
            "importance": "high",
            "message": "Exception occurred",
            "error_type": "ValueError",
            "error_message": "Invalid value provided",
            "stack_trace": "Traceback (most recent call last):\n  File test.py, line 1",
            "environment": "production",
            "release": "v1.0.0",
            "sdk_version": "1.2.3",
            "platform": "python",
            "platform_version": "3.12.0",
            "attributes": {"user_id": "123", "request_id": "req_abc"},
        }

        response = await self.client.post(
            "/api/v1/ingest/single",
            json=log_entry,
            headers={"Authorization": "Bearer test_api_key_123"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 1
        assert data["rejected"] == 0

    async def test_ingest_single_log_without_api_key(self, setup_method):
        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "console",
            "importance": "standard",
            "message": "Test log message",
        }

        response = await self.client.post(
            "/api/v1/ingest/single",
            json=log_entry,
        )

        assert response.status_code == 401

    async def test_ingest_single_log_queue_full(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        mock_stub = self.mock_grpc_pool.get_stub("ingestion", None)
        mock_stub.ingest_log_response = None

        class MockError(grpc.RpcError):
            def code(self):
                return grpc.StatusCode.RESOURCE_EXHAUSTED

            def details(self):
                return "Queue full"

        async def raise_error(*args, **kwargs):
            raise MockError()

        mock_stub.IngestLog = raise_error

        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "console",
            "importance": "standard",
            "message": "Test log message",
        }

        response = await self.client.post(
            "/api/v1/ingest/single",
            json=log_entry,
            headers={"Authorization": "Bearer test_api_key_123"},
        )

        assert response.status_code == 503
        assert "queue full" in response.json()["detail"].lower()

    async def test_ingest_batch_logs_success(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        batch_request = {
            "logs": [
                {
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "level": "info",
                    "log_type": "logger",
                    "importance": "standard",
                    "message": f"Test log {i}",
                }
                for i in range(10)
            ]
        }

        response = await self.client.post(
            "/api/v1/ingest/batch",
            json=batch_request,
            headers={"Authorization": "Bearer test_api_key_123"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 10
        assert data["rejected"] == 0
        assert data["errors"] is None

    async def test_ingest_batch_logs_empty_batch(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        batch_request = {"logs": []}

        response = await self.client.post(
            "/api/v1/ingest/batch",
            json=batch_request,
            headers={"Authorization": "Bearer test_api_key_123"},
        )

        assert response.status_code == 422

    async def test_ingest_batch_logs_with_errors(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        mock_stub = self.mock_grpc_pool.get_stub("ingestion", None)
        mock_stub.ingest_log_batch_response = ingestion_pb2.IngestLogBatchResponse(
            success=True,
            queued=8,
            failed=2,
            error="Log 2: Invalid timestamp; Log 5: Message too long",
        )

        batch_request = {
            "logs": [
                {
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "level": "info",
                    "log_type": "logger",
                    "importance": "standard",
                    "message": f"Test log {i}",
                }
                for i in range(10)
            ]
        }

        response = await self.client.post(
            "/api/v1/ingest/batch",
            json=batch_request,
            headers={"Authorization": "Bearer test_api_key_123"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 8
        assert data["rejected"] == 2
        assert len(data["errors"]) == 2

    async def test_ingest_batch_logs_queue_full(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        mock_stub = self.mock_grpc_pool.get_stub("ingestion", None)

        class MockError(grpc.RpcError):
            def code(self):
                return grpc.StatusCode.RESOURCE_EXHAUSTED

            def details(self):
                return "Queue full"

        async def raise_error(*args, **kwargs):
            raise MockError()

        mock_stub.IngestLogBatch = raise_error

        batch_request = {
            "logs": [
                {
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "level": "info",
                    "log_type": "logger",
                    "importance": "standard",
                    "message": "Test log",
                }
            ]
        }

        response = await self.client.post(
            "/api/v1/ingest/batch",
            json=batch_request,
            headers={"Authorization": "Bearer test_api_key_123"},
        )

        assert response.status_code == 503
        assert "queue full" in response.json()["detail"].lower()

    async def test_ingest_batch_logs_without_api_key(self, setup_method):
        batch_request = {
            "logs": [
                {
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "level": "info",
                    "log_type": "logger",
                    "importance": "standard",
                    "message": "Test log",
                }
            ]
        }

        response = await self.client.post(
            "/api/v1/ingest/batch",
            json=batch_request,
        )

        assert response.status_code == 401

    async def test_get_queue_depth_success(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        mock_stub = self.mock_grpc_pool.get_stub("ingestion", None)
        mock_stub.get_queue_depth_response = ingestion_pb2.QueueDepthResponse(
            depth=1500
        )

        response = await self.client.get(
            "/api/v1/queue/depth",
            headers={"Authorization": "Bearer test_api_key_123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == 1
        assert data["queue_depth"] == 1500

    async def test_get_queue_depth_without_api_key(self, setup_method):
        response = await self.client.get("/api/v1/queue/depth")
        assert response.status_code == 401

    async def test_ingestion_with_rate_limiting(self, setup_method):
        await self.set_api_key_cache(
            "test_api_key_123",
            project_id=1,
            rate_limit_per_minute=5,
            rate_limit_per_hour=100,
        )

        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "console",
            "importance": "standard",
            "message": "Test log message",
        }

        for i in range(5):
            response = await self.client.post(
                "/api/v1/ingest/single",
                json=log_entry,
                headers={"Authorization": "Bearer test_api_key_123"},
            )
            assert response.status_code == 202

        response = await self.client.post(
            "/api/v1/ingest/single",
            json=log_entry,
            headers={"Authorization": "Bearer test_api_key_123"},
        )
        assert response.status_code == 429

    async def test_ingest_batch_large_payload(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        batch_request = {
            "logs": [
                {
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "level": "info",
                    "log_type": "custom",
                    "importance": "standard",
                    "message": "x" * 1000,
                    "attributes": {f"key_{j}": "value" * 10 for j in range(10)},
                }
                for i in range(100)
            ]
        }

        response = await self.client.post(
            "/api/v1/ingest/batch",
            json=batch_request,
            headers={"Authorization": "Bearer test_api_key_123"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 100
        assert data["rejected"] == 0

    async def test_ingest_single_log_minimal_fields(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "logger",
            "importance": "standard",
        }

        response = await self.client.post(
            "/api/v1/ingest/single",
            json=log_entry,
            headers={"Authorization": "Bearer test_api_key_123"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 1
