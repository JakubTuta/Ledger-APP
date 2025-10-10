import contextlib
import typing

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from . import config


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create database engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            config.settings.AUTH_DATABASE_URL,
            pool_size=config.settings.DB_POOL_SIZE,
            max_overflow=config.settings.DB_MAX_OVERFLOW,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=config.settings.DEBUG,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@contextlib.asynccontextmanager
async def get_session() -> typing.AsyncGenerator[AsyncSession, None]:
    """Get database session with automatic cleanup."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db():
    """Close database connections (call on shutdown)."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
