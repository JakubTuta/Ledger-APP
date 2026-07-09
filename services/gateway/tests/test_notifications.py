import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as redis

import gateway_service.main as main
import gateway_service.proto.auth_pb2 as auth_pb2

from .sse_client import ASGISSEStream, build_http_scope
from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestNotificationsSSE(BaseGatewayTest):
    async def test_sse_requires_authentication(self):
        response = await self.client.get("/api/v1/notifications/stream")

        assert response.status_code == 401

    async def test_sse_connection_with_api_key(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        scope = build_http_scope(
            "GET",
            "/api/v1/notifications/stream",
            headers={"X-API-Key": "test-api-key"},
        )
        async with ASGISSEStream(main.app, scope) as stream:
            assert stream.status_code == 200
            headers = dict(stream.headers)
            assert headers[b"content-type"] == b"text/event-stream; charset=utf-8"

            event = await stream.next_event()
            assert event["event"] == "connected"

    async def test_sse_connected_event_contains_project_list(self):
        await self.set_api_key_cache("test-api-key", project_id=123, account_id=1)

        scope = build_http_scope(
            "GET",
            "/api/v1/notifications/stream",
            headers={"X-API-Key": "test-api-key"},
        )
        async with ASGISSEStream(main.app, scope) as stream:
            assert stream.status_code == 200

            event = await stream.next_event()
            event_data = json.loads(event["data"])

            assert "projects" in event_data
            assert "timestamp" in event_data
            assert 123 in event_data["projects"]

    async def test_sse_notifications_disabled_returns_503(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        with patch("gateway_service.config.settings.NOTIFICATIONS_ENABLED", False):
            response = await self.client.get(
                "/api/v1/notifications/stream", headers={"X-API-Key": "test-api-key"}
            )

            assert response.status_code == 503
            assert "disabled" in response.json()["detail"].lower()

    @pytest.mark.slow
    async def test_sse_receives_error_notification(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        redis_client = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)

        try:

            async def publish_notification():
                await asyncio.sleep(0.5)
                notification = {
                    "project_id": 1,
                    "level": "error",
                    "log_type": "exception",
                    "message": "Test error notification",
                    "error_type": "TestError",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
                await redis_client.publish("notifications:errors:1", json.dumps(notification))

            publisher_task = asyncio.create_task(publish_notification())

            scope = build_http_scope(
                "GET",
                "/api/v1/notifications/stream",
                headers={"X-API-Key": "test-api-key"},
            )
            async with ASGISSEStream(main.app, scope, timeout=5.0) as stream:
                assert stream.status_code == 200

                event = await stream.next_event()
                assert event["event"] == "connected"

                error_event = await stream.next_event()
                assert error_event["event"] == "error_notification"
                error_data = json.loads(error_event["data"])

            await publisher_task

            assert error_data["level"] == "error"
            assert error_data["message"] == "Test error notification"

        finally:
            await redis_client.close()

    @pytest.mark.slow
    async def test_sse_heartbeat_events(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        # NOTIFICATIONS_HEARTBEAT_INTERVAL is a ClassVar constant now, not a
        # pydantic field, so it must be patched on the class rather than the
        # settings instance.
        with patch("gateway_service.config.Settings.NOTIFICATIONS_HEARTBEAT_INTERVAL", 1):
            scope = build_http_scope(
                "GET",
                "/api/v1/notifications/stream",
                headers={"X-API-Key": "test-api-key"},
            )
            async with ASGISSEStream(main.app, scope, timeout=5.0) as stream:
                assert stream.status_code == 200

                heartbeat_received = False
                for _ in range(5):
                    event = await stream.next_event()
                    if event["event"] == "heartbeat":
                        heartbeat_received = True
                        break

            assert heartbeat_received

    async def test_sse_filters_by_project_access(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        redis_client = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)

        try:

            async def publish_wrong_project():
                await asyncio.sleep(0.3)
                notification = {
                    "project_id": 999,
                    "level": "error",
                    "message": "Wrong project error",
                }
                await redis_client.publish("notifications:errors:999", json.dumps(notification))

            async def publish_correct_project():
                await asyncio.sleep(0.5)
                notification = {
                    "project_id": 1,
                    "level": "error",
                    "message": "Correct project error",
                }
                await redis_client.publish("notifications:errors:1", json.dumps(notification))

            publisher_task1 = asyncio.create_task(publish_wrong_project())
            publisher_task2 = asyncio.create_task(publish_correct_project())

            scope = build_http_scope(
                "GET",
                "/api/v1/notifications/stream",
                headers={"X-API-Key": "test-api-key"},
            )
            received_notifications = []
            async with ASGISSEStream(main.app, scope, timeout=5.0) as stream:
                assert stream.status_code == 200

                event = await stream.next_event()
                assert event["event"] == "connected"

                error_event = await stream.next_event()
                assert error_event["event"] == "error_notification"
                received_notifications.append(json.loads(error_event["data"]))

            await publisher_task1
            await publisher_task2

            assert len(received_notifications) >= 1
            assert all(n["project_id"] == 1 for n in received_notifications)

        finally:
            await redis_client.close()

    async def test_sse_multiple_concurrent_connections(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        streams = []
        try:
            for _ in range(3):
                scope = build_http_scope(
                    "GET",
                    "/api/v1/notifications/stream",
                    headers={"X-API-Key": "test-api-key"},
                )
                stream = ASGISSEStream(main.app, scope)
                await stream.__aenter__()
                streams.append(stream)

            connection_count = sum(1 for s in streams if s.status_code == 200)

            assert connection_count == 3

        finally:
            for stream in streams:
                await stream.aclose()

    async def test_sse_reconnection_after_disconnect(self):
        await self.set_api_key_cache("test-api-key", project_id=1, account_id=1)

        scope1 = build_http_scope(
            "GET",
            "/api/v1/notifications/stream",
            headers={"X-API-Key": "test-api-key"},
        )
        async with ASGISSEStream(main.app, scope1) as stream1:
            assert stream1.status_code == 200

        scope2 = build_http_scope(
            "GET",
            "/api/v1/notifications/stream",
            headers={"X-API-Key": "test-api-key"},
        )
        async with ASGISSEStream(main.app, scope2) as stream2:
            assert stream2.status_code == 200

            event = await stream2.next_event()
            assert event["event"] == "connected"

    async def test_sse_handles_invalid_authentication(self):
        mock_auth_stub = self.get_mock_auth_stub()
        mock_auth_stub.validate_api_key_response = auth_pb2.ValidateApiKeyResponse(
            valid=False, error_message="Invalid or expired API key"
        )

        response = await self.client.get(
            "/api/v1/notifications/stream", headers={"X-API-Key": "invalid-key"}
        )

        assert response.status_code == 401

    async def test_sse_connection_with_session_token(self):
        mock_auth_stub = self.get_mock_auth_stub()
        mock_auth_stub.GetProjects = AsyncMock(
            return_value=MagicMock(
                projects=[
                    MagicMock(project_id=1, name="Project 1"),
                    MagicMock(project_id=2, name="Project 2"),
                ]
            )
        )

        session_token = self.make_session_token(account_id=1, email="test@example.com")
        scope = build_http_scope(
            "GET",
            "/api/v1/notifications/stream",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        async with ASGISSEStream(main.app, scope, timeout=5.0) as stream:
            assert stream.status_code == 200

            event = await stream.next_event()
            event_data = json.loads(event["data"])

            assert "projects" in event_data
            assert 1 in event_data["projects"]
            assert 2 in event_data["projects"]
