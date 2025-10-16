import asyncio
import logging
import typing

import fastapi
import grpc
from gateway_service import config
from gateway_service.proto import auth_pb2, auth_pb2_grpc
from gateway_service.services import grpc_pool, redis_client
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """High-performance authentication middleware."""

    PUBLIC_PATHS = {
        "/health",
        "/health/deep",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/api/v1/accounts/register",
        "/api/v1/accounts/login",
    }

    def __init__(
        self,
        app,
        redis_client: redis_client.RedisClient,
        grpc_pool: grpc_pool.GRPCPoolManager,
    ):
        super().__init__(app)
        self.redis = redis_client
        self.grpc_pool = grpc_pool

        self._cache_hits = 0
        self._cache_misses = 0
        self._auth_failures = 0

    async def dispatch(self, request: fastapi.Request, call_next) -> Response:
        """Main middleware logic."""

        if self._is_public_path(request.url.path):
            return await call_next(request)

        try:
            api_key = self._extract_api_key(request)

            auth_data = await self._validate_api_key(api_key)

            request.state.project_id = auth_data["project_id"]
            request.state.account_id = auth_data["account_id"]
            request.state.rate_limits = {
                "per_minute": auth_data["rate_limit_per_minute"],
                "per_hour": auth_data["rate_limit_per_hour"],
            }
            request.state.daily_quota = auth_data["daily_quota"]

            return await call_next(request)

        except fastapi.HTTPException as exc:
            from starlette.responses import JSONResponse

            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=getattr(exc, "headers", None),
            )

        except Exception as e:
            logger.error(f"Auth middleware error: {e}", exc_info=True)
            from starlette.responses import JSONResponse

            return JSONResponse(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Authentication service error"},
            )

    def _is_public_path(self, path: str) -> bool:
        return path in self.PUBLIC_PATHS

    def _extract_api_key(self, request: fastapi.Request) -> str:
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail="Missing Authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        parts = auth_header.split()

        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
        elif len(parts) == 1:
            return parts[0]
        else:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header format",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def _validate_api_key(self, api_key: str) -> typing.Dict:
        cached_data = await self.redis.get_cached_api_key(api_key)

        if cached_data:
            self._cache_hits += 1
            logger.debug(
                f"Cache HIT for API key (hit rate: {self._get_hit_rate():.1f}%)"
            )
            return cached_data

        self._cache_misses += 1
        logger.debug(f"Cache MISS for API key (hit rate: {self._get_hit_rate():.1f}%)")

        auth_data = await self._fetch_from_auth_service(api_key)

        asyncio.create_task(self.redis.set_cached_api_key(api_key, auth_data))

        return auth_data

    async def _fetch_from_auth_service(self, api_key: str) -> typing.Dict:
        try:
            stub = self.grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

            request = auth_pb2.ValidateApiKeyRequest(api_key=api_key)

            response = await asyncio.wait_for(
                stub.ValidateApiKey(request), timeout=config.settings.GRPC_TIMEOUT
            )

            if not response.valid:
                self._auth_failures += 1
                raise fastapi.HTTPException(
                    status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired API key",
                )

            auth_data = {
                "project_id": response.project_id,
                "account_id": response.account_id,
                "rate_limit_per_minute": response.rate_limit_per_minute,
                "rate_limit_per_hour": response.rate_limit_per_hour,
                "daily_quota": response.daily_quota,
                "current_usage": response.current_usage,
            }

            return auth_data

        except asyncio.TimeoutError:
            logger.error("Auth Service timeout")
            stale_data = await self.redis.get_stale_cache(api_key)
            if stale_data:
                logger.warning("Using stale cache due to timeout")
                return stale_data

            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service timeout",
            )

        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")

            if e.code() == grpc.StatusCode.UNAVAILABLE:
                stale_data = await self.redis.get_stale_cache(api_key)
                if stale_data:
                    logger.warning("Using stale cache due to service unavailability")
                    return stale_data

                raise fastapi.HTTPException(
                    status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service unavailable",
                )

            elif e.code() == grpc.StatusCode.INVALID_ARGUMENT:
                raise fastapi.HTTPException(
                    status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                    detail="Invalid API key format",
                )

            else:
                raise fastapi.HTTPException(
                    status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Authentication service error",
                )

    def _get_hit_rate(self) -> float:
        total = self._cache_hits + self._cache_misses
        if total == 0:
            return 0.0
        return (self._cache_hits / total) * 100

    def get_stats(self) -> typing.Dict:
        total_requests = self._cache_hits + self._cache_misses

        return {
            "total_auth_requests": total_requests,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": self._get_hit_rate(),
            "auth_failures": self._auth_failures,
            "target_hit_rate": 95.0,
        }


def get_auth_data(request: fastapi.Request) -> typing.Dict:
    """
    Extract authentication data from request state.

    Usage in routes:
        @router.get("/projects")
        async def list_projects(auth: Dict = Depends(get_auth_data)):
            project_id = auth["project_id"]
            ...
    """

    if not hasattr(request.state, "project_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return {
        "project_id": request.state.project_id,
        "account_id": request.state.account_id,
        "rate_limits": request.state.rate_limits,
        "daily_quota": request.state.daily_quota,
    }
