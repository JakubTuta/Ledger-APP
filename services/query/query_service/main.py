import asyncio
import concurrent.futures
import logging
import signal

import grpc

import query_service.config as config
import query_service.database as database
import query_service.grpc.servicers as servicers
import query_service.proto.query_pb2_grpc as query_pb2_grpc
import query_service.redis_client as redis_client

logging.basicConfig(
    level=getattr(logging, config.settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def serve():
    logger.info("Initializing Query Service...")

    await database.init_db()
    logger.info("Database initialized")

    await redis_client.init_redis()
    logger.info("Redis initialized")

    server = grpc.aio.server(
        concurrent.futures.ThreadPoolExecutor(
            max_workers=config.settings.GRPC_MAX_WORKERS
        ),
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

    query_pb2_grpc.add_QueryServiceServicer_to_server(
        servicers.QueryServiceServicer(),
        server,
    )

    server.add_insecure_port(
        f"{config.settings.GRPC_SERVER_HOST}:{config.settings.GRPC_SERVER_PORT}"
    )

    await server.start()
    logger.info(
        f"Query Service gRPC server started on port {config.settings.GRPC_SERVER_PORT}"
    )

    async def shutdown(sig):
        logger.info(f"Received signal {sig.name}, shutting down gracefully...")
        await server.stop(grace=5)
        await redis_client.close_redis()
        await database.close_db()
        logger.info("Cleanup complete")

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")


def main():
    asyncio.run(serve())


if __name__ == "__main__":
    main()
