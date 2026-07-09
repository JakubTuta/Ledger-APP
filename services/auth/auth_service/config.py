import functools
import os
import typing

import pydantic
import pydantic_settings


class Settings(pydantic_settings.BaseSettings):
    """
    Application settings with validation.

    Loads from:
    1. Environment variables
    2. .env file
    3. Default values
    """

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

    # gRPC server port + keepalive/HTTP2 tuning: not expected to change
    # per-deployment, so these are constants rather than env-overridable.

    AUTH_GRPC_PORT: typing.ClassVar[int] = 50051
    GRPC_KEEPALIVE_TIME_MS: typing.ClassVar[int] = 300000
    GRPC_KEEPALIVE_TIMEOUT_MS: typing.ClassVar[int] = 20000
    GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS: typing.ClassVar[int] = 1
    GRPC_MAX_CONNECTION_IDLE_MS: typing.ClassVar[int] = 3600000
    GRPC_MAX_CONNECTION_AGE_MS: typing.ClassVar[int] = 86400000
    GRPC_HTTP2_MIN_RECV_PING_INTERVAL_WITHOUT_DATA_MS: typing.ClassVar[int] = 120000

    AUTH_DB_HOST: str = pydantic.Field(
        default="localhost",
        description="Auth database host",
    )

    AUTH_DB_PORT: int = pydantic.Field(
        default=5432,
        description="Auth database port",
    )

    AUTH_DB_NAME: str = pydantic.Field(
        default="auth_db",
        description="Auth database name",
    )

    AUTH_DB_USER: str = pydantic.Field(
        default="postgres",
        description="Auth database user",
    )

    AUTH_DB_PASSWORD: str = pydantic.Field(
        default="postgres",
        description="Auth database password",
    )

    DB_POOL_SIZE: typing.ClassVar[int] = 20
    DB_MAX_OVERFLOW: typing.ClassVar[int] = 10

    @property
    def AUTH_DATABASE_URL(self) -> str:
        """Build async PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.AUTH_DB_USER}:{self.AUTH_DB_PASSWORD}"
            f"@{self.AUTH_DB_HOST}:{self.AUTH_DB_PORT}/{self.AUTH_DB_NAME}"
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
        description="Redis password (optional)",
    )

    @property
    def REDIS_URL(self) -> str:
        """Build Redis connection URL."""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    JWT_SECRET: str = pydantic.Field(
        default="your-secret-key-change-this-in-production",
        min_length=32,
        description="JWT signing secret (min 32 chars)",
    )

    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: typing.ClassVar[int] = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: typing.ClassVar[int] = 7
    BCRYPT_ROUNDS: typing.ClassVar[int] = 12

    DEFAULT_RATE_LIMIT_PER_MINUTE: typing.ClassVar[int] = 1000
    DEFAULT_RATE_LIMIT_PER_HOUR: typing.ClassVar[int] = 20_000
    DEFAULT_DAILY_QUOTA: typing.ClassVar[int] = 100_000

    CACHE_TTL_SECONDS: typing.ClassVar[int] = 300
    DASHBOARD_CACHE_TTL: typing.ClassVar[int] = 300

    LOG_LEVEL: typing.Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = pydantic.Field(
        default="INFO",
        description="Logging level",
    )

    @pydantic.field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        """Ensure JWT secret is strong in production."""
        if info.data.get("ENV") == "production":
            if v == "your-secret-key-change-this-in-production":
                raise ValueError("Must set JWT_SECRET in production!")
            if len(v) < 32:
                raise ValueError("JWT_SECRET must be at least 32 characters")
        return v


@functools.lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses LRU cache to avoid re-parsing environment on every call.
    """
    return Settings()


settings = get_settings()
