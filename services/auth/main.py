import contextlib
import os

import dotenv
import fastapi
import redis
import sqlalchemy.ext.asyncio as async_sqlalchemy
import sqlalchemy.pool as pool

dotenv.load_dotenv()


def get_database_engine() -> (
    tuple[async_sqlalchemy.AsyncEngine, async_sqlalchemy.async_sessionmaker]
):
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        user = os.getenv("POSTGRES_USER")
        password = os.getenv("POSTGRES_PASSWORD")
        db = os.getenv("POSTGRES_DB")
        port = os.getenv("DATABASE_PORT", "5432")

        if not all([user, password, db]):
            raise ValueError(
                "Database configuration is incomplete. "
                "Set DATABASE_URL or POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB."
            )

        database_url = f"postgresql+asyncpg://{user}:{password}@postgres:{port}/{db}"

    engine = async_sqlalchemy.create_async_engine(
        database_url,
        poolclass=pool.AsyncAdaptedQueuePool,
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=3600,
        pool_pre_ping=True,
        echo_pool=True,
    )

    session_local = async_sqlalchemy.async_sessionmaker(
        bind=engine,
        class_=async_sqlalchemy.AsyncSession,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    return engine, session_local


def get_redis_client() -> redis.Redis:
    host = os.getenv("REDIS_HOST")
    port = os.getenv("REDIS_PORT", "6379")
    db = os.getenv("REDIS_DB", "0")

    if not host:
        raise ValueError("Redis configuration is incomplete. Set REDIS_HOST.")

    try:
        redis_client = redis.Redis(
            host=host,
            port=int(port),
            db=int(db),
            decode_responses=True,
        )

        return redis_client

    except ValueError as e:
        raise ValueError(f"Invalid Redis port or db configuration: {e}")


@contextlib.asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    app.state.database_engine, app.state.database_session = get_database_engine()
    app.state.redis_client = get_redis_client()

    yield

    await app.state.database_engine.dispose()
    app.state.redis_client.close()


app = fastapi.FastAPI(lifespan=lifespan)
