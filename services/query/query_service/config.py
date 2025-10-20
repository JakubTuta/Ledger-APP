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
        default=30,
        ge=5,
        le=100,
        description="Database connection pool size (read-heavy workload)",
    )

    DB_MAX_OVERFLOW: int = pydantic.Field(
        default=20,
        ge=0,
        le=50,
        description="Max overflow connections",
    )

    QUERY_TIMEOUT: int = pydantic.Field(
        default=30,
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
        default=50,
        ge=10,
        le=100,
        description="Redis connection pool size",
    )

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    MAX_QUERY_LIMIT: int = pydantic.Field(
        default=1000,
        ge=1,
        le=10000,
        description="Maximum logs per query",
    )

    DEFAULT_QUERY_LIMIT: int = pydantic.Field(
        default=100,
        ge=1,
        le=1000,
        description="Default logs per query",
    )

    MAX_SEARCH_RESULTS: int = pydantic.Field(
        default=10000,
        ge=100,
        le=100000,
        description="Maximum search results",
    )

    GRPC_SERVER_HOST: str = pydantic.Field(
        default="0.0.0.0",
        description="gRPC server host",
    )

    GRPC_SERVER_PORT: int = pydantic.Field(
        default=50053,
        ge=1024,
        le=65535,
        description="gRPC server port",
    )

    GRPC_MAX_WORKERS: int = pydantic.Field(
        default=10,
        ge=1,
        le=100,
        description="gRPC server max workers",
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
