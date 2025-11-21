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

    # ==================== Environment ====================

    ENV: typing.Literal["development", "staging", "production", "test"] = (
        pydantic.Field(
            default="development",
            description="Application environment",
        )
    )

    DEBUG: bool = pydantic.Field(
        default=True,
        description="Enable debug mode",
    )

    LOG_LEVEL: typing.Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = (
        pydantic.Field(
            default="INFO",
            description="Logging level",
        )
    )

    # ==================== Server Configuration ====================

    GATEWAY_HOST: str = pydantic.Field(
        default="0.0.0.0",
        description="Gateway HTTP host",
    )

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

    # ==================== Redis Configuration ====================

    REDIS_HOST: str = pydantic.Field(
        default="localhost",
        description="Redis host",
    )

    REDIS_PORT: int = pydantic.Field(
        default=6379,
        description="Redis port",
    )

    REDIS_DB: int = pydantic.Field(
        default=0,
        ge=0,
        le=15,
        description="Redis database number",
    )

    REDIS_PASSWORD: str | None = pydantic.Field(
        default=None,
        description="Redis password",
    )

    REDIS_MAX_CONNECTIONS: int = pydantic.Field(
        default=50,
        ge=10,
        le=200,
        description="Redis connection pool size",
    )

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ==================== gRPC Configuration ====================

    AUTH_SERVICE_HOST: str = pydantic.Field(
        default="localhost",
        description="Auth Service host",
    )

    AUTH_SERVICE_PORT: int = pydantic.Field(
        default=50051,
        description="Auth Service gRPC port",
    )

    @property
    def AUTH_SERVICE_URL(self) -> str:
        return f"{self.AUTH_SERVICE_HOST}:{self.AUTH_SERVICE_PORT}"

    INGESTION_SERVICE_HOST: str = pydantic.Field(
        default="localhost",
        description="Ingestion Service host",
    )

    INGESTION_GRPC_PORT: int = pydantic.Field(
        default=50052,
        description="Ingestion Service gRPC port",
    )

    @property
    def INGESTION_SERVICE_URL(self) -> str:
        return f"{self.INGESTION_SERVICE_HOST}:{self.INGESTION_GRPC_PORT}"

    QUERY_SERVICE_HOST: str = pydantic.Field(
        default="localhost",
        description="Query Service host",
    )

    QUERY_SERVICE_PORT: int = pydantic.Field(
        default=50053,
        description="Query Service gRPC port",
    )

    @property
    def QUERY_SERVICE_URL(self) -> str:
        return f"{self.QUERY_SERVICE_HOST}:{self.QUERY_SERVICE_PORT}"

    GRPC_POOL_SIZE: int = pydantic.Field(
        default=10,
        ge=1,
        le=50,
        description="gRPC channel pool size per service",
    )

    GRPC_KEEPALIVE_TIME_MS: int = pydantic.Field(
        default=10000,
        description="gRPC keepalive ping interval (ms)",
    )

    GRPC_KEEPALIVE_TIMEOUT_MS: int = pydantic.Field(
        default=5000,
        description="gRPC keepalive timeout (ms)",
    )

    GRPC_TIMEOUT: float = pydantic.Field(
        default=5.0,
        ge=1.0,
        le=30.0,
        description="gRPC request timeout (seconds)",
    )

    # ==================== Cache Configuration ====================

    API_KEY_CACHE_TTL: int = pydantic.Field(
        default=300,
        ge=60,
        le=3600,
        description="API key cache TTL (seconds) - 5 minutes",
    )

    EMERGENCY_CACHE_TTL: int = pydantic.Field(
        default=600,
        ge=300,
        le=1800,
        description="Emergency cache TTL for circuit breaker (seconds) - 10 minutes",
    )

    CACHE_TTL_SECONDS: int = pydantic.Field(
        default=300,
        ge=60,
        le=3600,
        description="Default cache TTL (seconds)",
    )

    # ==================== Rate Limiting ====================

    RATE_LIMIT_WINDOW_MINUTE: int = pydantic.Field(
        default=60,
        description="Rate limit minute window (seconds)",
    )

    RATE_LIMIT_WINDOW_HOUR: int = pydantic.Field(
        default=3600,
        description="Rate limit hour window (seconds)",
    )

    # ==================== Circuit Breaker ====================

    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = pydantic.Field(
        default=5,
        ge=3,
        le=20,
        description="Number of failures before opening circuit",
    )

    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = pydantic.Field(
        default=30,
        ge=10,
        le=300,
        description="Seconds to wait before trying recovery",
    )

    CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS: int = pydantic.Field(
        default=3,
        ge=1,
        le=10,
        description="Max concurrent calls in half-open state",
    )

    # ==================== Timeouts ====================

    REDIS_TIMEOUT: float = pydantic.Field(
        default=1.0,
        ge=0.5,
        le=5.0,
        description="Redis operation timeout (seconds)",
    )

    REQUEST_TIMEOUT: float = pydantic.Field(
        default=30.0,
        ge=5.0,
        le=120.0,
        description="HTTP request timeout (seconds)",
    )

    # ==================== Validators ====================

    @pydantic.field_validator("GATEWAY_WORKERS")
    @classmethod
    def validate_workers(cls, v: int, info) -> int:
        if info.data.get("ENV") == "production" and v < 2:
            raise ValueError("Production must have at least 2 workers")
        return v

    @pydantic.field_validator("GRPC_POOL_SIZE")
    @classmethod
    def validate_pool_size(cls, v: int) -> int:
        if v > 50:
            raise ValueError("Pool size > 50 may cause connection overhead")
        return v

    # ==================== Properties ====================

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
