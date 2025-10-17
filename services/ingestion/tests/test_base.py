import os

import grpc.aio as grpc_aio
import pytest_asyncio
import redis.asyncio as redis_async

import ingestion_service.config as config
import ingestion_service.database as database
import ingestion_service.grpc.servicers as servicers
import ingestion_service.proto.ingestion_pb2_grpc as ingestion_pb2_grpc
import ingestion_service.services.redis_client as redis_client


class BaseIngestionTest:
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

        redis_client._redis_client = self.redis

        database._session_factory = self.test_db_manager.session_factory
        database._engine = self.test_db_manager.engine

        self.server = grpc_aio.server()
        ingestion_pb2_grpc.add_IngestionServiceServicer_to_server(
            servicers.IngestionServicer(), self.server
        )
        port = self.server.add_insecure_port("localhost:0")
        await self.server.start()

        self.channel = grpc_aio.insecure_channel(f"localhost:{port}")
        self.stub = ingestion_pb2_grpc.IngestionServiceStub(self.channel)

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
        redis_client._redis_client = None
