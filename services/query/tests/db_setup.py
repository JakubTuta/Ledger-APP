import asyncio

import asyncpg
import ledger_common.models.logs as models
import sqlalchemy
import sqlalchemy.ext.asyncio as sa_async
import sqlalchemy.pool as sa_pool

import tests.infra as infra

TEST_DB_NAME = infra.require_test_database_name("test_logs_db")
_SERVER = (
    f"{infra.POSTGRES_USER}:{infra.POSTGRES_PASSWORD}@{infra.POSTGRES_HOST}:{infra.POSTGRES_PORT}"
)
TEST_DB_URL = f"postgresql+asyncpg://{_SERVER}/{TEST_DB_NAME}"
POSTGRES_URL = f"postgresql://{_SERVER}/postgres"


class TestDatabase:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def create_engine(self):
        self.engine = sa_async.create_async_engine(
            TEST_DB_URL,
            echo=False,
            poolclass=sa_pool.NullPool,
            connect_args={"server_settings": {"application_name": "query_test"}},
        )
        self.session_factory = sa_async.async_sessionmaker(
            self.engine,
            class_=sa_async.AsyncSession,
            expire_on_commit=False,
        )

    async def create_tables(self):
        async with self.engine.begin() as conn:

            def create_all_and_partitions(conn_sync):
                models.Base.metadata.create_all(conn_sync)

                # The rollup tables have no ORM model (analytics writes them with raw SQL), so
                # they are mirrored here; the partitioned base tables come from the shared models.
                conn_sync.execute(
                    sqlalchemy.text("""
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
                    """)
                )

                conn_sync.execute(
                    sqlalchemy.text("""
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
                    """)
                )

                conn_sync.execute(
                    sqlalchemy.text("""
                        CREATE TABLE IF NOT EXISTS spans_test_partition PARTITION OF spans
                        FOR VALUES FROM ('2020-01-01') TO ('2030-12-31')
                    """)
                )

                try:
                    conn_sync.execute(
                        sqlalchemy.text("""
                            CREATE TABLE IF NOT EXISTS logs_test_partition PARTITION OF logs
                            FOR VALUES FROM ('2020-01-01') TO ('2030-12-31');
                        """)
                    )
                except Exception as e:
                    print(f"Note: Partitions may already exist: {e}")

                try:
                    conn_sync.execute(
                        sqlalchemy.text("""
                            CREATE TABLE IF NOT EXISTS metric_points_test_partition
                            PARTITION OF metric_points
                            FOR VALUES FROM ('2020-01-01') TO ('2030-12-31');
                        """)
                    )
                except Exception as e:
                    print(f"Note: Partitions may already exist: {e}")

            await conn.run_sync(create_all_and_partitions)

        print("Query service test tables created with partitions")

    async def drop_tables(self):
        async with self.engine.begin() as conn:

            def drop_all(conn_sync):
                conn_sync.execute(sqlalchemy.text("DROP TABLE IF EXISTS metric_points_1h"))
                conn_sync.execute(sqlalchemy.text("DROP TABLE IF EXISTS service_edges_1h"))
                models.Base.metadata.drop_all(conn_sync)

            await conn.run_sync(drop_all)
        print("Query service test tables dropped")

    async def clear_tables(self):
        if not self.engine:
            return
        async with self.engine.begin() as conn:
            table_names = [t.name for t in reversed(models.Base.metadata.sorted_tables)]
            table_names += ["metric_points_1h", "metric_points", "spans", "service_edges_1h"]
            if table_names:
                await conn.execute(
                    sqlalchemy.text(
                        f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE"
                    )
                )

    async def close(self):
        if self.engine:
            await self.engine.dispose()


_test_db = None


async def get_test_db():
    global _test_db
    if _test_db is None:
        _test_db = TestDatabase()
        await _test_db.create_engine()
    return _test_db


async def ensure_test_database_exists():
    try:
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
                print(f"Created test database: {TEST_DB_NAME}")
            else:
                print(f"Test database already exists: {TEST_DB_NAME}")
        finally:
            await conn.close()
    except Exception as e:
        print(f"Error ensuring test database exists: {e}")
        raise


async def setup_test_database():
    await ensure_test_database_exists()
    db = await get_test_db()
    try:
        await db.create_tables()
    except Exception as e:
        print(f"Error creating tables: {e}")
        await db.create_tables()


async def teardown_test_database():
    global _test_db
    if _test_db:
        await _test_db.drop_tables()
        await _test_db.close()
        _test_db = None


async def clear_test_database():
    db = await get_test_db()
    await db.clear_tables()


if __name__ == "__main__":

    async def test():
        print("Creating tables...")
        await setup_test_database()
        print("Clearing tables...")
        await clear_test_database()
        print("Dropping tables...")
        await teardown_test_database()
        print("Database setup works!")

    asyncio.run(test())
