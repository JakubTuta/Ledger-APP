import logging
import typing

from fastapi import HTTPException, status
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_SESSION_RATE_LIMIT_PER_MINUTE = 300
_SESSION_RATE_LIMIT_PER_HOUR = 10_000
_NEGATIVE_KEY_CACHE_TTL = 30


class RateLimitMiddleware:
    EXEMPT_PATHS = {
        "/health",
        "/health/deep",
        "/metrics",
    }

    # OTLP routes reserve quota atomically per-item before forwarding to gRPC and
    # report denials as an OTLP partial-success response (200), not a hard error -
    # a hard 402 here would make OTel exporters treat it as retriable and retry-storm.
    DAILY_QUOTA_EXEMPT_PATHS = {
        "/v1/logs",
        "/v1/traces",
        "/v1/metrics",
    }

    READ_METHODS = {
        "GET",
        "HEAD",
        "OPTIONS",
    }

    def __init__(self, app: ASGIApp):
        self.app = app
        self._total_requests = 0
        self._rate_limited_requests = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        scope["app"].state.rate_limit_middleware = self

        if self._is_exempt_path(scope["path"]):
            await self.app(scope, receive, send)
            return

        self.redis = scope["app"].state.redis_client
        request = Request(scope, receive=receive)

        if not hasattr(request.state, "project_id"):
            await self.app(scope, receive, send)
            return

        self._total_requests += 1
        project_id = request.state.project_id
        extra_headers: dict[str, str] = {}

        # Only the rate-limit bookkeeping itself is inside this try — the
        # downstream `self.app(...)` call is deliberately outside it and made
        # exactly once below. Wrapping the downstream call in this try would
        # mean any unrelated exception raised by a route (a bug, a bad mock
        # in tests, anything) gets caught here and triggers a *second* call
        # to self.app with the same `receive` channel, which has already been
        # drained by the first call — the retry then hangs forever awaiting a
        # body message that will never arrive.
        try:
            if project_id is None:
                account_id = getattr(request.state, "account_id", None)
                if account_id:
                    await self._check_rate_limits(
                        account_id,
                        _SESSION_RATE_LIMIT_PER_MINUTE,
                        _SESSION_RATE_LIMIT_PER_HOUR,
                        key_prefix="session",
                    )
            else:
                rate_limits = request.state.rate_limits
                logs_daily_quota = request.state.logs_daily_quota

                await self._check_rate_limits(
                    project_id, rate_limits["per_minute"], rate_limits["per_hour"]
                )

                if request.url.path not in self.DAILY_QUOTA_EXEMPT_PATHS:
                    await self._check_daily_quota(project_id, logs_daily_quota)

                extra_headers = {
                    "X-RateLimit-Limit-Minute": str(rate_limits["per_minute"]),
                    "X-RateLimit-Limit-Hour": str(rate_limits["per_hour"]),
                }

        except HTTPException as exc:
            response = JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=getattr(exc, "headers", None),
            )
            await response(scope, receive, send)
            return
        except Exception as e:
            # Fail open: a bug in rate-limit bookkeeping itself must not block
            # traffic. Falls through to the single downstream call below.
            logger.error(f"Rate limit middleware error: {e}", exc_info=True)

        if not extra_headers:
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                for key, value in extra_headers.items():
                    headers.append((key.encode(), value.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)

    def _is_exempt_path(self, path: str) -> bool:
        return path in self.EXEMPT_PATHS

    async def _check_rate_limits(
        self,
        entity_id: int,
        limit_per_minute: int,
        limit_per_hour: int,
        key_prefix: str = "project",
    ):
        allowed, metadata = await self.redis.check_rate_limit(
            entity_id, limit_per_minute, limit_per_hour, key_prefix=key_prefix
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

            logger.warning(f"Rate limit exceeded for {key_prefix}:{entity_id}: {detail}")

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

    async def _check_daily_quota(self, project_id: int, logs_daily_quota: int):
        current_usage = await self.redis.get_daily_usage(project_id, signal="logs")

        if current_usage >= logs_daily_quota:
            logger.warning(
                f"Project {project_id} exceeded daily logs quota: "
                f"{current_usage}/{logs_daily_quota}"
            )

            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Daily quota exceeded: {current_usage}/{logs_daily_quota}",
            )

    def get_stats(self) -> typing.Dict:
        rate_limited_percentage = 0.0
        if self._total_requests > 0:
            rate_limited_percentage = (self._rate_limited_requests / self._total_requests) * 100

        return {
            "total_requests": self._total_requests,
            "rate_limited_requests": self._rate_limited_requests,
            "rate_limited_percentage": round(rate_limited_percentage, 2),
            "target_rate_limit_percentage": 1.0,
        }
