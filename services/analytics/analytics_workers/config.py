import functools
import typing

import pydantic
import ledger_common.settings


class Settings(
    ledger_common.settings.RedisSettings,
    ledger_common.settings.AuthDatabaseSettings,
    ledger_common.settings.LogsDatabaseSettings,
    ledger_common.settings.SmtpSettings,
    ledger_common.settings.DailyQuotaDefaults,
    ledger_common.settings.ConnectorSecretsSettings,
    ledger_common.settings.ServiceSettings,
):
    # Per database (one pool each for the logs and auth DBs). Jobs that fire on
    # the same minute queue for a connection rather than opening more; see the
    # connection budget in ingestion_service.config.
    DB_POOL_SIZE: typing.ClassVar[int] = 4
    DB_MAX_OVERFLOW: typing.ClassVar[int] = 2

    REDIS_MAX_CONNECTIONS: typing.ClassVar[int] = 10

    ANALYTICS_LOG_METRICS_CRON: str = pydantic.Field(
        default="*/10 * * * *",
        description="Combined log volume + error rate aggregation cron schedule (minute hour day month day_of_week)",
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

    ANALYTICS_LOG_FACETS_1H_ROLLUP_CRON: str = pydantic.Field(
        default="0 * * * *",
        description="log_facets_1h rollup cron schedule - each run fully recomputes a fixed "
        "trailing window, so this only needs to fire once an hour",
    )

    ANALYTICS_METRIC_POINTS_1H_ROLLUP_CRON: str = pydantic.Field(
        default="*/10 * * * *",
        description="metric_points_1h rollup cron schedule - feeds the downsampled read path "
        "the metric series query falls back to for windows longer than two days",
    )

    ANALYTICS_SERVICE_EDGES_1H_ROLLUP_CRON: str = pydantic.Field(
        default="5-59/10 * * * *",
        description="service_edges_1h rollup cron schedule - feeds service maps for windows "
        "longer than a few hours (staggered off the metric_points_1h rollup)",
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

    ANALYTICS_RIR_REFRESH_CRON: str = pydantic.Field(
        default="0 4 * * 0",
        description=(
            "RIR delegated-extended IP-to-country refresh cron schedule "
            "(weekly, Sunday 04:00 - the source files are only published daily)"
        ),
    )

    ANALYTICS_MAX_SERIES_PER_PROJECT: typing.ClassVar[int] = 500
    ANALYTICS_USAGE_STATS_TTL: typing.ClassVar[int] = 3600
    ANALYTICS_JOB_MISFIRE_GRACE_TIME: typing.ClassVar[int] = 60
    ANALYTICS_QUERY_TIMEOUT: typing.ClassVar[int] = 60

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
