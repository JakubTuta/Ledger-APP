import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import redis.asyncio as redis

from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestNotificationsSSE(BaseGatewayTest):

    async def test_sse_requires_authentication(self):
        response = await self.client.get("/api/v1/notifications/stream")

        assert response.status_code == 401

    async def test_sse_connection_with_api_key(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        async with self.client.stream(
            "GET",
            "/api/v1/notifications/stream",
            headers={"X-API-Key": "test-api-key"},
            timeout=httpx.Timeout(5.0)
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

            received_connected = False
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                    if event_type == "connected":
                        received_connected = True
                        break

            assert received_connected

    async def test_sse_connected_event_contains_project_list(self):
        await self.set_api_key_cache("test-api-key", project_id=123, account_id=1)

        async with self.client.stream(
            "GET",
            "/api/v1/notifications/stream",
            headers={"X-API-Key": "test-api-key"},
            timeout=httpx.Timeout(5.0)
        ) as response:
            assert response.status_code == 200

            event_data = None
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data_str = line.split(":", 1)[1].strip()
                    event_data = json.loads(data_str)
                    break

            assert event_data is not None
            assert "projects" in event_data
            assert "timestamp" in event_data
            assert 123 in event_data["projects"]

    async def test_sse_notifications_disabled_returns_503(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        with patch("gateway_service.config.settings.NOTIFICATIONS_ENABLED", False):
            response = await self.client.get(
                "/api/v1/notifications/stream",
                headers={"X-API-Key": "test-api-key"}
            )

            assert response.status_code == 503
            assert "disabled" in response.json()["detail"].lower()

    async def test_notification_health_endpoint(self):
        response = await self.client.get("/api/v1/notifications/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "enabled" in data
        assert "heartbeat_interval" in data
        assert data["status"] == "healthy"

    @pytest.mark.slow
    async def test_sse_receives_error_notification(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        redis_client = redis.Redis.from_url(
            "redis://localhost:6379/0",
            decode_responses=True
        )

        try:
            async def publish_notification():
                await asyncio.sleep(0.5)
                notification = {
                    "project_id": 1,
                    "level": "error",
                    "log_type": "exception",
                    "message": "Test error notification",
                    "error_type": "TestError",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                await redis_client.publish(
                    "notifications:errors:1",
                    json.dumps(notification)
                )

            publisher_task = asyncio.create_task(publish_notification())

            received_error = False
            error_data = None

            async with self.client.stream(
                "GET",
                "/api/v1/notifications/stream",
                headers={"X-API-Key": "test-api-key"},
                timeout=httpx.Timeout(3.0)
            ) as response:
                assert response.status_code == 200

                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                        if event_type == "error_notification":
                            received_error = True
                    elif line.startswith("data:") and received_error:
                        data_str = line.split(":", 1)[1].strip()
                        error_data = json.loads(data_str)
                        break

            await publisher_task

            assert received_error
            assert error_data is not None
            assert error_data["level"] == "error"
            assert error_data["message"] == "Test error notification"

        finally:
            await redis_client.close()

    @pytest.mark.slow
    async def test_sse_heartbeat_events(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        with patch("gateway_service.config.settings.NOTIFICATIONS_HEARTBEAT_INTERVAL", 1):
            heartbeat_received = False

            async with self.client.stream(
                "GET",
                "/api/v1/notifications/stream",
                headers={"X-API-Key": "test-api-key"},
                timeout=httpx.Timeout(5.0)
            ) as response:
                assert response.status_code == 200

                start_time = asyncio.get_event_loop().time()
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                        if event_type == "heartbeat":
                            heartbeat_received = True
                            break

                    if asyncio.get_event_loop().time() - start_time > 4:
                        break

            assert heartbeat_received

    async def test_sse_filters_by_project_access(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        redis_client = redis.Redis.from_url(
            "redis://localhost:6379/0",
            decode_responses=True
        )

        try:
            async def publish_wrong_project():
                await asyncio.sleep(0.5)
                notification = {
                    "project_id": 999,
                    "level": "error",
                    "message": "Wrong project error"
                }
                await redis_client.publish(
                    "notifications:errors:999",
                    json.dumps(notification)
                )

            async def publish_correct_project():
                await asyncio.sleep(0.7)
                notification = {
                    "project_id": 1,
                    "level": "error",
                    "message": "Correct project error"
                }
                await redis_client.publish(
                    "notifications:errors:1",
                    json.dumps(notification)
                )

            publisher_task1 = asyncio.create_task(publish_wrong_project())
            publisher_task2 = asyncio.create_task(publish_correct_project())

            received_notifications = []

            async with self.client.stream(
                "GET",
                "/api/v1/notifications/stream",
                headers={"X-API-Key": "test-api-key"},
                timeout=httpx.Timeout(3.0)
            ) as response:
                assert response.status_code == 200

                async for line in response.aiter_lines():
                    if line.startswith("event:") and "error_notification" in line:
                        pass
                    elif line.startswith("data:") and len(received_notifications) < 10:
                        data_str = line.split(":", 1)[1].strip()
                        try:
                            data = json.loads(data_str)
                            if "message" in data and "error" in data.get("message", "").lower():
                                received_notifications.append(data)
                        except json.JSONDecodeError:
                            pass

                    if len(received_notifications) >= 1:
                        break

            await publisher_task1
            await publisher_task2

            assert len(received_notifications) >= 1
            assert all(n["project_id"] == 1 for n in received_notifications)

        finally:
            await redis_client.close()

    async def test_sse_multiple_concurrent_connections(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        clients = []
        streams = []

        try:
            for i in range(3):
                client = httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=self.client._transport._app),
                    base_url="http://test"
                )
                clients.append(client)

                stream = client.stream(
                    "GET",
                    "/api/v1/notifications/stream",
                    headers={"X-API-Key": "test-api-key"},
                    timeout=httpx.Timeout(5.0)
                )
                streams.append(stream)

            connection_count = 0
            for stream in streams:
                response = await stream.__aenter__()
                if response.status_code == 200:
                    connection_count += 1

            assert connection_count == 3

        finally:
            for stream in streams:
                try:
                    await stream.__aexit__(None, None, None)
                except Exception:
                    pass
            for client in clients:
                await client.aclose()

    async def test_sse_reconnection_after_disconnect(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        async with self.client.stream(
            "GET",
            "/api/v1/notifications/stream",
            headers={"X-API-Key": "test-api-key"},
            timeout=httpx.Timeout(2.0)
        ) as response1:
            assert response1.status_code == 200

        async with self.client.stream(
            "GET",
            "/api/v1/notifications/stream",
            headers={"X-API-Key": "test-api-key"},
            timeout=httpx.Timeout(2.0)
        ) as response2:
            assert response2.status_code == 200

            received_connected = False
            async for line in response2.aiter_lines():
                if line.startswith("event:") and "connected" in line:
                    received_connected = True
                    break

            assert received_connected

    async def test_sse_handles_invalid_authentication(self):
        response = await self.client.get(
            "/api/v1/notifications/stream",
            headers={"X-API-Key": "invalid-key"}
        )

        assert response.status_code == 401

    async def test_sse_connection_with_session_token(self):
        await self.mock_redis.set(
            "session:test-token",
            json.dumps({
                "account_id": 1,
                "email": "test@example.com"
            })
        )

        mock_auth_stub = self.get_mock_auth_stub()
        mock_auth_stub.GetProjects = AsyncMock(return_value=MagicMock(
            projects=[
                MagicMock(project_id=1, name="Project 1"),
                MagicMock(project_id=2, name="Project 2")
            ]
        ))

        async with self.client.stream(
            "GET",
            "/api/v1/notifications/stream",
            headers={"Authorization": "Bearer test-token"},
            timeout=httpx.Timeout(3.0)
        ) as response:
            assert response.status_code == 200

            event_data = None
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data_str = line.split(":", 1)[1].strip()
                    event_data = json.loads(data_str)
                    break

            assert event_data is not None
            assert "projects" in event_data
            assert 1 in event_data["projects"]
            assert 2 in event_data["projects"]
