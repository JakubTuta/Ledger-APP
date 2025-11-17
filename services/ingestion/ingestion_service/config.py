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

    LOG_LEVEL: typing.Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = (
        pydantic.Field(
            default="INFO",
            description="Logging level",
        )
    )

    INGESTION_HOST: str = pydantic.Field(
        default="0.0.0.0",
        description="Ingestion service gRPC host",
    )

    INGESTION_GRPC_PORT: int = pydantic.Field(
        default=50052,
        description="Ingestion service gRPC port",
    )

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

    REDIS_DB: int = pydantic.Field(
        default=1,
        ge=0,
        le=15,
        description="Redis database number (1 for ingestion)",
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

    QUEUE_MAX_DEPTH: int = pydantic.Field(
        default=100_000,
        ge=10_000,
        le=1_000_000,
        description="Maximum queue depth per project before backpressure",
    )

    QUEUE_WORKER_TIMEOUT: int = pydantic.Field(
        default=30,
        ge=5,
        le=300,
        description="BRPOP timeout in seconds",
    )

    QUEUE_BATCH_SIZE: int = pydantic.Field(
        default=1000,
        ge=100,
        le=10_000,
        description="Number of logs to batch before bulk insert",
    )

    WORKER_COUNT: int = pydantic.Field(
        default=5,
        ge=1,
        le=50,
        description="Number of storage workers",
    )

    PARTITION_MONTHS_AHEAD: int = pydantic.Field(
        default=6,
        ge=1,
        le=24,
        description="Number of months ahead to create partitions",
    )

    ENABLE_PARTITION_SCHEDULER: bool = pydantic.Field(
        default=True,
        description="Enable automatic partition creation scheduler",
    )

    MAX_LOG_MESSAGE_LENGTH: int = pydantic.Field(
        default=10_000,
        ge=1_000,
        le=100_000,
        description="Max log message length in characters (10KB)",
    )

    MAX_ERROR_MESSAGE_LENGTH: int = pydantic.Field(
        default=5_000,
        ge=1_000,
        le=50_000,
        description="Max error message length in characters (5KB)",
    )

    MAX_STACK_TRACE_LENGTH: int = pydantic.Field(
        default=50_000,
        ge=10_000,
        le=500_000,
        description="Max stack trace length in characters (50KB)",
    )

    MAX_ATTRIBUTES_SIZE: int = pydantic.Field(
        default=100_000,
        ge=10_000,
        le=1_000_000,
        description="Max attributes JSONB size in bytes (100KB)",
    )

    MAX_BATCH_LOGS: int = pydantic.Field(
        default=1000,
        ge=1,
        le=10_000,
        description="Maximum logs per batch request",
    )

    MAX_REQUEST_SIZE_MB: int = pydantic.Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum request body size in MB",
    )

    TIMESTAMP_FUTURE_TOLERANCE_MINUTES: int = pydantic.Field(
        default=5,
        ge=1,
        le=60,
        description="Clock skew tolerance for future timestamps (minutes)",
    )

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
