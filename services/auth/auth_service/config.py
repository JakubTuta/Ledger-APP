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

    # ==================== Service Configuration ====================

    AUTH_GRPC_PORT: int = pydantic.Field(
        default=50051,
        description="gRPC server port",
    )

    # ==================== Database Configuration ====================

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

    DB_POOL_SIZE: int = pydantic.Field(
        default=20,
        ge=5,
        le=100,
        description="Database connection pool size",
    )

    DB_MAX_OVERFLOW: int = pydantic.Field(
        default=10,
        ge=0,
        le=50,
        description="Max overflow connections",
    )

    @property
    def AUTH_DATABASE_URL(self) -> str:
        """Build async PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.AUTH_DB_USER}:{self.AUTH_DB_PASSWORD}"
            f"@{self.AUTH_DB_HOST}:{self.AUTH_DB_PORT}/{self.AUTH_DB_NAME}"
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
        description="Redis password (optional)",
    )

    @property
    def REDIS_URL(self) -> str:
        """Build Redis connection URL."""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ==================== Security ====================

    JWT_SECRET: str = pydantic.Field(
        default="your-secret-key-change-this-in-production",
        min_length=32,
        description="JWT signing secret (min 32 chars)",
    )

    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = pydantic.Field(
        default=15,
        ge=5,
        le=1440,
        description="Access token expiration (minutes)",
    )

    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = pydantic.Field(
        default=7,
        ge=1,
        le=30,
        description="Refresh token expiration (days)",
    )

    BCRYPT_ROUNDS: int = pydantic.Field(
        default=12,
        ge=10,
        le=14,
        description="Bcrypt cost factor (higher = slower + more secure)",
    )

    # ==================== Rate Limiting ====================

    DEFAULT_RATE_LIMIT_PER_MINUTE: int = pydantic.Field(
        default=1000,
        ge=10,
        le=100_000,
        description="Default rate limit per minute",
    )

    DEFAULT_RATE_LIMIT_PER_HOUR: int = pydantic.Field(
        default=50_000,
        ge=100,
        le=10_000_000,
        description="Default rate limit per hour",
    )

    DEFAULT_DAILY_QUOTA: int = pydantic.Field(
        default=1_000_000,
        ge=1_000,
        le=100_000_000,
        description="Default daily log quota",
    )

    # ==================== Caching ====================

    CACHE_TTL_SECONDS: int = pydantic.Field(
        default=300,
        ge=60,
        le=3600,
        description="Cache TTL (seconds)",
    )

    # ==================== Monitoring ====================

    LOG_LEVEL: typing.Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = (
        pydantic.Field(
            default="INFO",
            description="Logging level",
        )
    )

    # ==================== Validators ====================

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

    # ==================== Environment-Specific Overrides ====================

    def get_log_config(self) -> dict:
        """Get logging configuration based on environment."""
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                },
                "json": {
                    "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                    "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default" if self.ENV == "development" else "json",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "level": self.LOG_LEVEL,
                "handlers": ["console"],
            },
        }


@functools.lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses LRU cache to avoid re-parsing environment on every call.
    """
    return Settings()


settings = get_settings()
