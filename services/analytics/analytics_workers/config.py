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

    LOGS_DB_HOST: str = pydantic.Field(
        default="localhost",
        description="Logs database host",
    )

    LOGS_DB_PORT: int = pydantic.Field(
        default=5432,
        description="Logs database port",
    )

    LOGS_DB_NAME: str = pydantic.Field(
        default="logs_db",
        description="Logs database name",
    )

    LOGS_DB_USER: str = pydantic.Field(
        default="postgres",
        description="Logs database user",
    )

    LOGS_DB_PASSWORD: str = pydantic.Field(
        default="postgres",
        description="Logs database password",
    )

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

    QUERY_TIMEOUT: int = pydantic.Field(
        default=60,
        ge=10,
        le=300,
        description="Query timeout in seconds",
    )

    @property
    def LOGS_DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.LOGS_DB_USER}:{self.LOGS_DB_PASSWORD}"
            f"@{self.LOGS_DB_HOST}:{self.LOGS_DB_PORT}/{self.LOGS_DB_NAME}"
        )

    @property
    def AUTH_DATABASE_URL(self) -> str:
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

    REDIS_MAX_CONNECTIONS: int = pydantic.Field(
        default=30,
        ge=10,
        le=100,
        description="Redis connection pool size",
    )

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    ANALYTICS_ERROR_RATE_CRON: str = pydantic.Field(
        default="*/5 * * * *",
        description="Error rate aggregation cron schedule (minute hour day month day_of_week)",
    )

    ANALYTICS_LOG_VOLUME_CRON: str = pydantic.Field(
        default="*/5 * * * *",
        description="Log volume aggregation cron schedule",
    )

    ANALYTICS_TOP_ERRORS_CRON: str = pydantic.Field(
        default="*/15 * * * *",
        description="Top errors computation cron schedule",
    )

    ANALYTICS_USAGE_STATS_CRON: str = pydantic.Field(
        default="*/5 * * * *",
        description="Usage stats generation cron schedule",
    )

    ANALYTICS_HOURLY_METRICS_CRON: str = pydantic.Field(
        default="0 * * * *",
        description="Hourly metrics aggregation cron schedule",
    )

    ANALYTICS_AVAILABLE_ROUTES_CRON: str = pydantic.Field(
        default="0 * * * *",
        description="Available routes update cron schedule",
    )

    ANALYTICS_ERROR_RATE_TTL: int = pydantic.Field(
        default=600,
        ge=300,
        le=3600,
        description="Error rate cache TTL (seconds)",
    )

    ANALYTICS_LOG_VOLUME_TTL: int = pydantic.Field(
        default=600,
        ge=300,
        le=3600,
        description="Log volume cache TTL (seconds)",
    )

    ANALYTICS_TOP_ERRORS_TTL: int = pydantic.Field(
        default=900,
        ge=300,
        le=3600,
        description="Top errors cache TTL (seconds)",
    )

    ANALYTICS_USAGE_STATS_TTL: int = pydantic.Field(
        default=3600,
        ge=600,
        le=86400,
        description="Usage stats cache TTL (seconds)",
    )

    ANALYTICS_JOB_MISFIRE_GRACE_TIME: int = pydantic.Field(
        default=60,
        ge=10,
        le=300,
        description="Job misfire grace time (seconds)",
    )

    ANALYTICS_QUERY_TIMEOUT: int = pydantic.Field(
        default=60,
        ge=10,
        le=300,
        description="Analytics query timeout (seconds)",
    )

    LOG_LEVEL: typing.Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = (
        pydantic.Field(
            default="INFO",
            description="Logging level",
        )
    )

    def get_log_config(self) -> dict:
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
    return Settings()


settings = get_settings()
