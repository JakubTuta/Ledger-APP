import typing

import sqlalchemy.ext.asyncio as async_sqlalchemy

import analytics_workers.config as config

logs_engine: async_sqlalchemy.AsyncEngine | None = None
auth_engine: async_sqlalchemy.AsyncEngine | None = None
logs_session_maker: async_sqlalchemy.async_sessionmaker | None = None
auth_session_maker: async_sqlalchemy.async_sessionmaker | None = None


async def init_db() -> None:
    global logs_engine, auth_engine, logs_session_maker, auth_session_maker

    settings = config.get_settings()

    logs_engine = async_sqlalchemy.create_async_engine(
        settings.LOGS_DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=settings.DEBUG,
    )

    auth_engine = async_sqlalchemy.create_async_engine(
        settings.AUTH_DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=settings.DEBUG,
    )

    logs_session_maker = async_sqlalchemy.async_sessionmaker(
        logs_engine,
        class_=async_sqlalchemy.AsyncSession,
        expire_on_commit=False,
    )

    auth_session_maker = async_sqlalchemy.async_sessionmaker(
        auth_engine,
        class_=async_sqlalchemy.AsyncSession,
        expire_on_commit=False,
    )


async def close_db() -> None:
    global logs_engine, auth_engine

    if logs_engine:
        await logs_engine.dispose()
    if auth_engine:
        await auth_engine.dispose()


def get_logs_session() -> typing.AsyncIterator[async_sqlalchemy.AsyncSession]:
    if logs_session_maker is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return logs_session_maker()


def get_auth_session() -> typing.AsyncIterator[async_sqlalchemy.AsyncSession]:
    if auth_session_maker is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return auth_session_maker()
