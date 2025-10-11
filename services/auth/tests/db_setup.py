import asyncio

from auth_service.config import settings
from auth_service.database import Base
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_URL = (
    f"postgresql+asyncpg://{settings.AUTH_DB_USER}:{settings.AUTH_DB_PASSWORD}"
    f"@{settings.AUTH_DB_HOST}:{settings.AUTH_DB_PORT}/test_auth_db"
)


class TestDatabase:
    """Simple test database manager."""

    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def create_engine(self):
        """Create database engine."""
        self.engine = create_async_engine(TEST_DB_URL, echo=False)
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def create_tables(self):
        """Create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("Tables created")

    async def drop_tables(self):
        """Drop all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        print("Tables dropped")

    async def clear_tables(self):
        """Clear all data from tables."""
        await self.engine.dispose()

        async with self.engine.begin() as conn:
            await conn.execute(text("SET session_replication_role = 'replica';"))

            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(table.delete())

            await conn.execute(text("SET session_replication_role = 'origin';"))
        print("Tables cleared")

    async def get_session(self) -> AsyncSession:
        """Get a new database session."""
        return self.session_factory()

    async def close(self):
        """Close engine."""
        if self.engine:
            await self.engine.dispose()


_test_db = None


async def get_test_db():
    """Get or create test database instance."""
    global _test_db
    if _test_db is None:
        _test_db = TestDatabase()
        await _test_db.create_engine()
    return _test_db


async def setup_test_database():
    """Setup test database (run once before all tests)."""
    db = await get_test_db()
    await db.create_tables()


async def teardown_test_database():
    """Teardown test database (run once after all tests)."""
    global _test_db
    if _test_db:
        await _test_db.drop_tables()
        await _test_db.close()
        _test_db = None


async def clear_test_database():
    """Clear test database (run before each test)."""
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
