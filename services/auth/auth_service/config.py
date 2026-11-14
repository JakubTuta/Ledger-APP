import functools
import typing

import ledger_common.settings


class Settings(
    ledger_common.settings.RedisSettings,
    ledger_common.settings.AuthDatabaseSettings,
    ledger_common.settings.GrpcServerSettings,
    ledger_common.settings.DailyQuotaDefaults,
    ledger_common.settings.JwtSettings,
    ledger_common.settings.ConnectorSecretsSettings,
    ledger_common.settings.ServiceSettings,
):
    """
    Application settings with validation.

    Loads from:
    1. Environment variables
    2. .env file
    3. Default values
    """

    # gRPC server port + keepalive/HTTP2 tuning: not expected to change
    # per-deployment, so these are constants rather than env-overridable.

    AUTH_GRPC_PORT: typing.ClassVar[int] = 50051

    # Auth DB budget (max_connections=30 in docker-compose.prod.yaml): auth
    # service 15 + analytics 6, leaving room for migrations and admin sessions.
    DB_POOL_SIZE: typing.ClassVar[int] = 10
    DB_MAX_OVERFLOW: typing.ClassVar[int] = 5

    REDIS_MAX_CONNECTIONS: typing.ClassVar[int] = 20

    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: typing.ClassVar[int] = 15
    BCRYPT_ROUNDS: typing.ClassVar[int] = 12

    DEFAULT_RATE_LIMIT_PER_MINUTE: typing.ClassVar[int] = 1000
    DEFAULT_RATE_LIMIT_PER_HOUR: typing.ClassVar[int] = 20_000

    DASHBOARD_CACHE_TTL: typing.ClassVar[int] = 300


@functools.lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses LRU cache to avoid re-parsing environment on every call.
    """
    return Settings()


settings = get_settings()
