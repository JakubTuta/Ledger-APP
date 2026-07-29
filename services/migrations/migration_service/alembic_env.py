"""Shared alembic environment.

Each database's `alembic/<key>/env.py` is a one-liner that calls `run(key)`, so
the connection handling lives in one place instead of once per database.
"""

import asyncio

import migration_service.databases as databases
import migration_service.runner as runner
import sqlalchemy
from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext import asyncio as sqlalchemy_asyncio


def run(key: str) -> None:
    target = databases.get_target(key)
    metadata = runner.load_metadata(target)
    context.config.set_main_option("sqlalchemy.url", target.url)

    if context.is_offline_mode():
        _run_offline(target, metadata)
    else:
        asyncio.run(_run_online(target, metadata))


def _run_offline(
    target: databases.DatabaseTarget,
    metadata: sqlalchemy.MetaData | None,
) -> None:
    """Emit migration SQL to stdout without connecting to the database."""
    context.configure(
        url=target.url,
        target_metadata=metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


async def _run_online(
    target: databases.DatabaseTarget,
    metadata: sqlalchemy.MetaData | None,
) -> None:
    engine = sqlalchemy_asyncio.create_async_engine(target.url, poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_apply, metadata)
    finally:
        await engine.dispose()


def _apply(connection: sqlalchemy.Connection, metadata: sqlalchemy.MetaData | None) -> None:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()
