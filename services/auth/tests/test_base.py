import asyncio

import pytest_asyncio
from auth_service import database
from auth_service.config import settings
from auth_service.grpc.servicers import AuthServicer
from auth_service.proto import auth_pb2_grpc
from grpc import aio
from redis.asyncio import Redis

from .db_setup import (
    clear_test_database,
    get_test_db,
    setup_test_database,
    teardown_test_database,
)


def pytest_configure(config):
    """Called before any tests run."""
    asyncio.run(setup_test_database())


def pytest_unconfigure(config):
    """Called after all tests complete."""
    asyncio.run(teardown_test_database())


class BaseGrpcTest:
    """Base class for gRPC endpoint tests."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_method(self):
        """Setup before each test."""
        self.test_db_manager = await get_test_db()

        await clear_test_database()

        self.db_session = await self.test_db_manager.get_session()

        self.redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)
        try:
            await self.redis.flushdb()
        except:
            pass

        database._session_factory = self.test_db_manager.session_factory
        database._engine = self.test_db_manager.engine

        self.server = aio.server()
        auth_pb2_grpc.add_AuthServiceServicer_to_server(
            AuthServicer(self.redis), self.server
        )
        port = self.server.add_insecure_port("localhost:0")
        await self.server.start()

        self.channel = aio.insecure_channel(f"localhost:{port}")
        self.stub = auth_pb2_grpc.AuthServiceStub(self.channel)

        yield

        try:
            if hasattr(self, "stub"):
                del self.stub
        except:
            pass

        try:
            if hasattr(self, "channel"):
                await self.channel.close()
        except:
            pass

        try:
            if hasattr(self, "server"):
                await self.server.stop(0)
        except:
            pass

        try:
            if hasattr(self, "db_session"):
                await self.db_session.close()
        except:
            pass

        try:
            if hasattr(self, "redis"):
                await self.redis.aclose()
        except:
            pass
