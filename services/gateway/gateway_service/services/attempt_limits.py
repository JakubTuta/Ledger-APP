"""Attempt limits for the endpoints that run before authentication.

RateLimitMiddleware only meters authenticated callers, so login, registration,
2FA completion, token refresh and heartbeat pings had no limit at all: a
password or 6-digit TOTP code could be guessed as fast as the network allows,
and every login attempt also costs a bcrypt hash on the auth service.
"""

import dataclasses
import hashlib

import fastapi

from gateway_service.services import redis_client


@dataclasses.dataclass(frozen=True)
class AttemptLimit:
    name: str
    max_attempts: int
    window_seconds: int


LOGIN_PER_IP = AttemptLimit("login_ip", max_attempts=20, window_seconds=60)
LOGIN_PER_EMAIL = AttemptLimit("login_email", max_attempts=10, window_seconds=900)
REGISTER_PER_IP = AttemptLimit("register_ip", max_attempts=5, window_seconds=600)
TOTP_PER_IP = AttemptLimit("totp_ip", max_attempts=20, window_seconds=60)
# Matches the totp session lifetime: five codes per password entry.
TOTP_PER_SESSION = AttemptLimit("totp_session", max_attempts=5, window_seconds=300)
REFRESH_PER_IP = AttemptLimit("refresh_ip", max_attempts=60, window_seconds=60)
VERIFY_EMAIL_PER_IP = AttemptLimit("verify_email_ip", max_attempts=20, window_seconds=60)
RESEND_VERIFICATION_PER_ACCOUNT = AttemptLimit(
    "resend_verification", max_attempts=3, window_seconds=600
)
HEARTBEAT_PER_TOKEN = AttemptLimit("heartbeat", max_attempts=120, window_seconds=60)


def client_ip(request: fastapi.Request) -> str:
    """The caller's address as seen by our reverse proxy.

    The gateway is only reachable through that proxy, which appends the
    address it accepted the connection from as the last X-Forwarded-For hop;
    every earlier hop is client-supplied and must not be trusted.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.rsplit(",", 1)[-1].strip()
    return request.client.host if request.client else "unknown"


async def enforce(redis: redis_client.RedisClient, limit: AttemptLimit, subject: str) -> None:
    """Count one attempt by `subject`; raise 429 once the window's budget is spent."""
    subject_hash = hashlib.sha256(subject.encode()).hexdigest()[:32]
    attempts = await redis.increment_window_counter(
        f"attempts:{limit.name}:{subject_hash}", limit.window_seconds
    )
    if attempts > limit.max_attempts:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts, please try again later",
            headers={"Retry-After": str(limit.window_seconds)},
        )
