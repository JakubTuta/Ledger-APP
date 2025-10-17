import asyncio

import pytest
import pytest_asyncio

import tests.db_setup as db_setup


def pytest_configure(config):
    if not hasattr(config, "workerinput"):
        asyncio.run(db_setup.setup_test_database())


def pytest_unconfigure(config):
    if not hasattr(config, "workerinput"):
        asyncio.run(db_setup.teardown_test_database())


@pytest_asyncio.fixture
async def test_db_manager():
    db_manager = await db_setup.get_test_db()
    try:
        await db_setup.clear_test_database()
    except Exception as e:
        print(f"Error clearing tables, recreating: {e}")
        try:
            await db_manager.create_tables()
            await db_setup.clear_test_database()
        except Exception as e2:
            print(f"Error creating tables: {e2}")
            raise
    yield db_manager
