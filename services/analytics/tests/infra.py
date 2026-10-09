"""Where this suite's disposable Postgres servers live (Redis is mocked).

The suite drops tables, so addresses come from TEST_* variables (defaults match
the CI service containers) and tables live only in the suite's own test_*
databases.
"""

import dataclasses
import os

import analytics_workers.config as config


@dataclasses.dataclass(frozen=True)
class PostgresServer:
    host: str
    port: str
    user: str
    password: str

    def url(self, database: str, driver: str = "postgresql") -> str:
        return f"{driver}://{self.user}:{self.password}@{self.host}:{self.port}/{database}"


_HOST = os.getenv("TEST_POSTGRES_HOST", "localhost")

AUTH_DB_SERVER = PostgresServer(
    host=_HOST,
    port=os.getenv("TEST_AUTH_DB_PORT", "5432"),
    user=os.getenv("TEST_POSTGRES_USER", config.settings.AUTH_DB_USER),
    password=os.getenv("TEST_POSTGRES_PASSWORD", config.settings.AUTH_DB_PASSWORD),
)
LOGS_DB_SERVER = PostgresServer(
    host=_HOST,
    port=os.getenv("TEST_LOGS_DB_PORT", "5433"),
    user=os.getenv("TEST_POSTGRES_USER", config.settings.LOGS_DB_USER),
    password=os.getenv("TEST_POSTGRES_PASSWORD", config.settings.LOGS_DB_PASSWORD),
)


def require_test_database_name(name: str) -> str:
    if not name.startswith("test_"):
        raise ValueError(f"Refusing to use database {name!r}: test databases must start 'test_'")
    return name
