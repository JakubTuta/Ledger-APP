"""Process-wide async Redis client for the services that open one connection pool at startup.

Call `init_redis(settings)` once from the service's main; everything else uses `get_redis()`.
`settings` needs REDIS_URL and REDIS_MAX_CONNECTIONS (see ledger_common.settings.RedisSettings).
"""

import typing

import redis.asyncio as redis

redis_client: redis.Redis | None = None


class RedisConfig(typing.Protocol):
    REDIS_URL: str
    REDIS_MAX_CONNECTIONS: int


async def init_redis(settings: RedisConfig) -> None:
    global redis_client

    redis_client = redis.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        decode_responses=True,
        encoding="utf-8",
    )

    await redis_client.ping()


async def close_redis() -> None:
    global redis_client

    if redis_client:
        await redis_client.aclose()
        redis_client = None


def get_redis() -> redis.Redis:
    if redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return redis_client
