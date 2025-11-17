import asyncio
import logging

import grpc

import ingestion_service.config as config
import ingestion_service.database as database
import ingestion_service.grpc.servicers as servicers
import ingestion_service.proto.ingestion_pb2_grpc as ingestion_pb2_grpc
import ingestion_service.services.redis_client as redis_client

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def serve():
    logger.info("Ingestion Service starting up...")

    redis = redis_client.get_redis_client()
    await redis.ping()
    logger.info("Redis connection initialized")

    db_engine = database.get_engine()
    logger.info("Database engine initialized")

    server = grpc.aio.server(
        options=[
            ("grpc.keepalive_time_ms", 10000),
            ("grpc.keepalive_timeout_ms", 5000),
            ("grpc.http2.min_time_between_pings_ms", 5000),
            ("grpc.http2.max_pings_without_data", 0),
            ("grpc.keepalive_permit_without_calls", 1),
            ("grpc.max_connection_idle_ms", 60000),
            ("grpc.max_connection_age_ms", 300000),
        ]
    )
    ingestion_pb2_grpc.add_IngestionServiceServicer_to_server(
        servicers.IngestionServicer(), server
    )

    listen_addr = f"{config.settings.INGESTION_HOST}:{config.settings.INGESTION_GRPC_PORT}"
    server.add_insecure_port(listen_addr)

    logger.info(f"Starting gRPC server on {listen_addr}")
    await server.start()
    logger.info(f"Ingestion Service gRPC server listening on {listen_addr}")

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        logger.info("Shutting down...")

        await server.stop(grace=5)
        logger.info("gRPC server stopped")

        await redis_client.close_redis()
        logger.info("Redis connection closed")

        await database.close_db()
        logger.info("Database connections closed")

        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(serve())
