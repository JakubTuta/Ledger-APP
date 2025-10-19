import redis.asyncio as redis

import analytics_workers.config as config

redis_client: redis.Redis | None = None


async def init_redis() -> None:
    global redis_client

    settings = config.get_settings()

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


def get_redis() -> redis.Redis:
    if redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return redis_client
