import logging
import typing

from fastapi import HTTPException, Request, status
from gateway_service.services import redis_client
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    EXEMPT_PATHS = {
        "/health",
        "/health/deep",
        "/metrics",
    }

    READ_METHODS = {
        "GET",
        "HEAD",
        "OPTIONS",
    }

    def __init__(self, app):
        super().__init__(app)
        self._total_requests = 0
        self._rate_limited_requests = 0

    async def dispatch(self, request: Request, call_next) -> Response:
        if self._is_exempt_path(request.url.path):
            return await call_next(request)

        self.redis = request.app.state.redis_client

        if not hasattr(request.state, "project_id"):
            return await call_next(request)

        self._total_requests += 1

        try:
            project_id = request.state.project_id
            rate_limits = request.state.rate_limits
            daily_quota = request.state.daily_quota

            await self._check_rate_limits(
                project_id, rate_limits["per_minute"], rate_limits["per_hour"]
            )

            await self._check_daily_quota(project_id, daily_quota)

            response = await call_next(request)

            self._add_rate_limit_headers(response, project_id, rate_limits)

            return response

        except HTTPException as exc:
            from starlette.responses import JSONResponse

            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=getattr(exc, "headers", None),
            )
        except Exception as e:
            logger.error(f"Rate limit middleware error: {e}", exc_info=True)
            return await call_next(request)

    def _is_exempt_path(self, path: str) -> bool:
        return path in self.EXEMPT_PATHS

    async def _check_rate_limits(
        self, project_id: int, limit_per_minute: int, limit_per_hour: int
    ):
        allowed, metadata = await self.redis.check_rate_limit(
            project_id, limit_per_minute, limit_per_hour
        )

        if not allowed:
            self._rate_limited_requests += 1

            hour_exceeded = metadata["hour_count"] > metadata["hour_limit"]

            if hour_exceeded:
                retry_after = 3600
                detail = (
                    f"Hourly rate limit exceeded. "
                    f"Current: {metadata['hour_count']}, "
                    f"Limit: {metadata['hour_limit']}"
                )
            else:
                retry_after = 60
                detail = (
                    f"Per-minute rate limit exceeded. "
                    f"Current: {metadata['minute_count']}, "
                    f"Limit: {metadata['minute_limit']}"
                )

            logger.warning(f"Rate limit exceeded for project {project_id}: {detail}")

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit-Minute": str(metadata["minute_limit"]),
                    "X-RateLimit-Remaining-Minute": str(
                        max(0, metadata["minute_limit"] - metadata["minute_count"])
                    ),
                    "X-RateLimit-Limit-Hour": str(metadata["hour_limit"]),
                    "X-RateLimit-Remaining-Hour": str(
                        max(0, metadata["hour_limit"] - metadata["hour_count"])
                    ),
                },
            )

    async def _check_daily_quota(self, project_id: int, daily_quota: int):
        current_usage = await self.redis.get_daily_usage(project_id)

        if current_usage >= daily_quota:
            logger.warning(
                f"Project {project_id} exceeded daily quota: "
                f"{current_usage}/{daily_quota}"
            )

            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Daily quota exceeded: {current_usage}/{daily_quota}",
            )

    def _add_rate_limit_headers(
        self, response: Response, project_id: int, rate_limits: typing.Dict
    ):
        response.headers["X-RateLimit-Limit-Minute"] = str(rate_limits["per_minute"])
        response.headers["X-RateLimit-Limit-Hour"] = str(rate_limits["per_hour"])

    def get_stats(self) -> typing.Dict:
        rate_limited_percentage = 0.0
        if self._total_requests > 0:
            rate_limited_percentage = (
                self._rate_limited_requests / self._total_requests
            ) * 100

        return {
            "total_requests": self._total_requests,
            "rate_limited_requests": self._rate_limited_requests,
            "rate_limited_percentage": round(rate_limited_percentage, 2),
            "target_rate_limit_percentage": 1.0,
        }


class RateLimitExceeded(Exception):
    def __init__(self, metadata: typing.Dict):
        self.metadata = metadata
        super().__init__("Rate limit exceeded")


def rate_limit(
    per_minute: typing.Optional[int] = None, per_hour: typing.Optional[int] = None
):
    """
    Decorator for endpoint-specific rate limiting.

    Usage:
        @router.post("/expensive-operation")
        @rate_limit(per_minute=10, per_hour=100)
        async def expensive_op():
            ...

    Allows fine-grained control without global middleware overhead.
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if not request:
                return await func(*args, **kwargs)

            redis = request.app.state.redis_client
            project_id = getattr(request.state, "project_id", None)

            if not project_id:
                return await func(*args, **kwargs)

            minute_limit = per_minute or request.state.rate_limits["per_minute"]
            hour_limit = per_hour or request.state.rate_limits["per_hour"]

            allowed, metadata = await redis.check_rate_limit(
                project_id, minute_limit, hour_limit
            )

            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded for this endpoint",
                    headers={"Retry-After": "60"},
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator
