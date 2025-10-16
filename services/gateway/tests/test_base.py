import pytest_asyncio
import httpx

import gateway_service.main as main
import tests.mocks as mocks


class BaseGatewayTest:
    @pytest_asyncio.fixture(autouse=True)
    async def setup_method(self):
        self.mock_redis = mocks.MockRedisClient()
        self.mock_grpc_pool = mocks.MockGRPCPool()

        main.app.state.redis_client = self.mock_redis
        main.app.state.grpc_pool = self.mock_grpc_pool

        for middleware in main.app.user_middleware:
            if hasattr(middleware, 'kwargs'):
                if 'redis_client' in middleware.kwargs:
                    middleware.kwargs['redis_client'] = self.mock_redis
                if 'grpc_pool' in middleware.kwargs:
                    middleware.kwargs['grpc_pool'] = self.mock_grpc_pool

        if hasattr(main.app, 'middleware_stack'):
            self._update_middleware_in_stack(main.app.middleware_stack)

        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app),
            base_url="http://test"
        )

        yield

        await self.client.aclose()

    def _update_middleware_in_stack(self, middleware_stack):
        if hasattr(middleware_stack, 'app'):
            self._update_middleware_in_stack(middleware_stack.app)
        if hasattr(middleware_stack, 'redis'):
            middleware_stack.redis = self.mock_redis
        if hasattr(middleware_stack, 'grpc_pool'):
            middleware_stack.grpc_pool = self.mock_grpc_pool

    def get_mock_auth_stub(self):
        return self.mock_grpc_pool.get_stub("auth", None)

    async def set_api_key_cache(
        self,
        api_key: str,
        project_id: int = 1,
        account_id: int = 1,
        rate_limit_per_minute: int = 1000,
        rate_limit_per_hour: int = 50000,
        daily_quota: int = 1000000,
        current_usage: int = 0,
    ):
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": project_id,
                "account_id": account_id,
                "rate_limit_per_minute": rate_limit_per_minute,
                "rate_limit_per_hour": rate_limit_per_hour,
                "daily_quota": daily_quota,
                "current_usage": current_usage,
            },
        )
