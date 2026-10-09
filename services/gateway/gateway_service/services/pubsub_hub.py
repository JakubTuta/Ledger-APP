import asyncio
import collections
import contextlib
import datetime
import json
import logging
import typing

from redis import asyncio as aioredis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# Per-stream buffer. A browser tab that stops reading must neither grow gateway
# memory without bound nor slow delivery to every other stream, so overflow is
# dropped (and counted) rather than awaited.
_SUBSCRIBER_QUEUE_SIZE = 1000
_READ_TIMEOUT_SECONDS = 1.0
_RETRY_DELAY_SECONDS = 1.0


class PubSubHub:
    """One Redis pub/sub connection per gateway worker, shared by every SSE stream.

    Each live-tail / notification stream used to open its own Redis connection,
    so a few dozen open dashboard tabs could exhaust Redis' client limit - and
    with it rate limiting, the API key cache and quota accounting, which share
    that Redis. Here a channel is subscribed on Redis while at least one local
    stream wants it, and every message is fanned out to the local queues.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.Redis.from_url(redis_url, decode_responses=True)
        self._pubsub = self._redis.pubsub()
        self._queues: dict[str, set[asyncio.Queue]] = collections.defaultdict(set)
        self._lock = asyncio.Lock()
        self._reader: asyncio.Task | None = None
        self.dropped_messages = 0

    @contextlib.asynccontextmanager
    async def subscribe(
        self, channels: typing.Iterable[str]
    ) -> typing.AsyncIterator[asyncio.Queue]:
        """Yield a queue receiving every message published on `channels`."""
        channels = list(dict.fromkeys(channels))
        queue: asyncio.Queue = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_SIZE)
        if not channels:
            yield queue
            return
        await self._add(queue, channels)
        try:
            yield queue
        finally:
            await self._remove(queue, channels)

    async def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
        await self._pubsub.aclose()
        await self._redis.aclose()

    def stats(self) -> dict[str, int]:
        return {
            "channels": len(self._queues),
            "streams": len({id(q) for queues in self._queues.values() for q in queues}),
            "dropped_messages": self.dropped_messages,
        }

    async def _add(self, queue: asyncio.Queue, channels: list[str]) -> None:
        async with self._lock:
            new_channels = [channel for channel in channels if not self._queues.get(channel)]
            if new_channels:
                await self._pubsub.subscribe(*new_channels)
            for channel in channels:
                self._queues[channel].add(queue)
            if self._reader is None or self._reader.done():
                self._reader = asyncio.create_task(self._read_loop())

    async def _remove(self, queue: asyncio.Queue, channels: list[str]) -> None:
        async with self._lock:
            idle_channels = []
            for channel in channels:
                subscribers = self._queues.get(channel)
                if subscribers is None:
                    continue
                subscribers.discard(queue)
                if not subscribers:
                    del self._queues[channel]
                    idle_channels.append(channel)
            if idle_channels:
                try:
                    await self._pubsub.unsubscribe(*idle_channels)
                except RedisError as e:
                    # A dropped connection resubscribes from pubsub.channels on
                    # reconnect; leftover subscriptions only cost an ignored message.
                    logger.warning(f"Pub/sub unsubscribe failed: {e}")

    async def _read_loop(self) -> None:
        while True:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=_READ_TIMEOUT_SECONDS
                )
            except (RedisError, OSError) as e:
                logger.warning(f"Pub/sub read failed, retrying: {e}")
                await asyncio.sleep(_RETRY_DELAY_SECONDS)
                continue
            if message is not None and message.get("type") == "message":
                self._dispatch(message["channel"], message["data"])

    def _dispatch(self, channel: str, data: str) -> None:
        for queue in tuple(self._queues.get(channel, ())):
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                self.dropped_messages += 1


async def channel_events(
    hub: PubSubHub,
    channels: list[str],
    event_name: str,
    connected_payload: dict,
    heartbeat_seconds: float,
) -> typing.AsyncIterator[dict]:
    """SSE events for `channels`: `connected`, then every message, with heartbeats.

    Payloads are forwarded as published - the publishers (ingestion worker,
    analytics) already write JSON.
    """
    async with hub.subscribe(channels) as queue:
        yield {"event": "connected", "data": json.dumps(connected_payload)}
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except TimeoutError:
                timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
                yield {"event": "heartbeat", "data": json.dumps({"timestamp": timestamp})}
                continue
            yield {"event": event_name, "data": data}
