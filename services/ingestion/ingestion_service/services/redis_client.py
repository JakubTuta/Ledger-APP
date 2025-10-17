import redis.asyncio as redis

import ingestion_service.config as config

_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            config.settings.REDIS_URL,
            max_connections=config.settings.REDIS_MAX_CONNECTIONS,
            decode_responses=False,
            socket_timeout=config.settings.REDIS_TIMEOUT,
            socket_connect_timeout=config.settings.REDIS_TIMEOUT,
        )
    return _redis_client


async def close_redis():
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
