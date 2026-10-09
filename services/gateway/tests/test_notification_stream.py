import asyncio
import json

import pytest
from gateway_service.services import pubsub_hub


class _FakeRedisPubSub:
    """Records SUBSCRIBE/UNSUBSCRIBE and serves queued messages to get_message()."""

    def __init__(self):
        self.subscribe_calls: list[tuple[str, ...]] = []
        self.unsubscribe_calls: list[tuple[str, ...]] = []
        self.inbox: asyncio.Queue = asyncio.Queue()

    async def subscribe(self, *channels):
        self.subscribe_calls.append(channels)

    async def unsubscribe(self, *channels):
        self.unsubscribe_calls.append(channels)

    async def get_message(self, ignore_subscribe_messages=False, timeout=0.0):
        try:
            return await asyncio.wait_for(self.inbox.get(), timeout=timeout)
        except TimeoutError:
            return None

    async def aclose(self):
        pass

    def deliver(self, channel: str, data: str) -> None:
        self.inbox.put_nowait({"type": "message", "channel": channel, "data": data})


async def _hub_with_fake_pubsub() -> tuple[pubsub_hub.PubSubHub, _FakeRedisPubSub]:
    hub = pubsub_hub.PubSubHub("redis://unused:6379/0")
    fake = _FakeRedisPubSub()
    hub._pubsub = fake
    return hub, fake


@pytest.mark.asyncio
async def test_streams_on_one_channel_share_one_redis_subscription():
    hub, fake = await _hub_with_fake_pubsub()

    async with hub.subscribe(["logs:tail:1"]) as first, hub.subscribe(["logs:tail:1"]) as second:
        fake.deliver("logs:tail:1", '{"n": 1}')
        assert await asyncio.wait_for(first.get(), 1) == '{"n": 1}'
        assert await asyncio.wait_for(second.get(), 1) == '{"n": 1}'
        assert fake.subscribe_calls == [("logs:tail:1",)]
        assert fake.unsubscribe_calls == []

    assert fake.unsubscribe_calls == [("logs:tail:1",)]
    await hub.close()


@pytest.mark.asyncio
async def test_message_reaches_only_streams_of_its_channel():
    hub, fake = await _hub_with_fake_pubsub()

    async with hub.subscribe(["notifications:errors:1"]) as mine:
        async with hub.subscribe(["notifications:errors:2"]) as other:
            fake.deliver("notifications:errors:1", "for-1")
            assert await asyncio.wait_for(mine.get(), 1) == "for-1"
            await asyncio.sleep(0.05)
            assert other.empty()

    await hub.close()


@pytest.mark.asyncio
async def test_stalled_stream_drops_overflow_instead_of_blocking(monkeypatch):
    monkeypatch.setattr(pubsub_hub, "_SUBSCRIBER_QUEUE_SIZE", 2)
    hub, fake = await _hub_with_fake_pubsub()

    async with hub.subscribe(["c"]) as stalled:
        for n in range(5):
            fake.deliver("c", str(n))
        await asyncio.sleep(0.1)
        assert stalled.qsize() == 2
        assert hub.dropped_messages == 3

    await hub.close()


@pytest.mark.asyncio
async def test_channel_events_emits_connected_messages_and_heartbeats():
    hub, fake = await _hub_with_fake_pubsub()
    events = pubsub_hub.channel_events(hub, ["c"], "log", {"project_id": 1}, heartbeat_seconds=0.2)

    connected = await events.__anext__()
    assert connected == {"event": "connected", "data": json.dumps({"project_id": 1})}

    fake.deliver("c", '{"message": "hi"}')
    assert await events.__anext__() == {"event": "log", "data": '{"message": "hi"}'}

    heartbeat = await events.__anext__()
    assert heartbeat["event"] == "heartbeat"

    await events.aclose()
    assert fake.unsubscribe_calls == [("c",)]
    await hub.close()
