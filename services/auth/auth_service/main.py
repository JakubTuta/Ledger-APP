import asyncio
import concurrent.futures
import logging

import grpc
import ledger_common.connector_secrets as connector_secrets
import ledger_common.self_monitoring as self_monitoring
from redis.asyncio import Redis

from . import config, database
from .grpc import servicers
from .proto import auth_pb2_grpc
from .services import connector_secrets_backfill

logging.basicConfig(
    level=getattr(logging, config.settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def _encrypt_stored_connector_secrets() -> None:
    connector_secrets.ensure_key_configured(config.settings.CONNECTOR_SECRETS_KEY)
    async with database.get_session() as session:
        rewritten = await connector_secrets_backfill.rewrite_stored_configs(session)
    if rewritten:
        logger.info(f"Encrypted connector secrets under the current key: {rewritten} connectors")


async def serve():
    """Start gRPC server."""

    self_monitoring.start("auth", config.settings)
    await _encrypt_stored_connector_secrets()

    redis = Redis.from_url(
        config.settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=False,
        max_connections=config.settings.REDIS_MAX_CONNECTIONS,
    )

    server = grpc.aio.server(
        concurrent.futures.ThreadPoolExecutor(max_workers=10),
        interceptors=self_monitoring.rpc_interceptors("auth"),
        options=config.settings.grpc_server_options,
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
