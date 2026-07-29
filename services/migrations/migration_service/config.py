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

    LOG_LEVEL: typing.Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = pydantic.Field(
        default="INFO",
        description="Logging level",
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

    # The runner blocks until every target database accepts connections. Compose
    # already gates on pg_isready, but a healthy Postgres can still refuse the
    # first connections while it finishes its own recovery/init pass.
    DB_CONNECT_TIMEOUT_SECONDS: typing.ClassVar[int] = 60
    DB_CONNECT_RETRY_INTERVAL_SECONDS: typing.ClassVar[float] = 2.0

    @property
    def AUTH_DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.AUTH_DB_USER}:{self.AUTH_DB_PASSWORD}"
            f"@{self.AUTH_DB_HOST}:{self.AUTH_DB_PORT}/{self.AUTH_DB_NAME}"
        )

    @property
    def LOGS_DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.LOGS_DB_USER}:{self.LOGS_DB_PASSWORD}"
            f"@{self.LOGS_DB_HOST}:{self.LOGS_DB_PORT}/{self.LOGS_DB_NAME}"
        )


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
