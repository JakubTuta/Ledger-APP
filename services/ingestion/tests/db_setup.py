import asyncio
import os

import asyncpg
import ingestion_service.config as config
import ingestion_service.database as database
import sqlalchemy
import sqlalchemy.ext.asyncio as sa_async
import sqlalchemy.pool as sa_pool

TEST_DB_HOST = "localhost"
TEST_DB_PORT = "5433"
TEST_DB_NAME = "test_logs_db"
TEST_DB_URL = (
    f"postgresql+asyncpg://{config.settings.LOGS_DB_USER}:{config.settings.LOGS_DB_PASSWORD}"
    f"@{TEST_DB_HOST}:{TEST_DB_PORT}/{TEST_DB_NAME}"
)

POSTGRES_URL = (
    f"postgresql://{config.settings.LOGS_DB_USER}:{config.settings.LOGS_DB_PASSWORD}"
    f"@{TEST_DB_HOST}:{TEST_DB_PORT}/postgres"
)


class TestDatabase:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def create_engine(self):
        self.engine = sa_async.create_async_engine(
            TEST_DB_URL,
            echo=False,
            poolclass=sa_pool.NullPool,
            connect_args={"server_settings": {"application_name": "ingestion_test"}},
        )
        self.session_factory = sa_async.async_sessionmaker(
            self.engine,
            class_=sa_async.AsyncSession,
            expire_on_commit=False,
        )

    async def create_tables(self):
        async with self.engine.begin() as conn:
            def create_all_and_partitions(conn_sync):
                database.Base.metadata.create_all(conn_sync)

                try:
                    conn_sync.execute(
                        sqlalchemy.text("""
                            CREATE TABLE IF NOT EXISTS logs_test_partition PARTITION OF logs
                            FOR VALUES FROM ('2020-01-01') TO ('2030-12-31');
                        """)
                    )
                    conn_sync.execute(
                        sqlalchemy.text("""
                            CREATE TABLE IF NOT EXISTS ingestion_metrics_test_partition PARTITION OF ingestion_metrics
                            FOR VALUES FROM ('2020-01-01') TO ('2030-12-31');
                        """)
                    )
                except Exception as e:
                    print(f"Note: Partitions may already exist: {e}")

            await conn.run_sync(create_all_and_partitions)

        print("Logs tables created with test partitions")

    async def drop_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.drop_all)
        print("Logs tables dropped")

    async def clear_tables(self):
        if not self.engine:
            return
        async with self.engine.begin() as conn:
            table_names = [t.name for t in reversed(database.Base.metadata.sorted_tables)]
            if table_names:
                await conn.execute(
                    sqlalchemy.text(f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE")
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
    """Create test database if it doesn't exist."""
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
