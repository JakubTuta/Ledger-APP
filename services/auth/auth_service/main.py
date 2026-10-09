import asyncio
import concurrent.futures
import logging

import grpc
from redis.asyncio import Redis

from . import config, database
from .grpc import servicers
from .proto import auth_pb2_grpc
from .services import connector_secrets, self_monitoring

logging.basicConfig(
    level=getattr(logging, config.settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def _encrypt_stored_connector_secrets() -> None:
    connector_secrets.ensure_key_configured()
    async with database.get_session() as session:
        rewritten = await connector_secrets.rewrite_stored_configs(session)
    if rewritten:
        logger.info(f"Encrypted connector secrets under the current key: {rewritten} connectors")


async def serve():
    """Start gRPC server."""

    self_monitoring.start("auth")
    await _encrypt_stored_connector_secrets()

    redis = Redis.from_url(
        config.settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=False,
        max_connections=50,
    )

    server = grpc.aio.server(
        concurrent.futures.ThreadPoolExecutor(max_workers=10),
        interceptors=self_monitoring.rpc_interceptors("auth"),
        options=[
            ("grpc.max_send_message_length", 100 * 1024 * 1024),
            ("grpc.max_receive_message_length", 100 * 1024 * 1024),
            ("grpc.keepalive_time_ms", config.settings.GRPC_KEEPALIVE_TIME_MS),
            ("grpc.keepalive_timeout_ms", config.settings.GRPC_KEEPALIVE_TIMEOUT_MS),
            (
                "grpc.keepalive_permit_without_calls",
                config.settings.GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS,
            ),
            ("grpc.max_connection_idle_ms", config.settings.GRPC_MAX_CONNECTION_IDLE_MS),
            ("grpc.max_connection_age_ms", config.settings.GRPC_MAX_CONNECTION_AGE_MS),
            (
                "grpc.http2.min_recv_ping_interval_without_data_ms",
                config.settings.GRPC_HTTP2_MIN_RECV_PING_INTERVAL_WITHOUT_DATA_MS,
            ),
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
        self_monitoring.stop()


def main():
    """Entry point."""
    asyncio.run(serve())


if __name__ == "__main__":
    main()
