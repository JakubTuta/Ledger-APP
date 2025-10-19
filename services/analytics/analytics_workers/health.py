import asyncio
import datetime
import json
import pathlib

import sqlalchemy as sa

import analytics_workers.database as database
import analytics_workers.redis_client as redis_client
import analytics_workers.utils.logging as logging

logger = logging.get_logger("health")

HEALTH_FILE_PATH = pathlib.Path("/tmp/analytics_health.json")


async def update_health_status() -> dict:
    health_status = {
        "status": "healthy",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "checks": {},
    }

    try:
        redis = redis_client.get_redis()
        await redis.ping()
        health_status["checks"]["redis"] = "healthy"
    except Exception as e:
        health_status["checks"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    try:
        async with database.get_logs_session() as session:
            await session.execute(sa.text("SELECT 1"))
        health_status["checks"]["logs_db"] = "healthy"
    except Exception as e:
        health_status["checks"]["logs_db"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    try:
        async with database.get_auth_session() as session:
            await session.execute(sa.text("SELECT 1"))
        health_status["checks"]["auth_db"] = "healthy"
    except Exception as e:
        health_status["checks"]["auth_db"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    return health_status


async def write_health_file() -> None:
    try:
        health_status = await update_health_status()
        HEALTH_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        HEALTH_FILE_PATH.write_text(json.dumps(health_status, indent=2))
    except Exception as e:
        logger.error(f"Failed to write health file: {e}")


async def health_check_loop() -> None:
    while True:
        await write_health_file()
        await asyncio.sleep(30)
