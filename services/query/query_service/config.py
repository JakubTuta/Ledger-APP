import functools
import typing

import ledger_common.settings


class Settings(
    ledger_common.settings.RedisSettings,
    ledger_common.settings.LogsDatabaseSettings,
    ledger_common.settings.GrpcServerSettings,
    ledger_common.settings.ServiceSettings,
):
    # Share of the logs DB connection budget (see ingestion_service.config).
    # A burst beyond this waits up to DB_POOL_TIMEOUT for a free connection
    # instead of opening more and starving the ingestion worker.
    DB_POOL_SIZE: typing.ClassVar[int] = 6
    DB_MAX_OVERFLOW: typing.ClassVar[int] = 4
    DB_POOL_TIMEOUT: typing.ClassVar[int] = 10
    # The gateway abandons a query RPC after 10 s; without a server-side limit
    # the query itself kept running and holding its connection.
    DB_STATEMENT_TIMEOUT_MS: typing.ClassVar[int] = 15_000

    REDIS_MAX_CONNECTIONS: typing.ClassVar[int] = 20

    MAX_QUERY_LIMIT: typing.ClassVar[int] = 1000
    DEFAULT_QUERY_LIMIT: typing.ClassVar[int] = 100
    MAX_SEARCH_RESULTS: typing.ClassVar[int] = 10000
    QUERY_HOST: typing.ClassVar[str] = "0.0.0.0"
    QUERY_GRPC_PORT: typing.ClassVar[int] = 50053
    GRPC_MAX_WORKERS: typing.ClassVar[int] = 10


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
