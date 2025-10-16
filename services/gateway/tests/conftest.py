import pytest
import pytest_asyncio
import httpx

import gateway_service.main as main
import tests.mocks as mocks


@pytest_asyncio.fixture
async def mock_redis():
    return mocks.MockRedisClient()


@pytest.fixture
def mock_grpc_pool():
    return mocks.MockGRPCPool()


@pytest_asyncio.fixture
async def async_client(mock_redis, mock_grpc_pool):
    main.app.state.redis_client = mock_redis
    main.app.state.grpc_pool = mock_grpc_pool

    for middleware in main.app.user_middleware:
        if hasattr(middleware, 'kwargs'):
            if 'redis_client' in middleware.kwargs:
                middleware.kwargs['redis_client'] = mock_redis
            if 'grpc_pool' in middleware.kwargs:
                middleware.kwargs['grpc_pool'] = mock_grpc_pool

    if hasattr(main.app, 'middleware_stack'):
        _update_middleware_in_stack(main.app.middleware_stack, mock_redis, mock_grpc_pool)

    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app),
        base_url="http://test"
    )

    yield client

    await client.aclose()


def _update_middleware_in_stack(middleware_stack, mock_redis, mock_grpc_pool):
    if hasattr(middleware_stack, 'app'):
        _update_middleware_in_stack(middleware_stack.app, mock_redis, mock_grpc_pool)
    if hasattr(middleware_stack, 'redis'):
        middleware_stack.redis = mock_redis
    if hasattr(middleware_stack, 'grpc_pool'):
        middleware_stack.grpc_pool = mock_grpc_pool
