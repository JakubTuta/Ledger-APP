import asyncio
import os

# Connector create/update encrypts credentials and refuses to run without a
# key. Fixed test-only key, set before auth_service.config is first imported.
os.environ.setdefault("CONNECTOR_SECRETS_KEY", "IFmJbAUZIllVQ4ShSzg7B4tGgQ2R1A_wQzzMmlqSUMI=")

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
    except Exception:
        await db_manager.create_tables()
        await db_setup.clear_test_database()
    yield db_manager
