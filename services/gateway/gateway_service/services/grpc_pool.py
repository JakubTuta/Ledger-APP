import asyncio
import contextlib
import logging
import typing

import grpc
from gateway_service import config
from gateway_service.proto import auth_pb2_grpc, ingestion_pb2_grpc, query_pb2_grpc

logger = logging.getLogger(__name__)


class GRPCChannelPool:
    def __init__(self, service_name: str, address: str, pool_size: int = 10):
        self.service_name = service_name
        self.address = address
        self.pool_size = pool_size
        self.channels: typing.List[grpc.aio.Channel] = []
        self.current_index = 0
        self._lock = asyncio.Lock()

    async def initialize(self):
        for i in range(self.pool_size):
            channel = grpc.aio.insecure_channel(
                self.address,
                options=[
                    ("grpc.keepalive_time_ms", config.settings.GRPC_KEEPALIVE_TIME_MS),
                    ("grpc.keepalive_timeout_ms", config.settings.GRPC_KEEPALIVE_TIMEOUT_MS),
                    ("grpc.keepalive_permit_without_calls", 0),
                    ("grpc.http2.max_pings_without_data", 2),
                    ("grpc.http2.min_time_between_pings_ms", config.settings.GRPC_KEEPALIVE_TIME_MS),
                    ("grpc.max_receive_message_length", 100 * 1024 * 1024),
                    ("grpc.max_send_message_length", 100 * 1024 * 1024),
                ],
            )

            self.channels.append(channel)

    def get_channel(self) -> grpc.aio.Channel:
        if not self.channels:
            raise RuntimeError(f"No channels available for {self.service_name}")

        channel = self.channels[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.channels)

        return channel

    def get_stub(self, stub_class):
        channel = self.get_channel()
        return stub_class(channel)

    async def close_all(self):
        for i, channel in enumerate(self.channels):
            try:
                await channel.close()
            except Exception as e:
                logger.error(f"Error closing channel {i+1}: {e}")

        self.channels.clear()


class GRPCPoolManager:
    def __init__(self):
        self.pools: typing.Dict[str, GRPCChannelPool] = {}
        self._lock = asyncio.Lock()

    async def add_service(
        self, service_name: str, address: str, pool_size: typing.Optional[int] = None
    ):
        if pool_size is None:
            pool_size = config.settings.GRPC_POOL_SIZE

        async with self._lock:
            if service_name in self.pools:
                logger.warning(f"Service {service_name} already registered")
                return

            pool = GRPCChannelPool(service_name, address, pool_size)
            await pool.initialize()
            self.pools[service_name] = pool

    def get_pool(self, service_name: str) -> GRPCChannelPool:
        if service_name not in self.pools:
            raise KeyError(f"Service {service_name} not registered")

        return self.pools[service_name]

    def get_channel(self, service_name: str) -> grpc.aio.Channel:
        return self.get_pool(service_name).get_channel()

    def get_stub(self, service_name: str, stub_class):
        return self.get_pool(service_name).get_stub(stub_class)

    @contextlib.asynccontextmanager
    async def get_auth_stub(self):
        """
        Context manager for Auth Service stub.

        Usage:
            async with grpc_pool.get_auth_stub() as stub:
                response = await stub.ValidateApiKey(request)
        """
        try:
            stub = self.get_stub("auth", auth_pb2_grpc.AuthServiceStub)
            yield stub
        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise

    @contextlib.asynccontextmanager
    async def get_ingestion_stub(self):
        """
        Context manager for Ingestion Service stub.

        Usage:
            async with grpc_pool.get_ingestion_stub() as stub:
                response = await stub.IngestLog(request)
        """
        try:
            stub = self.get_stub("ingestion", ingestion_pb2_grpc.IngestionServiceStub)
            yield stub
        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise

    @contextlib.asynccontextmanager
    async def get_query_stub(self):
        """
        Context manager for Query Service stub.

        Usage:
            async with grpc_pool.get_query_stub() as stub:
                response = await stub.GetLog(request)
        """
        try:
            stub = self.get_stub("query", query_pb2_grpc.QueryServiceStub)
            yield stub
        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise

    async def close_all(self):
        for _, pool in self.pools.items():
            await pool.close_all()

        self.pools.clear()

    def get_stats(self) -> typing.Dict:
        stats = {}
        for service_name, pool in self.pools.items():
            stats[service_name] = {
                "address": pool.address,
                "pool_size": pool.pool_size,
                "active_channels": len(pool.channels),
                "current_index": pool.current_index,
            }

        return stats
