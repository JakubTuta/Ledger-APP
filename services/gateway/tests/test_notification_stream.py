import json

import pytest
from gateway_service.routes import notifications


class _FakePubSub:
    def __init__(self, payloads: list[dict]):
        self._messages = [{"type": "message", "data": json.dumps(p)} for p in payloads]

    async def listen(self):
        for message in self._messages:
            yield message


async def _drain(stream: notifications.NotificationStream) -> list[dict]:
    return [json.loads(event["data"]) async for event in stream.listen()]


@pytest.mark.asyncio
async def test_stream_forwards_every_notification_for_the_subscribed_projects():
    published = [
        {"project_id": 1, "level": "error", "log_type": "exception", "message": "boom"},
        {"project_id": 1, "level": "warning", "log_type": "alert", "message": "Alert firing: p95"},
        {"project_id": 1, "level": "critical", "log_type": "alert", "message": "Alert firing: 5xx"},
    ]
    stream = notifications.NotificationStream("redis://unused", {1})
    stream.pubsub = _FakePubSub(published)

    assert await _drain(stream) == published
