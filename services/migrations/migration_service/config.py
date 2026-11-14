import functools
import typing

import ledger_common.settings


class Settings(
    ledger_common.settings.AuthDatabaseSettings,
    ledger_common.settings.LogsDatabaseSettings,
    ledger_common.settings.ServiceSettings,
):
    # The runner blocks until every target database accepts connections. Compose
    # already gates on pg_isready, but a healthy Postgres can still refuse the
    # first connections while it finishes its own recovery/init pass.
    DB_CONNECT_TIMEOUT_SECONDS: typing.ClassVar[int] = 60
    DB_CONNECT_RETRY_INTERVAL_SECONDS: typing.ClassVar[float] = 2.0


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
