import functools
import typing

import pydantic
import ledger_common.settings


class Settings(
    ledger_common.settings.RedisSettings,
    ledger_common.settings.GrpcKeepaliveSettings,
    ledger_common.settings.SmtpSettings,
    ledger_common.settings.DailyQuotaDefaults,
    ledger_common.settings.JwtSettings,
    ledger_common.settings.ServiceSettings,
):
    GATEWAY_HOST: typing.ClassVar[str] = "0.0.0.0"

    GATEWAY_HTTP_PORT: int = pydantic.Field(
        default=8000,
        description="Gateway HTTP port",
    )

    GATEWAY_WORKERS: int = pydantic.Field(
        default=4,
        ge=1,
        le=32,
        description="Number of worker processes",
    )

    REDIS_MAX_CONNECTIONS: typing.ClassVar[int] = 20

    AUTH_SERVICE_HOST: str = pydantic.Field(
        default="localhost",
        description="Auth Service host",
    )

    AUTH_SERVICE_PORT: typing.ClassVar[int] = 50051

    @property
    def AUTH_SERVICE_URL(self) -> str:
        return f"{self.AUTH_SERVICE_HOST}:{self.AUTH_SERVICE_PORT}"

    INGESTION_SERVICE_HOST: str = pydantic.Field(
        default="localhost",
        description="Ingestion Service host",
    )

    INGESTION_GRPC_PORT: typing.ClassVar[int] = 50052

    @property
    def INGESTION_SERVICE_URL(self) -> str:
        return f"{self.INGESTION_SERVICE_HOST}:{self.INGESTION_GRPC_PORT}"

    QUERY_SERVICE_HOST: str = pydantic.Field(
        default="localhost",
        description="Query Service host",
    )

    QUERY_SERVICE_PORT: typing.ClassVar[int] = 50053

    @property
    def QUERY_SERVICE_URL(self) -> str:
        return f"{self.QUERY_SERVICE_HOST}:{self.QUERY_SERVICE_PORT}"

    GRPC_POOL_SIZE: int = pydantic.Field(
        default=2,
        ge=1,
        le=32,
        description="gRPC channels kept open per internal service (1-2 is usually sufficient "
        "due to HTTP/2 multiplexing)",
    )

    # keepalive/HTTP2 tuning: constants, not expected to change per-deployment.
    GRPC_HTTP2_MAX_PINGS_WITHOUT_DATA: typing.ClassVar[int] = 0
    GRPC_HTTP2_MIN_TIME_BETWEEN_PINGS_MS: typing.ClassVar[int] = 300000
    GRPC_HTTP2_MIN_PING_INTERVAL_WITHOUT_DATA_MS: typing.ClassVar[int] = 300000
    GRPC_TIMEOUT: typing.ClassVar[float] = 30.0
    # ValidateApiKey is one indexed lookup. Channels wait for ready, so with the auth service
    # down a call blocks for its whole deadline - short here so the stale-cache fallback (or a
    # retryable 503) answers before an OTLP exporter gives up on the request.
    AUTH_VALIDATE_TIMEOUT: typing.ClassVar[float] = 3.0

    # Must match auth service's JWT_REFRESH_TOKEN_EXPIRE_DAYS constant; used
    # for the refresh_token cookie max_age.

    FRONTEND_URL: str = pydantic.Field(
        default="http://localhost:3000",
        description="Base URL of the web frontend, used to build links in emails (e.g. email verification)",
    )

    API_KEY_CACHE_TTL: typing.ClassVar[int] = 300
    EMERGENCY_CACHE_TTL: typing.ClassVar[int] = 600

    RATE_LIMIT_WINDOW_MINUTE: typing.ClassVar[int] = 60
    RATE_LIMIT_WINDOW_HOUR: typing.ClassVar[int] = 3600

    REDIS_TIMEOUT: typing.ClassVar[float] = 1.0
    REQUEST_TIMEOUT: typing.ClassVar[float] = 30.0

    # Applies to the wire body and, for gzip uploads, to the inflated body.
    # An SDK export is ~100 records; a collector batch of several thousand
    # spans still fits comfortably.
    MAX_REQUEST_BODY_BYTES: typing.ClassVar[int] = 10 * 1024 * 1024

    NOTIFICATIONS_ENABLED: bool = pydantic.Field(
        default=True,
        description="Enable real-time error notifications via Server-Sent Events (SSE)",
    )

    NOTIFICATIONS_MAX_CONNECTIONS_PER_USER: typing.ClassVar[int] = 5
    NOTIFICATIONS_HEARTBEAT_INTERVAL: typing.ClassVar[int] = 30

    @pydantic.field_validator("GATEWAY_WORKERS")
    @classmethod
    def validate_workers(cls, v: int, info) -> int:
        if info.data.get("ENV") == "production" and v < 2:
            raise ValueError("Production must have at least 2 workers")
        return v


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
