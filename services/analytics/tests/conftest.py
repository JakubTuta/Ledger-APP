import asyncio

import pytest_asyncio

import tests.db_setup as db_setup


def pytest_configure(config):
    if not hasattr(config, "workerinput"):
        asyncio.run(db_setup.setup_test_databases())


def pytest_unconfigure(config):
    if not hasattr(config, "workerinput"):
        asyncio.run(db_setup.teardown_test_databases())


@pytest_asyncio.fixture
async def test_dbs():
    dbs = await db_setup.get_test_dbs()
    try:
        await db_setup.clear_test_databases()
    except Exception as e:
        print(f"Error clearing tables, recreating: {e}")
        try:
            await dbs.create_tables()
            await db_setup.clear_test_databases()
        except Exception as e2:
            print(f"Error creating tables: {e2}")
            raise

    import analytics_workers.database as database

    database.auth_session_maker = dbs.auth.session_factory
    database.auth_engine = dbs.auth.engine
    database.logs_session_maker = dbs.logs.session_factory
    database.logs_engine = dbs.logs.engine

    yield dbs
