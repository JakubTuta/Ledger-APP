import asyncio
import json
from unittest.mock import patch

import pytest
import redis.asyncio as redis

import gateway_service.main as main
import gateway_service.proto.auth_pb2 as auth_pb2

from .sse_client import ASGISSEStream, build_http_scope
from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestLogTailSSE(BaseGatewayTest):
    async def test_tail_requires_authentication(self):
        response = await self.client.get("/api/v1/logs/tail?project_id=1")

        assert response.status_code == 401

    async def test_tail_connection_and_connected_event(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        scope = build_http_scope(
            "GET",
            "/api/v1/logs/tail",
            query_string=b"project_id=1",
            headers={"X-API-Key": "test-api-key"},
        )
        async with ASGISSEStream(main.app, scope) as stream:
            assert stream.status_code == 200
            headers = dict(stream.headers)
            assert headers[b"content-type"] == b"text/event-stream; charset=utf-8"

            event = await stream.next_event()
            assert event["event"] == "connected"

    @pytest.mark.slow
    async def test_tail_receives_log_event(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        redis_client = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)

        try:

            async def publish_tail_event():
                await asyncio.sleep(0.5)
                summary = {
                    "id": "abc123",
                    "project_id": 1,
                    "level": "info",
                    "log_type": "console",
                    "message": "Hello from tail",
                }
                await redis_client.publish("logs:tail:1", json.dumps(summary))

            publisher_task = asyncio.create_task(publish_tail_event())

            scope = build_http_scope(
                "GET",
                "/api/v1/logs/tail",
                query_string=b"project_id=1",
                headers={"X-API-Key": "test-api-key"},
            )
            async with ASGISSEStream(main.app, scope, timeout=5.0) as stream:
                assert stream.status_code == 200

                event = await stream.next_event()
                assert event["event"] == "connected"

                log_event = await stream.next_event()
                assert log_event["event"] == "log"
                log_data = json.loads(log_event["data"])

            await publisher_task

            assert log_data["message"] == "Hello from tail"

        finally:
            await redis_client.close()

    async def test_tail_disabled_returns_503(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        with patch("gateway_service.config.settings.NOTIFICATIONS_ENABLED", False):
            response = await self.client.get(
                "/api/v1/logs/tail?project_id=1", headers={"X-API-Key": "test-api-key"}
            )

            assert response.status_code == 503

    async def test_tail_requires_project_membership(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        stub = self.get_mock_auth_stub()

        async def not_a_member(request, timeout=None):
            return auth_pb2.GetProjectRoleResponse(is_member=False, role="")

        stub.GetProjectRole = not_a_member

        response = await self.client.get(
            "/api/v1/logs/tail?project_id=999", headers={"X-API-Key": "test-api-key"}
        )

        assert response.status_code == 403
