import asyncio
import os

import auth_service.config as config
import auth_service.database as database
import sqlalchemy
import sqlalchemy.ext.asyncio as sa_async
import sqlalchemy.pool as sa_pool

TEST_DB_HOST = os.getenv("TEST_DB_HOST", "localhost")
TEST_DB_NAME = "test_auth_db"
TEST_DB_URL = (
    f"postgresql+asyncpg://{config.settings.AUTH_DB_USER}:{config.settings.AUTH_DB_PASSWORD}"
    f"@{TEST_DB_HOST}:{config.settings.AUTH_DB_PORT}/{TEST_DB_NAME}"
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
            connect_args={"server_settings": {"application_name": "auth_test"}},
        )
        self.session_factory = sa_async.async_sessionmaker(
            self.engine,
            class_=sa_async.AsyncSession,
            expire_on_commit=False,
        )

    async def create_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)
        print("Tables created")

    async def drop_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.drop_all)
        print("Tables dropped")

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


async def setup_test_database():
    db = await get_test_db()
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
