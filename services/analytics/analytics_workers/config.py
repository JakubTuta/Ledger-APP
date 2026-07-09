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

    DB_POOL_SIZE: typing.ClassVar[int] = 20
    DB_MAX_OVERFLOW: typing.ClassVar[int] = 10

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

    REDIS_DB: typing.ClassVar[int] = 0
    REDIS_MAX_CONNECTIONS: typing.ClassVar[int] = 30

    REDIS_PASSWORD: str | None = pydantic.Field(
        default=None,
        description="Redis password (optional)",
    )

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    EMAIL_ENABLED: bool = pydantic.Field(
        default=False,
        description="Enable outbound email alert delivery",
    )

    SMTP_HOST: str = pydantic.Field(
        default="smtp.gmail.com",
        description="SMTP server hostname",
    )

    SMTP_PORT: int = pydantic.Field(
        default=587,
        description="SMTP server port (587 = STARTTLS)",
    )

    SMTP_USER: str = pydantic.Field(
        default="",
        description="SMTP username (Gmail address)",
    )

    SMTP_PASSWORD: str = pydantic.Field(
        default="",
        description="SMTP password (Gmail App Password, not account password)",
    )

    SMTP_FROM: str = pydantic.Field(
        default="",
        description="From address; falls back to SMTP_USER when empty",
    )

    SMTP_USE_TLS: typing.ClassVar[bool] = True

    ANALYTICS_LOG_METRICS_CRON: str = pydantic.Field(
        default="*/10 * * * *",
        description="Combined log volume + error rate aggregation cron schedule (minute hour day month day_of_week)",
    )

    ANALYTICS_TOP_ERRORS_CRON: str = pydantic.Field(
        default="*/30 * * * *",
        description="Top errors computation cron schedule",
    )

    ANALYTICS_USAGE_STATS_CRON: str = pydantic.Field(
        default="*/10 * * * *",
        description="Usage stats generation cron schedule",
    )

    ANALYTICS_HOURLY_METRICS_CRON: str = pydantic.Field(
        default="0 * * * *",
        description="Hourly metrics aggregation cron schedule",
    )

    ANALYTICS_AVAILABLE_ROUTES_CRON: str = pydantic.Field(
        default="0 */2 * * *",
        description="Available routes update cron schedule",
    )

    ANALYTICS_BOTTLENECK_METRICS_CRON: str = pydantic.Field(
        default="30 * * * *",
        description="Bottleneck metrics aggregation cron schedule (runs at 30 minutes past each hour)",
    )

    ANALYTICS_LOG_VOLUME_1H_ROLLUP_CRON: str = pydantic.Field(
        default="*/10 * * * *",
        description="log_volume_1h rollup cron schedule (aligned to log_volume_5m source freq)",
    )

    ANALYTICS_LOG_VOLUME_1D_ROLLUP_CRON: str = pydantic.Field(
        default="5 * * * *",
        description="log_volume_1d rollup cron schedule (staggered off the hour boundary)",
    )

    ANALYTICS_PARTITION_MANAGER_CRON: str = pydantic.Field(
        default="10 * * * *",
        description="Partition manager cron schedule (staggered off the hour boundary)",
    )

    ANALYTICS_SPAN_LATENCY_1H_CRON: str = pydantic.Field(
        default="*/5 * * * *",
        description="span_latency_1h rollup cron schedule",
    )

    ANALYTICS_METRIC_POINTS_1H_ROLLUP_CRON: str = pydantic.Field(
        default="*/10 * * * *",
        description="metric_points_1h rollup cron schedule",
    )

    ANALYTICS_ALERT_EVALUATOR_CRON: str = pydantic.Field(
        default="*/1 * * * *",
        description="Alert rule evaluator cron schedule",
    )

    ANALYTICS_MONITOR_CHECK_CRON: str = pydantic.Field(
        default="*/1 * * * *",
        description="Uptime/heartbeat monitor checker cron schedule",
    )

    ANALYTICS_ERROR_REGRESSION_CRON: str = pydantic.Field(
        default="*/5 * * * *",
        description="Error group regression detector cron schedule",
    )

    ALERT_WEBHOOK_ALLOW_HTTP: bool = pydantic.Field(
        default=False,
        description="Allow plain-http webhook URLs (dev/testing only; https required otherwise)",
    )

    ANALYTICS_NOTIFICATION_CLEANUP_CRON: str = pydantic.Field(
        default="0 3 * * *",
        description="Expired notification cleanup cron schedule (daily at 03:00)",
    )

    ANALYTICS_RETENTION_CRON: str = pydantic.Field(
        default="0 3 * * *",
        description="Data retention enforcement cron schedule (daily at 03:00)",
    )

    ANALYTICS_MAX_SERIES_PER_PROJECT: typing.ClassVar[int] = 500
    ANALYTICS_ERROR_RATE_TTL: typing.ClassVar[int] = 600
    ANALYTICS_LOG_VOLUME_TTL: typing.ClassVar[int] = 600
    ANALYTICS_TOP_ERRORS_TTL: typing.ClassVar[int] = 900
    ANALYTICS_TOP_ERRORS_LIMIT: typing.ClassVar[int] = 50
    ANALYTICS_USAGE_STATS_TTL: typing.ClassVar[int] = 3600
    DEFAULT_DAILY_QUOTA: typing.ClassVar[int] = 100_000
    ANALYTICS_JOB_MISFIRE_GRACE_TIME: typing.ClassVar[int] = 60
    ANALYTICS_QUERY_TIMEOUT: typing.ClassVar[int] = 60

    LOG_LEVEL: typing.Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = pydantic.Field(
        default="INFO",
        description="Logging level",
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
