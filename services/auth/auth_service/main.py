import asyncio
import concurrent.futures
import logging

import grpc
from redis.asyncio import Redis

from . import config, database
from .grpc import servicers
from .proto import auth_pb2_grpc

logging.basicConfig(
    level=getattr(logging, config.settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def serve():
    """Start gRPC server."""

    redis = Redis.from_url(
        config.settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=False,
        max_connections=50,
    )

    server = grpc.aio.server(
        concurrent.futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.max_send_message_length", 10 * 1024 * 1024),
            ("grpc.max_receive_message_length", 10 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 10000),
            ("grpc.keepalive_timeout_ms", 5000),
            ("grpc.http2.min_time_between_pings_ms", 5000),
            ("grpc.http2.max_pings_without_data", 0),
            ("grpc.keepalive_permit_without_calls", 1),
            ("grpc.max_connection_idle_ms", 60000),
            ("grpc.max_connection_age_ms", 300000),
        ],
    )

    auth_pb2_grpc.add_AuthServiceServicer_to_server(
        servicers.AuthServicer(redis),
        server,
    )

    server.add_insecure_port(f"0.0.0.0:{config.settings.AUTH_GRPC_PORT}")

    await server.start()

    try:
        await server.wait_for_termination()
    finally:
        await server.stop(grace=5)
        await redis.close()
        await database.close_db()


def main():
    """Entry point."""
    asyncio.run(serve())


if __name__ == "__main__":
    main()
