import os

import aio_pika
import grpc.aio as grpc_aio
import msgpack
import pytest_asyncio
import redis.asyncio as redis_async

import ingestion_service.config as config
import ingestion_service.database as database
import ingestion_service.grpc.servicers as servicers
import ingestion_service.proto.ingestion_pb2_grpc as ingestion_pb2_grpc
import ingestion_service.services.rabbitmq_client as rabbitmq_client
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

        test_rabbitmq_host = os.getenv("TEST_RABBITMQ_HOST", "localhost")
        rabbitmq_url = (
            f"amqp://{config.settings.RABBITMQ_USER}:{config.settings.RABBITMQ_PASSWORD}"
            f"@{test_rabbitmq_host}:{config.settings.RABBITMQ_PORT}/"
        )

        rabbitmq_client._connection = None
        rabbitmq_client._channel_pool = None

        self.rabbitmq_connection = await aio_pika.connect_robust(rabbitmq_url)
        rabbitmq_client._connection = self.rabbitmq_connection

        await rabbitmq_client.setup_topology()
        await self._purge_queues()

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
        try:
            await self._purge_queues()
        except Exception:
            pass
        try:
            if rabbitmq_client._channel_pool is not None:
                await rabbitmq_client._channel_pool.close()
                rabbitmq_client._channel_pool = None
            if not self.rabbitmq_connection.is_closed:
                await self.rabbitmq_connection.close()
        except Exception:
            pass

        redis_client._redis_client = None
        rabbitmq_client._connection = None
        rabbitmq_client._channel_pool = None

    async def _purge_queues(self) -> None:
        async with self.rabbitmq_connection.channel() as channel:
            for queue_name in [
                config.settings.RABBITMQ_QUEUE,
                config.settings.RABBITMQ_DLQ,
            ]:
                try:
                    queue = await channel.declare_queue(queue_name, passive=True)
                    await queue.purge()
                except Exception:
                    pass

    async def get_queue_message_count(self, queue_name: str | None = None) -> int:
        target = queue_name or config.settings.RABBITMQ_QUEUE
        async with self.rabbitmq_connection.channel() as channel:
            try:
                queue = await channel.declare_queue(target, passive=True)
                return queue.declaration_result.message_count
            except Exception:
                return 0

    async def consume_one_payload(self) -> dict | None:
        async with self.rabbitmq_connection.channel() as channel:
            queue = await channel.declare_queue(
                config.settings.RABBITMQ_QUEUE,
                passive=True,
            )
            message = await queue.get(no_ack=True, fail=False)
            if message is None:
                return None
            return msgpack.unpackb(message.body, raw=False)

    async def consume_all_payloads(self, count: int) -> list[dict]:
        payloads = []
        async with self.rabbitmq_connection.channel() as channel:
            queue = await channel.declare_queue(
                config.settings.RABBITMQ_QUEUE,
                passive=True,
            )
            for _ in range(count):
                message = await queue.get(no_ack=True, fail=False)
                if message is None:
                    break
                payloads.append(msgpack.unpackb(message.body, raw=False))
        return payloads
