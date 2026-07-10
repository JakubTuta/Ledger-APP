import hashlib
import json
import logging
import typing

from gateway_service import config
from redis import asyncio as aioredis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

_QUOTA_CONSUME_LUA = """
local current = redis.call('INCRBY', KEYS[1], ARGV[1])
if current == tonumber(ARGV[1]) then
    redis.call('EXPIRE', KEYS[1], ARGV[3])
end
if current > tonumber(ARGV[2]) then
    redis.call('DECRBY', KEYS[1], ARGV[1])
    return {0, current - tonumber(ARGV[1])}
end
return {1, current}
"""


class RedisClient:
    def __init__(self, url: str, max_connections: int = 50, decode_responses: bool = False):
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

    async def check_rate_limit(
        self,
        entity_id: int,
        limit_per_minute: int,
        limit_per_hour: int,
        key_prefix: str = "project",
        amount: int = 1,
    ) -> tuple[bool, typing.Dict]:
        import time

        now = int(time.time())
        minute_key = f"ratelimit:{key_prefix}:{entity_id}:min:{now // 60}"
        hour_key = f"ratelimit:{key_prefix}:{entity_id}:hour:{now // 3600}"

        try:
            pipe = self.client.pipeline()  # type: ignore
            pipe.incrby(minute_key, amount)
            pipe.expire(minute_key, 60)
            pipe.incrby(hour_key, amount)
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

    async def get_cached_project_access(
        self, account_id: int, project_id: int
    ) -> typing.Optional[bool]:
        key = f"project_access:{account_id}:{project_id}"
        try:
            val = await self.client.get(key)  # type: ignore
            if val is None:
                return None
            return val == b"1"
        except RedisError as e:
            logger.error(f"Redis GET project_access error: {e}")
            return None

    async def set_cached_project_access(
        self, account_id: int, project_id: int, is_member: bool, ttl: int = 60
    ):
        key = f"project_access:{account_id}:{project_id}"
        try:
            await self.client.setex(key, ttl, b"1" if is_member else b"0")  # type: ignore
        except RedisError as e:
            logger.error(f"Redis SETEX project_access error: {e}")

    async def delete_cached_project_access(self, account_id: int, project_id: int):
        key = f"project_access:{account_id}:{project_id}"
        try:
            await self.client.delete(key)  # type: ignore
        except RedisError as e:
            logger.error(f"Redis DELETE project_access error: {e}")

    # Short-lived (~5 min) mapping from an opaque totp_session_token to the
    # account_id it belongs to, created after password verification when an
    # account has 2FA enabled and consumed by /accounts/2fa/login.

    _TOTP_SESSION_TTL = 300

    def _totp_session_key(self, totp_session_token: str) -> str:
        return f"totp_session:{totp_session_token}"

    async def set_totp_session(
        self, totp_session_token: str, account_id: int, ttl: int = _TOTP_SESSION_TTL
    ):
        key = self._totp_session_key(totp_session_token)
        try:
            await self.client.setex(key, ttl, str(account_id))  # type: ignore
        except RedisError as e:
            logger.error(f"Redis SETEX totp_session error: {e}")

    async def get_totp_session(self, totp_session_token: str) -> typing.Optional[int]:
        key = self._totp_session_key(totp_session_token)
        try:
            val = await self.client.get(key)  # type: ignore
            if val is None:
                return None
            return int(val)
        except (RedisError, ValueError) as e:
            logger.error(f"Redis GET totp_session error: {e}")
            return None

    async def delete_totp_session(self, totp_session_token: str):
        await self.delete(self._totp_session_key(totp_session_token))

    _USAGE_SIGNALS = ("logs", "spans", "metrics")

    def _daily_usage_key(self, project_id: int, signal: str, today: str) -> str:
        return f"usage:{project_id}:{signal}:{today}"

    async def get_daily_usage(self, project_id: int, signal: str = "logs") -> int:
        import datetime

        today = datetime.date.today().strftime("%Y%m%d")
        key = self._daily_usage_key(project_id, signal, today)

        try:
            count = await self.client.get(key)  # type: ignore
            return int(count) if count else 0

        except RedisError as e:
            logger.error(f"Get daily usage error: {e}")
            return 0

    async def get_daily_usage_by_signal(self, project_id: int) -> dict[str, int]:
        """Fetch today's usage for all three signals in a single round trip."""
        import datetime

        today = datetime.date.today().strftime("%Y%m%d")
        keys = [self._daily_usage_key(project_id, signal, today) for signal in self._USAGE_SIGNALS]

        try:
            values = await self.client.mget(keys)  # type: ignore
        except RedisError as e:
            logger.error(f"Get daily usage by signal error: {e}")
            values = [None] * len(self._USAGE_SIGNALS)

        return {
            signal: int(value) if value else 0 for signal, value in zip(self._USAGE_SIGNALS, values)
        }

    async def try_consume_quota(
        self, project_id: int, signal: str, amount: int, quota: int
    ) -> tuple[bool, int]:
        """Atomically reserve `amount` against a signal's daily quota.

        Returns (allowed, usage_after). On denial the reservation is rolled back
        so usage reflects only accepted items, avoiding the increment-after-accept
        race where a burst could overshoot the quota by a full request.
        """
        import datetime

        today = datetime.date.today().strftime("%Y%m%d")
        key = self._daily_usage_key(project_id, signal, today)

        try:
            allowed, usage = await self.client.eval(  # type: ignore
                _QUOTA_CONSUME_LUA, 1, key, amount, quota, 48 * 3600
            )
            return bool(allowed), int(usage)

        except RedisError as e:
            logger.error(f"Quota consume error: {e}")
            return True, 0

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

    async def batch_get(self, keys: typing.List[str]) -> typing.List[typing.Optional[bytes]]:
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
