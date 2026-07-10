import functools
import os
import typing

import pydantic
import pydantic_settings


class Settings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(
        env_file=os.getenv("ENV_FILE_PATH", "../../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ENV: typing.Literal["development", "staging", "production", "test"] = pydantic.Field(
        default="development",
        description="Application environment",
    )

    DEBUG: bool = pydantic.Field(
        default=True,
        description="Enable debug mode",
    )

    LOG_LEVEL: typing.Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = pydantic.Field(
        default="INFO",
        description="Logging level",
    )

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

    REDIS_HOST: str = pydantic.Field(
        default="localhost",
        description="Redis host",
    )

    REDIS_PORT: int = pydantic.Field(
        default=6379,
        description="Redis port",
    )

    REDIS_DB: typing.ClassVar[int] = 0

    REDIS_PASSWORD: str | None = pydantic.Field(
        default=None,
        description="Redis password",
    )

    REDIS_MAX_CONNECTIONS: typing.ClassVar[int] = 50

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

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

    # gRPC channel pool size per service (1-2 is usually sufficient due to
    # HTTP/2 multiplexing) + keepalive/HTTP2 tuning: constants, not expected
    # to change per-deployment.
    GRPC_POOL_SIZE: typing.ClassVar[int] = 2
    GRPC_KEEPALIVE_TIME_MS: typing.ClassVar[int] = 300000
    GRPC_KEEPALIVE_TIMEOUT_MS: typing.ClassVar[int] = 20000
    GRPC_HTTP2_MAX_PINGS_WITHOUT_DATA: typing.ClassVar[int] = 0
    GRPC_HTTP2_MIN_TIME_BETWEEN_PINGS_MS: typing.ClassVar[int] = 300000
    GRPC_HTTP2_MIN_PING_INTERVAL_WITHOUT_DATA_MS: typing.ClassVar[int] = 300000
    GRPC_TIMEOUT: typing.ClassVar[float] = 30.0

    JWT_SECRET: str = pydantic.Field(
        default="your-secret-key-change-this-in-production",
        min_length=32,
        description="JWT signing secret (min 32 chars)",
    )

    # Must match auth service's JWT_REFRESH_TOKEN_EXPIRE_DAYS constant; used
    # for the refresh_token cookie max_age.
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: typing.ClassVar[int] = 7

    FRONTEND_URL: str = pydantic.Field(
        default="http://localhost:3000",
        description="Base URL of the web frontend, used to build links in emails (e.g. email verification)",
    )

    EMAIL_ENABLED: bool = pydantic.Field(
        default=False,
        description="Enable outbound transactional email (verification emails)",
    )

    SMTP_HOST: str = pydantic.Field(
        default="smtp.gmail.com",
        description="SMTP server hostname",
    )

    SMTP_PORT: int = pydantic.Field(
        default=465,
        description="SMTP server port (465 = implicit TLS, 587 = STARTTLS)",
    )

    SMTP_USER: str = pydantic.Field(
        default="",
        description="SMTP username",
    )

    SMTP_PASSWORD: str = pydantic.Field(
        default="",
        description="SMTP password (app password, not account password)",
    )

    SMTP_FROM: str = pydantic.Field(
        default="",
        description="From address; falls back to SMTP_USER when empty",
    )

    SMTP_USE_TLS: typing.ClassVar[bool] = True

    API_KEY_CACHE_TTL: typing.ClassVar[int] = 300
    EMERGENCY_CACHE_TTL: typing.ClassVar[int] = 600
    CACHE_TTL_SECONDS: typing.ClassVar[int] = 300

    RATE_LIMIT_WINDOW_MINUTE: typing.ClassVar[int] = 60
    RATE_LIMIT_WINDOW_HOUR: typing.ClassVar[int] = 3600

    CIRCUIT_BREAKER_FAILURE_THRESHOLD: typing.ClassVar[int] = 5
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: typing.ClassVar[int] = 30
    CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS: typing.ClassVar[int] = 3

    REDIS_TIMEOUT: typing.ClassVar[float] = 1.0
    REQUEST_TIMEOUT: typing.ClassVar[float] = 30.0

    NOTIFICATIONS_ENABLED: bool = pydantic.Field(
        default=True,
        description="Enable real-time error notifications via Server-Sent Events (SSE)",
    )

    NOTIFICATIONS_MAX_CONNECTIONS_PER_USER: typing.ClassVar[int] = 5
    NOTIFICATIONS_HEARTBEAT_INTERVAL: typing.ClassVar[int] = 30

    @pydantic.field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        if info.data.get("ENV") == "production":
            if v == "your-secret-key-change-this-in-production":
                raise ValueError("Must set JWT_SECRET in production!")
            if len(v) < 32:
                raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @pydantic.field_validator("GATEWAY_WORKERS")
    @classmethod
    def validate_workers(cls, v: int, info) -> int:
        if info.data.get("ENV") == "production" and v < 2:
            raise ValueError("Production must have at least 2 workers")
        return v

    DEFAULT_LOGS_DAILY_QUOTA: typing.ClassVar[int] = 100_000
    DEFAULT_SPANS_DAILY_QUOTA: typing.ClassVar[int] = 300_000
    DEFAULT_METRICS_DAILY_QUOTA: typing.ClassVar[int] = 100_000

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.ENV.lower() == "development"


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
