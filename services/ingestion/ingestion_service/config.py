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

    INGESTION_HOST: typing.ClassVar[str] = "0.0.0.0"
    INGESTION_GRPC_PORT: typing.ClassVar[int] = 50052
    GRPC_KEEPALIVE_TIME_MS: typing.ClassVar[int] = 300000
    GRPC_KEEPALIVE_TIMEOUT_MS: typing.ClassVar[int] = 20000
    GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS: typing.ClassVar[int] = 1
    GRPC_MAX_CONNECTION_IDLE_MS: typing.ClassVar[int] = 3600000
    GRPC_MAX_CONNECTION_AGE_MS: typing.ClassVar[int] = 86400000
    GRPC_HTTP2_MIN_RECV_PING_INTERVAL_WITHOUT_DATA_MS: typing.ClassVar[int] = 120000

    LOGS_DB_HOST: str = pydantic.Field(
        default="localhost",
        description="Logs database host",
    )

    LOGS_DB_PORT: int = pydantic.Field(
        default=5433,
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

    DB_POOL_SIZE: typing.ClassVar[int] = 20
    DB_MAX_OVERFLOW: typing.ClassVar[int] = 10

    @property
    def LOGS_DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.LOGS_DB_USER}:{self.LOGS_DB_PASSWORD}"
            f"@{self.LOGS_DB_HOST}:{self.LOGS_DB_PORT}/{self.LOGS_DB_NAME}"
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
    REDIS_MAX_CONNECTIONS: typing.ClassVar[int] = 50

    REDIS_PASSWORD: str | None = pydantic.Field(
        default=None,
        description="Redis password",
    )

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    QUEUE_MAX_DEPTH: typing.ClassVar[int] = 100_000
    QUEUE_WORKER_TIMEOUT: typing.ClassVar[int] = 30
    QUEUE_BATCH_SIZE: typing.ClassVar[int] = 1000
    WORKER_COUNT: typing.ClassVar[int] = 5
    WORKER_SPANS_COUNT: typing.ClassVar[int] = 2
    WORKER_METRICS_COUNT: typing.ClassVar[int] = 2

    PARTITION_MONTHS_AHEAD: typing.ClassVar[int] = 6
    PARTITION_CREATE_CRON: typing.ClassVar[str] = "0 0 1 * *"
    PARTITION_CHECK_CRON: typing.ClassVar[str] = "30 0 * * *"
    PARTITION_MISFIRE_GRACE_TIME: typing.ClassVar[int] = 3600

    ENABLE_PARTITION_SCHEDULER: bool = pydantic.Field(
        default=True,
        description="Enable automatic partition creation scheduler",
    )

    MAX_LOG_MESSAGE_LENGTH: typing.ClassVar[int] = 10_000
    MAX_ERROR_MESSAGE_LENGTH: typing.ClassVar[int] = 5_000
    MAX_STACK_TRACE_LENGTH: typing.ClassVar[int] = 50_000
    MAX_ATTRIBUTES_SIZE: typing.ClassVar[int] = 100_000
    MAX_BATCH_LOGS: typing.ClassVar[int] = 1000
    MAX_REQUEST_SIZE_MB: typing.ClassVar[int] = 5
    TIMESTAMP_FUTURE_TOLERANCE_MINUTES: typing.ClassVar[int] = 5

    REDIS_TIMEOUT: typing.ClassVar[float] = 1.0

    RABBITMQ_HOST: str = pydantic.Field(
        default="localhost",
        description="RabbitMQ host",
    )

    RABBITMQ_PORT: int = pydantic.Field(
        default=5672,
        description="RabbitMQ AMQP port",
    )

    RABBITMQ_USER: str = pydantic.Field(
        default="ledger",
        description="RabbitMQ username",
    )

    RABBITMQ_PASSWORD: str = pydantic.Field(
        default="ledger",
        description="RabbitMQ password",
    )

    RABBITMQ_VHOST: typing.ClassVar[str] = "/"
    RABBITMQ_EXCHANGE: typing.ClassVar[str] = "logs"
    RABBITMQ_QUEUE: typing.ClassVar[str] = "ingestion.logs"
    RABBITMQ_SPANS_QUEUE: typing.ClassVar[str] = "ingestion.spans"
    RABBITMQ_METRICS_QUEUE: typing.ClassVar[str] = "ingestion.metrics"
    RABBITMQ_CHANNEL_POOL_SIZE: typing.ClassVar[int] = 10
    RABBITMQ_PREFETCH_COUNT: typing.ClassVar[int] = 1000
    BATCH_FLUSH_INTERVAL: typing.ClassVar[float] = 1.0
    RABBITMQ_ENVELOPE_MAX_LOGS: typing.ClassVar[int] = 200
    RABBITMQ_ENVELOPE_MAX_SPANS: typing.ClassVar[int] = 200
    RABBITMQ_ENVELOPE_MAX_METRICS: typing.ClassVar[int] = 200

    @property
    def RABBITMQ_URL(self) -> str:
        import urllib.parse

        password = urllib.parse.quote(self.RABBITMQ_PASSWORD, safe="")
        vhost = urllib.parse.quote(self.RABBITMQ_VHOST, safe="")
        return f"amqp://{self.RABBITMQ_USER}:{password}@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/{vhost}"

    REQUEST_TIMEOUT: typing.ClassVar[float] = 30.0

    NOTIFICATIONS_ENABLED: bool = pydantic.Field(
        default=True,
        description="Enable real-time error notifications via Redis Pub/Sub",
    )

    NOTIFICATIONS_PUBLISH_ERRORS: typing.ClassVar[bool] = True
    NOTIFICATIONS_PUBLISH_CRITICAL: typing.ClassVar[bool] = True

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
