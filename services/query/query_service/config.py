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
        description="Logs database password (override in .env for production)",
    )

    DB_POOL_SIZE: typing.ClassVar[int] = 30
    DB_MAX_OVERFLOW: typing.ClassVar[int] = 20

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
        description="Redis password (optional)",
    )

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    MAX_QUERY_LIMIT: typing.ClassVar[int] = 1000
    DEFAULT_QUERY_LIMIT: typing.ClassVar[int] = 100
    MAX_SEARCH_RESULTS: typing.ClassVar[int] = 10000
    QUERY_HOST: typing.ClassVar[str] = "0.0.0.0"
    QUERY_GRPC_PORT: typing.ClassVar[int] = 50053
    GRPC_MAX_WORKERS: typing.ClassVar[int] = 10
    GRPC_KEEPALIVE_TIME_MS: typing.ClassVar[int] = 300000
    GRPC_KEEPALIVE_TIMEOUT_MS: typing.ClassVar[int] = 20000
    GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS: typing.ClassVar[int] = 1
    GRPC_MAX_CONNECTION_IDLE_MS: typing.ClassVar[int] = 3600000
    GRPC_MAX_CONNECTION_AGE_MS: typing.ClassVar[int] = 86400000
    GRPC_HTTP2_MIN_RECV_PING_INTERVAL_WITHOUT_DATA_MS: typing.ClassVar[int] = 120000

    LOG_LEVEL: typing.Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = pydantic.Field(
        default="INFO",
        description="Logging level",
    )


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
