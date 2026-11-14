import types

import pytest

import ledger_common.redis_client as redis_client


class _FakeRedis:
    def __init__(self):
        self.pinged = False
        self.closed = False

    async def ping(self):
        self.pinged = True

    async def aclose(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_client():
    redis_client.redis_client = None
    yield
    redis_client.redis_client = None


def test_get_redis_before_init_is_an_error():
    with pytest.raises(RuntimeError, match="not initialized"):
        redis_client.get_redis()


async def test_init_builds_a_pooled_client_and_pings(monkeypatch):
    fake = _FakeRedis()
    built = {}

    def from_url(url, **kwargs):
        built.update(url=url, **kwargs)
        return fake

    monkeypatch.setattr(redis_client.redis, "from_url", from_url)

    await redis_client.init_redis(
        types.SimpleNamespace(REDIS_URL="redis://cache:6379/0", REDIS_MAX_CONNECTIONS=7)
    )

    assert redis_client.get_redis() is fake
    assert fake.pinged
    assert built["url"] == "redis://cache:6379/0"
    assert built["max_connections"] == 7


async def test_close_releases_the_client():
    fake = _FakeRedis()
    redis_client.redis_client = fake

    await redis_client.close_redis()

    assert fake.closed
    with pytest.raises(RuntimeError):
        redis_client.get_redis()
