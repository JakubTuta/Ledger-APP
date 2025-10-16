import os

import pytest_asyncio
import auth_service.database as database
import auth_service.config as config
import auth_service.grpc.servicers as servicers
import auth_service.proto.auth_pb2_grpc as auth_pb2_grpc
import grpc.aio as grpc_aio
import redis.asyncio as redis_async


class BaseGrpcTest:
    @pytest_asyncio.fixture(autouse=True)
    async def setup_method(self, test_db_manager):
        self.test_db_manager = test_db_manager

        test_redis_host = os.getenv("TEST_REDIS_HOST", "localhost")
        redis_password = config.settings.REDIS_PASSWORD
        redis_db = config.settings.REDIS_DB

        if redis_password:
            test_redis_url = f"redis://:{redis_password}@{test_redis_host}:{config.settings.REDIS_PORT}/{redis_db}"
        else:
            test_redis_url = f"redis://{test_redis_host}:{config.settings.REDIS_PORT}/{redis_db}"

        self.redis = redis_async.Redis.from_url(test_redis_url, decode_responses=False)
        await self.redis.flushdb()

        database._session_factory = self.test_db_manager.session_factory
        database._engine = self.test_db_manager.engine

        self.server = grpc_aio.server()
        auth_pb2_grpc.add_AuthServiceServicer_to_server(
            servicers.AuthServicer(self.redis), self.server
        )
        port = self.server.add_insecure_port("localhost:0")
        await self.server.start()

        self.channel = grpc_aio.insecure_channel(f"localhost:{port}")
        self.stub = auth_pb2_grpc.AuthServiceStub(self.channel)

        yield

        try:
            await self.channel.close()
        except Exception:
            pass
        try:
            await self.server.stop(0)
        except Exception:
            pass
        try:
            await self.redis.aclose()
        except Exception:
            pass
