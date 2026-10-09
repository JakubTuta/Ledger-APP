import asyncio
import pathlib
import sys

import asyncpg
import sqlalchemy
import sqlalchemy.ext.asyncio as sa_async
import sqlalchemy.pool as sa_pool

import tests.infra as infra

# analytics_workers owns no ORM models of its own (every job is raw SQL
# against tables owned by auth_service and ingestion_service - see
# database.py's get_auth_session()/get_logs_session()). Reusing those
# services' real Base.metadata for test table creation (rather than
# hand-duplicating DDL here) keeps this harness from drifting out of sync
# with their migrations. This is a test-only sys.path trick - it does not
# touch production imports, Docker build contexts, or the "light dedupe
# only" decision (no shared runtime package).
_SERVICES_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _service in ("auth", "ingestion"):
    _path = str(_SERVICES_ROOT / _service)
    if _path not in sys.path:
        sys.path.insert(0, _path)

import auth_service.database as auth_db_module  # noqa: E402
import auth_service.models  # noqa: E402,F401
import ingestion_service.database as logs_db_module  # noqa: E402
import ingestion_service.models  # noqa: E402,F401

TEST_AUTH_DB_NAME = infra.require_test_database_name("test_auth_db")
TEST_LOGS_DB_NAME = infra.require_test_database_name("test_logs_db")

# Rollup tables live in logs_db (created by ingestion's migrations), mirrored
# here since analytics has no ORM model for them either.
_LOGS_ROLLUP_DDL = [
    # Every rollup job reads and writes its watermark through get_logs_session(),
    # and init_logs_db.sql puts the table in logs_db - so it belongs here, and
    # has to be truncated here, or a watermark set by one test hides the next
    # test's fixtures from the job under test.
    """
    CREATE TABLE IF NOT EXISTS rollup_job_state (
        job_name    TEXT NOT NULL PRIMARY KEY,
        last_bucket TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS log_volume_5m (
        project_id  BIGINT NOT NULL,
        level       VARCHAR(20) NOT NULL,
        bucket      TIMESTAMPTZ NOT NULL,
        count       BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (project_id, level, bucket)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS log_volume_1h (
        project_id  BIGINT NOT NULL,
        level       VARCHAR(20) NOT NULL,
        bucket      TIMESTAMPTZ NOT NULL,
        count       BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (project_id, level, bucket)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS log_volume_1d (
        project_id  BIGINT NOT NULL,
        level       VARCHAR(20) NOT NULL,
        bucket      DATE NOT NULL,
        count       BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (project_id, level, bucket)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS error_rate_5m (
        project_id  BIGINT NOT NULL,
        bucket      TIMESTAMPTZ NOT NULL,
        errors      BIGINT NOT NULL DEFAULT 0,
        total       BIGINT NOT NULL DEFAULT 0,
        ratio       DOUBLE PRECISION NOT NULL DEFAULT 0,
        PRIMARY KEY (project_id, bucket)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS span_latency_1h (
        project_id   BIGINT NOT NULL,
        service_name TEXT NOT NULL,
        name         TEXT NOT NULL,
        bucket       TIMESTAMPTZ NOT NULL,
        calls        BIGINT NOT NULL DEFAULT 0,
        p50_ns       BIGINT,
        p95_ns       BIGINT,
        p99_ns       BIGINT,
        errors       BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (project_id, service_name, name, bucket)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS metric_points_1h (
        project_id   BIGINT NOT NULL,
        name         TEXT NOT NULL,
        type         SMALLINT NOT NULL,
        tags_hash    CHAR(16) NOT NULL,
        tags         JSONB NOT NULL DEFAULT '{}'::jsonb,
        bucket       TIMESTAMPTZ NOT NULL,
        count        BIGINT NOT NULL DEFAULT 0,
        sum_v        DOUBLE PRECISION NOT NULL DEFAULT 0,
        min_v        DOUBLE PRECISION,
        max_v        DOUBLE PRECISION,
        avg_v        DOUBLE PRECISION,
        temporality  SMALLINT,
        PRIMARY KEY (project_id, name, tags_hash, bucket)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS service_edges_1h (
        project_id      BIGINT NOT NULL,
        bucket          TIMESTAMPTZ NOT NULL,
        caller          TEXT NOT NULL,
        callee          TEXT NOT NULL,
        calls           BIGINT NOT NULL,
        errors          BIGINT NOT NULL,
        duration_ns_sum BIGINT NOT NULL,
        p95_ns          BIGINT,
        PRIMARY KEY (project_id, bucket, caller, callee)
    )
    """,
]


class _TestDatabase:
    def __init__(self, url: str):
        self.url = url
        self.engine: sa_async.AsyncEngine | None = None
        self.session_factory: sa_async.async_sessionmaker | None = None

    async def create_engine(self) -> None:
        self.engine = sa_async.create_async_engine(
            self.url,
            echo=False,
            poolclass=sa_pool.NullPool,
        )
        self.session_factory = sa_async.async_sessionmaker(
            self.engine, class_=sa_async.AsyncSession, expire_on_commit=False
        )

    async def close(self) -> None:
        if self.engine:
            await self.engine.dispose()


class AnalyticsTestDatabases:
    def __init__(self):
        self.auth = _TestDatabase(
            infra.AUTH_DB_SERVER.url(TEST_AUTH_DB_NAME, driver="postgresql+asyncpg")
        )
        self.logs = _TestDatabase(
            infra.LOGS_DB_SERVER.url(TEST_LOGS_DB_NAME, driver="postgresql+asyncpg")
        )

    async def create_engines(self) -> None:
        await self.auth.create_engine()
        await self.logs.create_engine()

    async def create_tables(self) -> None:
        async with self.auth.engine.begin() as conn:

            def create_auth(conn_sync):
                auth_db_module.Base.metadata.create_all(conn_sync)
                # auth_service.models declares created_at with a Python-side
                # default= (applied by the ORM, not raw SQL); production
                # tables get NOW() via the migration's server_default
                # instead, which create_all() does not reproduce. Analytics
                # jobs insert into notifications via raw SQL, so mirror that
                # server_default here.
                conn_sync.execute(
                    sqlalchemy.text(
                        "ALTER TABLE notifications ALTER COLUMN created_at SET DEFAULT NOW()"
                    )
                )

            await conn.run_sync(create_auth)

        async with self.logs.engine.begin() as conn:

            def create_logs(conn_sync):
                logs_db_module.Base.metadata.create_all(conn_sync)
                for ddl in _LOGS_ROLLUP_DDL:
                    conn_sync.execute(sqlalchemy.text(ddl))
                try:
                    conn_sync.execute(
                        sqlalchemy.text("""
                            CREATE TABLE IF NOT EXISTS logs_test_partition PARTITION OF logs
                            FOR VALUES FROM ('2020-01-01') TO ('2030-12-31');
                        """)
                    )
                except Exception as e:
                    print(f"Note: logs partition may already exist: {e}")
                try:
                    conn_sync.execute(
                        sqlalchemy.text("""
                            CREATE TABLE IF NOT EXISTS spans_test_partition PARTITION OF spans
                            FOR VALUES FROM ('2020-01-01') TO ('2030-12-31');
                        """)
                    )
                except Exception as e:
                    print(f"Note: spans partition may already exist: {e}")
                try:
                    conn_sync.execute(
                        sqlalchemy.text("""
                            CREATE TABLE IF NOT EXISTS metric_points_test_partition
                            PARTITION OF metric_points
                            FOR VALUES FROM ('2020-01-01') TO ('2030-12-31');
                        """)
                    )
                except Exception as e:
                    print(f"Note: metric_points partition may already exist: {e}")

            await conn.run_sync(create_logs)

        print("Analytics test tables created (auth_db + logs_db)")

    async def drop_tables(self) -> None:
        async with self.auth.engine.begin() as conn:

            def drop_auth(conn_sync):
                auth_db_module.Base.metadata.drop_all(conn_sync)

            await conn.run_sync(drop_auth)

        async with self.logs.engine.begin() as conn:

            def drop_logs(conn_sync):
                for table in (
                    "rollup_job_state",
                    "service_edges_1h",
                    "metric_points_1h",
                    "span_latency_1h",
                    "error_rate_5m",
                    "log_volume_1d",
                    "log_volume_1h",
                    "log_volume_5m",
                ):
                    conn_sync.execute(sqlalchemy.text(f"DROP TABLE IF EXISTS {table}"))
                logs_db_module.Base.metadata.drop_all(conn_sync)

            await conn.run_sync(drop_logs)

        print("Analytics test tables dropped")

    async def clear_tables(self) -> None:
        async with self.auth.engine.begin() as conn:
            table_names = [t.name for t in reversed(auth_db_module.Base.metadata.sorted_tables)]
            await conn.execute(
                sqlalchemy.text(f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE")
            )

        async with self.logs.engine.begin() as conn:
            table_names = [t.name for t in reversed(logs_db_module.Base.metadata.sorted_tables)]
            table_names += [
                "rollup_job_state",
                "log_volume_5m",
                "log_volume_1h",
                "log_volume_1d",
                "error_rate_5m",
                "span_latency_1h",
                "metric_points_1h",
                "service_edges_1h",
            ]
            await conn.execute(
                sqlalchemy.text(f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE")
            )

    async def close(self) -> None:
        await self.auth.close()
        await self.logs.close()


_test_dbs: AnalyticsTestDatabases | None = None


async def get_test_dbs() -> AnalyticsTestDatabases:
    global _test_dbs
    if _test_dbs is None:
        _test_dbs = AnalyticsTestDatabases()
        await _test_dbs.create_engines()
    return _test_dbs


async def _ensure_database_exists(server: infra.PostgresServer, db_name: str) -> None:
    conn = await asyncpg.connect(server.url("postgres"))
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            print(f"Created test database: {db_name}")
        else:
            print(f"Test database already exists: {db_name}")
    finally:
        await conn.close()


async def setup_test_databases() -> None:
    await _ensure_database_exists(infra.AUTH_DB_SERVER, TEST_AUTH_DB_NAME)
    await _ensure_database_exists(infra.LOGS_DB_SERVER, TEST_LOGS_DB_NAME)
    dbs = await get_test_dbs()
    try:
        await dbs.create_tables()
    except Exception as e:
        print(f"Error creating tables: {e}")
        await dbs.create_tables()


async def teardown_test_databases() -> None:
    global _test_dbs
    if _test_dbs:
        await _test_dbs.drop_tables()
        await _test_dbs.close()
        _test_dbs = None


async def clear_test_databases() -> None:
    dbs = await get_test_dbs()
    await dbs.clear_tables()


if __name__ == "__main__":

    async def _self_test():
        print("Creating tables...")
        await setup_test_databases()
        print("Clearing tables...")
        await clear_test_databases()
        print("Dropping tables...")
        await teardown_test_databases()
        print("Database setup works!")

    asyncio.run(_self_test())
