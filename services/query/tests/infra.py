"""Where this suite's disposable Postgres and Redis live.

The suite drops tables and flushes Redis, so addresses come from TEST_*
variables (defaults match the CI service containers), tables live only in the
suite's own test_* database, and Redis is the dedicated TEST_REDIS_DB (15 by
default, never the app's 0) which is flushed only while it is empty or still
carries the marker a previous Ledger test run left in it.
"""

import os

import pytest
import redis.asyncio as redis_async

import query_service.config as config

POSTGRES_HOST = os.getenv("TEST_POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("TEST_LOGS_DB_PORT", "5433")
POSTGRES_USER = os.getenv("TEST_POSTGRES_USER", config.settings.LOGS_DB_USER)
POSTGRES_PASSWORD = os.getenv("TEST_POSTGRES_PASSWORD", config.settings.LOGS_DB_PASSWORD)

REDIS_HOST = os.getenv("TEST_REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("TEST_REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("TEST_REDIS_DB", "15"))
REDIS_PASSWORD = os.getenv("TEST_REDIS_PASSWORD", config.settings.REDIS_PASSWORD or "")

_SUITE_MARKER_KEY = "ledger:test-suite"


def require_test_database_name(name: str) -> str:
    if not name.startswith("test_"):
        raise ValueError(f"Refusing to use database {name!r}: test databases must start 'test_'")
    return name


def redis_url() -> str:
    credentials = f":{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""
    return f"redis://{credentials}{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"


async def reset_redis(redis: redis_async.Redis) -> None:
    """FLUSHDB, but only on a Redis database this suite owns."""
    if await redis.dbsize() and not await redis.exists(_SUITE_MARKER_KEY):
        pytest.exit(
            f"Refusing to flush Redis db {REDIS_DB} at {REDIS_HOST}:{REDIS_PORT}: it holds keys "
            "this test suite did not write. Point TEST_REDIS_HOST/TEST_REDIS_PORT/TEST_REDIS_DB "
            "at a disposable Redis database.",
            returncode=2,
        )
    await redis.flushdb()
    await redis.set(_SUITE_MARKER_KEY, "1")
