import asyncio
import logging
import typing

import fastapi
import grpc
import jwt
from gateway_service import config
from gateway_service.proto import auth_pb2, auth_pb2_grpc
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """High-performance authentication middleware (pure ASGI)."""

    PUBLIC_PATHS = {
        "/health",
        "/health/deep",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/api/v1/accounts/register",
        "/api/v1/accounts/login",
        "/api/v1/accounts/refresh",
        # Email verification: the token in the request body IS the
        # credential, there's no session yet for a brand-new registrant.
        "/api/v1/accounts/verify-email",
        # 2FA login completion: the caller only has a short-lived opaque
        # totp_session_token (from /accounts/login) at this point, not a
        # session token yet — that's exactly what this endpoint mints.
        "/api/v1/accounts/2fa/login",
    }

    def __init__(self, app: ASGIApp):
        self.app = app
        self._cache_hits = 0
        self._cache_misses = 0
        self._auth_failures = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Main middleware logic."""

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        scope["app"].state.auth_middleware = self

        if self._is_public_path(scope["path"]):
            await self.app(scope, receive, send)
            return

        self.redis = scope["app"].state.redis_client
        self.grpc_pool = scope["app"].state.grpc_pool
        request = Request(scope, receive=receive)

        try:
            token, auth_type = self._extract_auth_token(request)

            if auth_type == "session":
                auth_data = await self._validate_session_token(token)
            else:
                auth_data = await self._validate_api_key(token)

            state = scope.setdefault("state", {})
            state["project_id"] = auth_data.get("project_id")
            state["account_id"] = auth_data["account_id"]
            state["rate_limits"] = auth_data.get(
                "rate_limits",
                {
                    "per_minute": auth_data.get("rate_limit_per_minute", 1000),
                    "per_hour": auth_data.get("rate_limit_per_hour", 50000),
                },
            )
            state["logs_daily_quota"] = auth_data.get(
                "logs_daily_quota", config.settings.DEFAULT_LOGS_DAILY_QUOTA
            )
            state["spans_daily_quota"] = auth_data.get(
                "spans_daily_quota", config.settings.DEFAULT_SPANS_DAILY_QUOTA
            )
            state["metrics_daily_quota"] = auth_data.get(
                "metrics_daily_quota", config.settings.DEFAULT_METRICS_DAILY_QUOTA
            )

            await self.app(scope, receive, send)

        except fastapi.HTTPException as exc:
            response = JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=getattr(exc, "headers", None),
            )
            await response(scope, receive, send)

        except Exception as e:
            logger.error(f"Auth middleware error: {e}", exc_info=True)
            response = JSONResponse(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Authentication service error"},
            )
            await response(scope, receive, send)

    def _is_public_path(self, path: str) -> bool:
        if path in self.PUBLIC_PATHS:
            return True

        # Heartbeat ping endpoint is authenticated by the token embedded in
        # the URL path itself (POST /api/v1/monitors/{token}/ping), not by
        # the normal JWT/API-key headers, so it can't be a fixed PUBLIC_PATHS
        # entry. Match on prefix + suffix instead of a full path.
        if path.startswith("/api/v1/monitors/") and path.endswith("/ping"):
            return True

        return False

    def _extract_auth_token(self, request: fastapi.Request) -> typing.Tuple[str, str]:
        """
        Extract authentication token and type from request.

        Returns:
            Tuple of (token, auth_type) where auth_type is either 'session' or 'api_key'
        """
        api_key_header = request.headers.get("X-API-Key")
        if api_key_header:
            return (api_key_header, "api_key")

        auth_header = request.headers.get("Authorization")

        if not auth_header:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail="Missing authentication header (X-API-Key or Authorization)",
                headers={"WWW-Authenticate": "Bearer"},
            )

        parts = auth_header.split()

        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
            if token.startswith("ledger_"):
                return (token, "api_key")
            else:
                return (token, "session")
        elif len(parts) == 1:
            return (parts[0], "api_key")
        else:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header format",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def _validate_session_token(self, token: str) -> typing.Dict:
        """
        Validate JWT access token from login.

        Returns:
            Dict with account_id and other session data
        """
        try:
            settings = config.get_settings()

            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])

            if payload.get("type") != "access":
                self._auth_failures += 1
                raise fastapi.HTTPException(
                    status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type",
                )

            return {
                "account_id": int(payload["sub"]),
                "email": payload.get("email"),
                "project_id": None,
            }

        except jwt.ExpiredSignatureError:
            self._auth_failures += 1
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
            )
        except jwt.InvalidTokenError as e:
            logger.error(f"JWT validation error: {e}")
            self._auth_failures += 1
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or malformed token",
            )
        except Exception as e:
            logger.error(f"Unexpected error validating JWT: {e}", exc_info=True)
            self._auth_failures += 1
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed",
            )

    _NEGATIVE_CACHE_TTL = 30

    async def _validate_api_key(self, api_key: str) -> typing.Dict:
        cached_data = await self.redis.get_cached_api_key(api_key)

        if cached_data:
            if cached_data.get("__invalid__"):
                self._auth_failures += 1
                raise fastapi.HTTPException(
                    status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired API key",
                )
            self._cache_hits += 1
            return cached_data

        self._cache_misses += 1

        try:
            auth_data = await self._fetch_from_auth_service(api_key)
        except fastapi.HTTPException as exc:
            if exc.status_code == fastapi.status.HTTP_401_UNAUTHORIZED:
                task = asyncio.create_task(
                    self.redis.set_cached_api_key(
                        api_key, {"__invalid__": True}, ttl=self._NEGATIVE_CACHE_TTL
                    )
                )
                task.add_done_callback(
                    lambda t: (
                        logger.error("Negative cache write failed: %s", t.exception())
                        if not t.cancelled() and t.exception()
                        else None
                    )
                )
            raise

        task = asyncio.create_task(self.redis.set_cached_api_key(api_key, auth_data))
        task.add_done_callback(
            lambda t: (
                logger.error("Cache write failed: %s", t.exception())
                if not t.cancelled() and t.exception()
                else None
            )
        )

        return auth_data

    async def _fetch_from_auth_service(self, api_key: str) -> typing.Dict:
        try:
            stub = self.grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

            request = auth_pb2.ValidateApiKeyRequest(api_key=api_key)

            response = await stub.ValidateApiKey(request, timeout=config.settings.GRPC_TIMEOUT)

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
                "logs_daily_quota": response.logs_daily_quota,
                "spans_daily_quota": response.spans_daily_quota,
                "metrics_daily_quota": response.metrics_daily_quota,
            }

            return auth_data

        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")

            if e.code() in (grpc.StatusCode.DEADLINE_EXCEEDED, grpc.StatusCode.UNAVAILABLE):
                stale_data = await self.redis.get_stale_cache(api_key)
                if stale_data:
                    logger.warning("Using stale cache due to auth service error")
                    return stale_data

                if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                    logger.error("Auth Service timeout")
                    raise fastapi.HTTPException(
                        status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Authentication service timeout",
                    )

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
        "logs_daily_quota": request.state.logs_daily_quota,
        "spans_daily_quota": request.state.spans_daily_quota,
        "metrics_daily_quota": request.state.metrics_daily_quota,
    }
