import pytest

import gateway_service.proto.ingestion_pb2 as ingestion_pb2
import tests.test_base as test_base


@pytest.mark.asyncio
class TestIngestionRoutes(test_base.BaseGatewayTest):
    async def test_get_queue_depth_success(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        mock_stub = self.mock_grpc_pool.get_stub("ingestion", None)
        mock_stub.get_queue_depth_response = ingestion_pb2.QueueDepthResponse(depth=1500)

        response = await self.client.get(
            "/api/v1/queue/depth",
            headers={"X-API-Key": "test_api_key_123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == 1
        assert data["queue_depth"] == 1500

    async def test_get_queue_depth_without_api_key(self, setup_method):
        response = await self.client.get("/api/v1/queue/depth")
        assert response.status_code == 401
