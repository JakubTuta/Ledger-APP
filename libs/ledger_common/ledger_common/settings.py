"""Settings every Ledger service reads the same way.

A service builds its `Settings` from `ServiceSettings` plus the mixins it needs, so a variable
that several services read (Redis, the two databases, SMTP, JWT, ...) is declared once and its
name, default and URL builder cannot drift between services:

    class Settings(RedisSettings, AuthDatabaseSettings, ServiceSettings):
        AUTH_GRPC_PORT: typing.ClassVar[int] = 50051

Keep `ServiceSettings` last: that puts its fields (ENV in particular) first, which validators
that read other fields rely on.

Per-service tuning that is a *budget* rather than a shared fact (connection pool sizes,
REDIS_MAX_CONNECTIONS) deliberately stays in each service's config.
"""

import os
import typing

import pydantic
import pydantic_settings

_INSECURE_JWT_SECRET = "your-secret-key-change-this-in-production"


class ServiceSettings(pydantic_settings.BaseSettings):
    """Base of every service's Settings: .env loading plus the always-present fields."""

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

    DEBUG: bool = pydantic.Field(
        default=False,
        description="Enable debug mode",
    )

    SELF_MONITORING_API_KEY: str = pydantic.Field(
        default="",
        description="API key of the project Ledger reports its own telemetry to; empty disables it",
    )

    SELF_MONITORING_URL: str = pydantic.Field(
        default="http://ledger-gateway:8000",
        description="Gateway the services export their own telemetry to",
    )

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.ENV.lower() == "development"


class RedisSettings(pydantic.BaseModel):
    REDIS_HOST: str = pydantic.Field(default="localhost", description="Redis host")
    REDIS_PORT: int = pydantic.Field(default=6379, description="Redis port")
    REDIS_PASSWORD: str | None = pydantic.Field(default=None, description="Redis password")
    REDIS_DB: typing.ClassVar[int] = 0

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


class AuthDatabaseSettings(pydantic.BaseModel):
    AUTH_DB_HOST: str = pydantic.Field(default="localhost", description="Auth database host")
    AUTH_DB_PORT: int = pydantic.Field(default=5432, description="Auth database port")
    AUTH_DB_NAME: str = pydantic.Field(default="auth_db", description="Auth database name")
    AUTH_DB_USER: str = pydantic.Field(default="postgres", description="Auth database user")
    AUTH_DB_PASSWORD: str = pydantic.Field(default="postgres", description="Auth database password")

    @property
    def AUTH_DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.AUTH_DB_USER}:{self.AUTH_DB_PASSWORD}"
            f"@{self.AUTH_DB_HOST}:{self.AUTH_DB_PORT}/{self.AUTH_DB_NAME}"
        )


class LogsDatabaseSettings(pydantic.BaseModel):
    LOGS_DB_HOST: str = pydantic.Field(default="localhost", description="Logs database host")
    LOGS_DB_PORT: int = pydantic.Field(default=5433, description="Logs database port")
    LOGS_DB_NAME: str = pydantic.Field(default="logs_db", description="Logs database name")
    LOGS_DB_USER: str = pydantic.Field(default="postgres", description="Logs database user")
    LOGS_DB_PASSWORD: str = pydantic.Field(default="postgres", description="Logs database password")

    @property
    def LOGS_DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.LOGS_DB_USER}:{self.LOGS_DB_PASSWORD}"
            f"@{self.LOGS_DB_HOST}:{self.LOGS_DB_PORT}/{self.LOGS_DB_NAME}"
        )


class GrpcKeepaliveSettings(pydantic.BaseModel):
    """Client-side keepalive; constants because nobody tunes them per deployment."""

    GRPC_KEEPALIVE_TIME_MS: typing.ClassVar[int] = 300000
    GRPC_KEEPALIVE_TIMEOUT_MS: typing.ClassVar[int] = 20000


class GrpcServerSettings(GrpcKeepaliveSettings):
    GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS: typing.ClassVar[int] = 1
    GRPC_MAX_CONNECTION_IDLE_MS: typing.ClassVar[int] = 3600000
    GRPC_MAX_CONNECTION_AGE_MS: typing.ClassVar[int] = 86400000
    GRPC_HTTP2_MIN_RECV_PING_INTERVAL_WITHOUT_DATA_MS: typing.ClassVar[int] = 120000


class SmtpSettings(pydantic.BaseModel):
    EMAIL_ENABLED: bool = pydantic.Field(
        default=False, description="Enable outbound email (verification and alert delivery)"
    )
    SMTP_HOST: str = pydantic.Field(default="smtp.gmail.com", description="SMTP server host")
    SMTP_PORT: int = pydantic.Field(
        default=465, description="SMTP server port (465 = implicit TLS, 587 = STARTTLS)"
    )
    SMTP_USER: str = pydantic.Field(default="", description="SMTP username")
    SMTP_PASSWORD: str = pydantic.Field(
        default="", description="SMTP password (app password, not account password)"
    )
    SMTP_FROM: str = pydantic.Field(
        default="", description="From address; falls back to SMTP_USER when empty"
    )
    SMTP_USE_TLS: typing.ClassVar[bool] = True


class DailyQuotaDefaults(pydantic.BaseModel):
    DEFAULT_LOGS_DAILY_QUOTA: typing.ClassVar[int] = 100_000
    DEFAULT_SPANS_DAILY_QUOTA: typing.ClassVar[int] = 300_000
    DEFAULT_METRICS_DAILY_QUOTA: typing.ClassVar[int] = 100_000


class JwtSettings(pydantic.BaseModel):
    JWT_SECRET: str = pydantic.Field(
        default=_INSECURE_JWT_SECRET,
        min_length=32,
        description="JWT signing secret (min 32 chars)",
    )
    # The gateway sets the refresh cookie's max-age from this, so it must equal the lifetime the
    # auth service gives a refresh token - one constant for both.
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: typing.ClassVar[int] = 7

    @pydantic.model_validator(mode="after")
    def _require_real_jwt_secret_in_production(self) -> typing.Self:
        if getattr(self, "ENV", None) == "production" and self.JWT_SECRET == _INSECURE_JWT_SECRET:
            raise ValueError("Must set JWT_SECRET in production!")
        return self


class ConnectorSecretsSettings(pydantic.BaseModel):
    CONNECTOR_SECRETS_KEY: str = pydantic.Field(
        default="",
        description=(
            "Comma-separated Fernet keys encrypting connector credentials at rest; the first "
            "encrypts, all decrypt (rotation). Auth and analytics must share the value."
        ),
    )
