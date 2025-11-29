import asyncio
import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ingestion_service import schemas
from ingestion_service.notifications import publisher as notif_publisher

from .test_base import BaseIngestionTest


@pytest.mark.asyncio
class TestNotificationPublisher(BaseIngestionTest):

    async def test_should_notify_error_level(self):
        redis_mock = AsyncMock()
        pub = notif_publisher.NotificationPublisher(redis_mock, enabled=True)

        assert pub.should_notify("error", "console", True, True) is True
        assert pub.should_notify("error", "logger", True, True) is True

    async def test_should_notify_critical_level(self):
        redis_mock = AsyncMock()
        pub = notif_publisher.NotificationPublisher(redis_mock, enabled=True)

        assert pub.should_notify("critical", "console", True, True) is True
        assert pub.should_notify("critical", "logger", True, True) is True

    async def test_should_notify_exception_type(self):
        redis_mock = AsyncMock()
        pub = notif_publisher.NotificationPublisher(redis_mock, enabled=True)

        assert pub.should_notify("info", "exception", True, True) is True
        assert pub.should_notify("warning", "exception", True, True) is True

    async def test_should_not_notify_info_level(self):
        redis_mock = AsyncMock()
        pub = notif_publisher.NotificationPublisher(redis_mock, enabled=True)

        assert pub.should_notify("info", "console", True, True) is False
        assert pub.should_notify("debug", "logger", True, True) is False
        assert pub.should_notify("warning", "console", True, True) is False

    async def test_should_not_notify_when_disabled(self):
        redis_mock = AsyncMock()
        pub = notif_publisher.NotificationPublisher(redis_mock, enabled=False)

        assert pub.should_notify("error", "console", True, True) is False
        assert pub.should_notify("critical", "exception", True, True) is False

    async def test_publish_error_notification_success(self):
        redis_mock = AsyncMock()
        redis_mock.publish = AsyncMock(return_value=1)

        pub = notif_publisher.NotificationPublisher(redis_mock, enabled=True)

        notification = notif_publisher.ErrorNotification(
            project_id=123,
            level="error",
            log_type="exception",
            message="Database connection failed",
            error_type="DatabaseError",
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            error_fingerprint="abc123",
            attributes={}
        )

        await pub.publish_error_notification(123, notification)

        redis_mock.publish.assert_called_once()
        call_args = redis_mock.publish.call_args
        assert call_args[0][0] == "notifications:errors:123"

        published_data = json.loads(call_args[0][1])
        assert published_data["project_id"] == 123
        assert published_data["level"] == "error"
        assert published_data["message"] == "Database connection failed"

    async def test_publish_notification_to_correct_channel(self):
        redis_mock = AsyncMock()
        redis_mock.publish = AsyncMock(return_value=2)

        pub = notif_publisher.NotificationPublisher(redis_mock, enabled=True)

        notification = notif_publisher.ErrorNotification(
            project_id=456,
            level="critical",
            log_type="exception",
            message="System failure",
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            attributes={}
        )

        await pub.publish_error_notification(456, notification)

        call_args = redis_mock.publish.call_args
        assert call_args[0][0] == "notifications:errors:456"

    async def test_publish_notification_disabled(self):
        redis_mock = AsyncMock()
        redis_mock.publish = AsyncMock()

        pub = notif_publisher.NotificationPublisher(redis_mock, enabled=False)

        notification = notif_publisher.ErrorNotification(
            project_id=123,
            level="error",
            log_type="exception",
            message="Test error",
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            attributes={}
        )

        await pub.publish_error_notification(123, notification)

        redis_mock.publish.assert_not_called()

    async def test_publish_notification_handles_error_gracefully(self):
        redis_mock = AsyncMock()
        redis_mock.publish = AsyncMock(side_effect=Exception("Redis connection failed"))

        pub = notif_publisher.NotificationPublisher(redis_mock, enabled=True)

        notification = notif_publisher.ErrorNotification(
            project_id=123,
            level="error",
            log_type="exception",
            message="Test error",
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            attributes={}
        )

        await pub.publish_error_notification(123, notification)

    async def test_notification_message_truncation(self):
        redis_mock = AsyncMock()
        redis_mock.publish = AsyncMock(return_value=1)

        pub = notif_publisher.NotificationPublisher(redis_mock, enabled=True)

        long_message = "X" * 1000
        notification = notif_publisher.ErrorNotification(
            project_id=123,
            level="error",
            log_type="exception",
            message=long_message,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            attributes={}
        )

        await pub.publish_error_notification(123, notification)

        call_args = redis_mock.publish.call_args
        published_data = json.loads(call_args[0][1])
        assert len(published_data["message"]) == 1000

    async def test_notification_with_optional_fields(self):
        redis_mock = AsyncMock()
        redis_mock.publish = AsyncMock(return_value=1)

        pub = notif_publisher.NotificationPublisher(redis_mock, enabled=True)

        notification = notif_publisher.ErrorNotification(
            project_id=123,
            level="error",
            log_type="exception",
            message="Error with metadata",
            error_type="CustomError",
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            error_fingerprint="fingerprint123",
            sdk_version="1.0.0",
            platform="python",
            attributes={"user_id": 456, "trace_id": "xyz"}
        )

        await pub.publish_error_notification(123, notification)

        call_args = redis_mock.publish.call_args
        published_data = json.loads(call_args[0][1])
        assert published_data["error_type"] == "CustomError"
        assert published_data["sdk_version"] == "1.0.0"
        assert published_data["platform"] == "python"
        assert published_data["attributes"]["user_id"] == 456

    async def test_real_redis_publish_subscribe(self):
        pub = notif_publisher.NotificationPublisher(self.redis, enabled=True)

        pubsub = self.redis.pubsub()
        await pubsub.subscribe("notifications:errors:999")

        notification = notif_publisher.ErrorNotification(
            project_id=999,
            level="error",
            log_type="exception",
            message="Real Redis test",
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            attributes={}
        )

        await pub.publish_error_notification(999, notification)

        await asyncio.sleep(0.1)

        message = None
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                message = msg
                break

        assert message is not None
        data = json.loads(message["data"])
        assert data["project_id"] == 999
        assert data["message"] == "Real Redis test"

        await pubsub.unsubscribe()
        await pubsub.close()
