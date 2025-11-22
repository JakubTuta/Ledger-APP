import asyncio
import hashlib
import json
import logging
import random
import typing

from gateway_service import config
from redis import asyncio as aioredis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class RedisClient:
    def __init__(
        self, url: str, max_connections: int = 50, decode_responses: bool = False
    ):
        self.url = url
        self.max_connections = max_connections
        self.decode_responses = decode_responses
        self.client: typing.Optional[aioredis.Redis] = None
        self._pipeline_size = 100

    async def connect(self):
        try:
            self.client = await aioredis.from_url(
                self.url,
                encoding="utf-8",
                decode_responses=self.decode_responses,
                max_connections=self.max_connections,
                socket_timeout=config.settings.REDIS_TIMEOUT,
                socket_connect_timeout=config.settings.REDIS_TIMEOUT,
                socket_keepalive=True,
                retry_on_timeout=True,
                health_check_interval=30,
            )

            await self.client.ping()

        except RedisError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def close(self):
        if self.client:
            await self.client.close()

    async def ping(self) -> bool:
        try:
            return await self.client.ping()  # type: ignore

        except RedisError:
            return False

    # ==================== CACHING OPERATIONS ====================

    async def get_cached_api_key(self, api_key: str) -> typing.Optional[typing.Dict]:
        cache_key = self._api_key_cache_key(api_key)

        try:
            data = await self.client.get(cache_key)  # type: ignore
            if data:
                return json.loads(data)
            return None

        except RedisError as e:
            logger.error(f"Redis GET error: {e}")
            return None

    async def set_cached_api_key(
        self, api_key: str, data: typing.Dict, ttl: typing.Optional[int] = None
    ):
        cache_key = self._api_key_cache_key(api_key)

        if ttl is None:
            ttl = config.settings.API_KEY_CACHE_TTL

        try:
            value = json.dumps(data)

            await self.client.setex(cache_key, ttl, value)  # type: ignore

        except RedisError as e:
            logger.error(f"Redis SETEX error: {e}")

    async def get_stale_cache(self, api_key: str) -> typing.Optional[typing.Dict]:
        return await self.get_cached_api_key(api_key)

    async def refresh_cache_probabilistic(
        self, api_key: str, refresh_callback
    ) -> typing.Optional[typing.Dict]:
        cache_key = self._api_key_cache_key(api_key)

        try:
            pipe = self.client.pipeline()  # type: ignore
            pipe.get(cache_key)
            pipe.ttl(cache_key)
            data_bytes, ttl_remaining = await pipe.execute()

            if data_bytes is None:
                return None

            data = json.loads(data_bytes)

            if ttl_remaining > 0 and ttl_remaining < 60 and random.random() < 0.1:
                asyncio.create_task(refresh_callback(api_key))

            return data

        except RedisError as e:
            logger.error(f"Redis error in probabilistic refresh: {e}")
            return None

    # ==================== RATE LIMITING OPERATIONS ====================

    async def check_rate_limit(
        self, project_id: int, limit_per_minute: int, limit_per_hour: int
    ) -> tuple[bool, typing.Dict]:
        import time

        now = int(time.time())
        minute_key = f"ratelimit:{project_id}:min:{now // 60}"
        hour_key = f"ratelimit:{project_id}:hour:{now // 3600}"

        try:
            pipe = self.client.pipeline()  # type: ignore
            pipe.incr(minute_key)
            pipe.expire(minute_key, 60)
            pipe.incr(hour_key)
            pipe.expire(hour_key, 3600)

            minute_count, _, hour_count, _ = await pipe.execute()

            allowed = minute_count <= limit_per_minute and hour_count <= limit_per_hour

            metadata = {
                "minute_count": minute_count,
                "minute_limit": limit_per_minute,
                "hour_count": hour_count,
                "hour_limit": limit_per_hour,
                "retry_after": 60 if not allowed else None,
            }

            return allowed, metadata

        except RedisError as e:
            logger.error(f"Rate limit check error: {e}")
            return True, {"error": str(e)}

    async def get_daily_usage(self, project_id: int) -> int:
        import datetime

        today = datetime.date.today().strftime("%Y%m%d")
        key = f"usage:{project_id}:{today}"

        try:
            count = await self.client.get(key)  # type: ignore
            return int(count) if count else 0

        except RedisError as e:
            logger.error(f"Get daily usage error: {e}")
            return 0

    async def increment_daily_usage(self, project_id: int, amount: int = 1):
        import datetime

        today = datetime.date.today().strftime("%Y%m%d")
        key = f"usage:{project_id}:{today}"

        try:
            pipe = self.client.pipeline()  # type: ignore
            pipe.incrby(key, amount)
            pipe.expire(key, 48 * 3600)
            await pipe.execute()

        except RedisError as e:
            logger.error(f"Increment usage error: {e}")

    # ==================== CIRCUIT BREAKER STATE ====================

    async def get_circuit_state(self, service_name: str) -> str:
        key = f"circuit:{service_name}:state"

        try:
            state = await self.client.get(key)  # type: ignore
            return state.decode() if state else "CLOSED"

        except RedisError:
            return "CLOSED"

    async def set_circuit_state(self, service_name: str, state: str, ttl: int = 300):
        key = f"circuit:{service_name}:state"

        try:
            await self.client.setex(key, ttl, state)  # type: ignore

        except RedisError as e:
            logger.error(f"Set circuit state error: {e}")

    async def increment_circuit_failures(self, service_name: str) -> int:
        key = f"circuit:{service_name}:failures"

        try:
            pipe = self.client.pipeline()  # type: ignore
            pipe.incr(key)
            pipe.expire(key, 60)
            count, _ = await pipe.execute()
            return count

        except RedisError as e:
            logger.error(f"Increment failures error: {e}")
            return 0

    async def reset_circuit_failures(self, service_name: str):
        key = f"circuit:{service_name}:failures"

        try:
            await self.client.delete(key)  # type: ignore

        except RedisError as e:
            logger.error(f"Reset failures error: {e}")

    # ==================== BATCH OPERATIONS ====================

    async def batch_get(
        self, keys: typing.List[str]
    ) -> typing.List[typing.Optional[bytes]]:
        if not keys:
            return []

        try:
            return await self.client.mget(keys)  # type: ignore

        except RedisError as e:
            logger.error(f"Batch GET error: {e}")
            return [None] * len(keys)

    async def batch_set(
        self, mapping: typing.Dict[str, typing.Any], ttl: typing.Optional[int] = None
    ):
        if not mapping:
            return

        try:
            pipe = self.client.pipeline()  # type: ignore

            for key, value in mapping.items():
                serialized = json.dumps(value) if isinstance(value, dict) else value
                if ttl:
                    pipe.setex(key, ttl, serialized)
                else:
                    pipe.set(key, serialized)

            await pipe.execute()

        except RedisError as e:
            logger.error(f"Batch SET error: {e}")

    # ==================== HELPER METHODS ====================

    def _api_key_cache_key(self, api_key: str) -> str:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        return f"api_key:{key_hash}"

    async def delete(self, key: str):
        try:
            await self.client.delete(key)  # type: ignore

        except RedisError as e:
            logger.error(f"Delete error: {e}")

    async def exists(self, key: str) -> bool:
        try:
            return await self.client.exists(key) > 0  # type: ignore

        except RedisError as e:
            logger.error(f"Exists error: {e}")
            return False

    async def ttl(self, key: str) -> int:
        try:
            return await self.client.ttl(key)  # type: ignore

        except RedisError as e:
            logger.error(f"TTL error: {e}")
            return -1

    async def clear_pattern(self, pattern: str):
        try:
            cursor = 0
            while True:
                cursor, keys = await self.client.scan(cursor, match=pattern, count=100)  # type: ignore

                if keys:
                    await self.client.delete(*keys)  # type: ignore

                if cursor == 0:
                    break

        except RedisError as e:
            logger.error(f"Clear pattern error: {e}")

    # ==================== STATISTICS ====================

    async def get_stats(self) -> typing.Dict[str, typing.Any]:
        try:
            info = await self.client.info()  # type: ignore

            return {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory_human", "0"),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(info),
            }

        except RedisError as e:
            logger.error(f"Get stats error: {e}")
            return {}

    def _calculate_hit_rate(self, info: typing.Dict[str, typing.Any]) -> float:
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses

        if total == 0:
            return 0.0

        return round((hits / total) * 100, 2)
