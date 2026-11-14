import json

import fastapi
import grpc
import pytest

import gateway_service.config as config
import gateway_service.middleware.auth as auth_middleware
import gateway_service.routes.otlp_routes as otlp_routes
import gateway_service.services.redis_client as redis_client_module

_AUTH_DATA = {
    "project_id": 7,
    "account_id": 3,
    "rate_limit_per_minute": 100,
    "rate_limit_per_hour": 1000,
    "logs_daily_quota": 10,
    "spans_daily_quota": 10,
    "metrics_daily_quota": 10,
}


class _FakeRedis:
    """Stores values with their TTL so a test can age an entry without sleeping."""

    def __init__(self):
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def setex(self, key, ttl, value):
        self.values[key] = value
        self.ttls[key] = ttl

    async def get(self, key):
        return self.values.get(key)

    def age(self, key, seconds):
        entry = json.loads(self.values[key])
        entry["_fresh_until"] -= seconds
        self.values[key] = json.dumps(entry)


def _client(fake: _FakeRedis) -> redis_client_module.RedisClient:
    client = redis_client_module.RedisClient("redis://unused")
    client.client = fake
    return client


class _RpcError(grpc.RpcError):
    def __init__(self, code):
        self._code = code

    def code(self):
        return self._code

    def details(self):
        return "boom"


class _FailingAuthStub:
    def __init__(self, code):
        self._code = code

    async def ValidateApiKey(self, request, timeout=None):
        raise _RpcError(self._code)


class _FailingGrpcPool:
    def __init__(self, code):
        self._code = code

    def get_stub(self, name, stub_cls):
        return _FailingAuthStub(self._code)


@pytest.mark.asyncio
class TestApiKeyCacheFreshness:
    async def test_entry_within_fresh_window_is_served(self):
        client = _client(_FakeRedis())
        await client.set_cached_api_key("k", dict(_AUTH_DATA))

        assert await client.get_cached_api_key("k") == _AUTH_DATA

    async def test_entry_past_fresh_window_is_a_miss_but_still_served_stale(self):
        fake = _FakeRedis()
        client = _client(fake)
        await client.set_cached_api_key("k", dict(_AUTH_DATA))
        fake.age(client._api_key_cache_key("k"), config.settings.API_KEY_CACHE_TTL + 1)

        assert await client.get_cached_api_key("k") is None
        assert await client.get_stale_cache("k") == _AUTH_DATA

    async def test_positive_entry_outlives_its_fresh_window(self):
        fake = _FakeRedis()
        client = _client(fake)
        await client.set_cached_api_key("k", dict(_AUTH_DATA))

        assert fake.ttls[client._api_key_cache_key("k")] == config.settings.EMERGENCY_CACHE_TTL

    async def test_negative_entry_expires_with_its_window_and_is_never_stale(self):
        fake = _FakeRedis()
        client = _client(fake)
        await client.set_cached_api_key("k", {"__invalid__": True}, ttl=30)

        assert fake.ttls[client._api_key_cache_key("k")] == 30
        assert (await client.get_cached_api_key("k"))["__invalid__"] is True
        assert await client.get_stale_cache("k") is None

    async def test_entry_without_freshness_marker_is_treated_as_fresh(self):
        fake = _FakeRedis()
        client = _client(fake)
        fake.values[client._api_key_cache_key("k")] = json.dumps(_AUTH_DATA)

        assert await client.get_cached_api_key("k") == _AUTH_DATA

    async def test_missing_entry_is_a_miss_in_both_reads(self):
        client = _client(_FakeRedis())

        assert await client.get_cached_api_key("nope") is None
        assert await client.get_stale_cache("nope") is None

    async def test_fresh_until_is_never_leaked_to_the_caller(self):
        client = _client(_FakeRedis())
        await client.set_cached_api_key("k", dict(_AUTH_DATA))

        assert "_fresh_until" not in await client.get_cached_api_key("k")
        assert "_fresh_until" not in await client.get_stale_cache("k")


@pytest.mark.asyncio
class TestStaleFallbackWhenAuthServiceIsDown:
    @pytest.mark.parametrize(
        "code", [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED]
    )
    async def test_expired_entry_is_served_stale(self, code):
        fake = _FakeRedis()
        client = _client(fake)
        await client.set_cached_api_key("k", dict(_AUTH_DATA))
        fake.age(client._api_key_cache_key("k"), config.settings.API_KEY_CACHE_TTL + 1)
        middleware = auth_middleware.AuthMiddleware(app=None)

        result = await middleware._validate_api_key(client, _FailingGrpcPool(code), "k")

        assert result == _AUTH_DATA

    @pytest.mark.parametrize(
        "code", [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED]
    )
    async def test_unknown_key_gets_503_not_a_stale_hit(self, code):
        client = _client(_FakeRedis())
        middleware = auth_middleware.AuthMiddleware(app=None)

        with pytest.raises(fastapi.HTTPException) as exc_info:
            await middleware._validate_api_key(client, _FailingGrpcPool(code), "never-seen")

        assert exc_info.value.status_code == 503


class _RecordingAuthStub:
    def __init__(self):
        self.timeouts = []

    async def ValidateApiKey(self, request, timeout=None):
        self.timeouts.append(timeout)
        raise _RpcError(grpc.StatusCode.UNAVAILABLE)


@pytest.mark.asyncio
class TestAuthLookupDeadline:
    async def test_key_validation_uses_the_short_deadline(self):
        stub = _RecordingAuthStub()

        class _Pool:
            def get_stub(self, name, stub_cls):
                return stub

        middleware = auth_middleware.AuthMiddleware(app=None)
        with pytest.raises(fastapi.HTTPException):
            await middleware._validate_api_key(_client(_FakeRedis()), _Pool(), "k")

        assert stub.timeouts == [config.settings.AUTH_VALIDATE_TIMEOUT]
        assert config.settings.AUTH_VALIDATE_TIMEOUT < config.settings.GRPC_TIMEOUT


class TestRetryableGrpcErrorsMapTo503:
    @pytest.mark.parametrize(
        "code",
        [
            grpc.StatusCode.RESOURCE_EXHAUSTED,
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
        ],
    )
    def test_transient_failure_is_retryable(self, code):
        error = otlp_routes._http_error_for(_RpcError(code), "logs")

        assert error.status_code == 503
        assert error.headers["Retry-After"] == "60"

    def test_invalid_argument_stays_a_client_error(self):
        error = otlp_routes._http_error_for(_RpcError(grpc.StatusCode.INVALID_ARGUMENT), "logs")

        assert error.status_code == 400

    def test_internal_error_stays_a_500(self):
        error = otlp_routes._http_error_for(_RpcError(grpc.StatusCode.INTERNAL), "logs")

        assert error.status_code == 500
