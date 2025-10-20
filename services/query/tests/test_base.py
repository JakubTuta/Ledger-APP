import os

import grpc.aio as grpc_aio
import pytest_asyncio
import redis.asyncio as redis_async

import query_service.config as config
import query_service.database as database
import query_service.grpc.servicers as servicers
import query_service.redis_client as redis_client
import query_service.proto.query_pb2_grpc as query_pb2_grpc


class BaseQueryTest:
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

        self.redis = redis_async.Redis.from_url(test_redis_url, decode_responses=True)
        await self.redis.flushdb()

        redis_client.redis_client = self.redis

        database.logs_session_maker = self.test_db_manager.session_factory
        database.logs_engine = self.test_db_manager.engine

        self.server = grpc_aio.server()
        query_pb2_grpc.add_QueryServiceServicer_to_server(
            servicers.QueryServiceServicer(), self.server
        )
        port = self.server.add_insecure_port("localhost:0")
        await self.server.start()

        self.channel = grpc_aio.insecure_channel(f"localhost:{port}")
        self.stub = query_pb2_grpc.QueryServiceStub(self.channel)

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
        redis_client.redis_client = None
