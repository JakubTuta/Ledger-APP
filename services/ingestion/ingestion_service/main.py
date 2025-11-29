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
    redis = redis_client.get_redis_client()
    await redis.ping()

    db_engine = database.get_engine()

    server = grpc.aio.server(
        options=[
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.http2.min_time_between_pings_ms", 10000),
            ("grpc.http2.min_recv_ping_interval_without_data_ms", 10000),
            ("grpc.http2.max_pings_without_data", 0),
            ("grpc.keepalive_permit_without_calls", 0),
            ("grpc.max_connection_idle_ms", 300000),
            ("grpc.max_connection_age_ms", 600000),
        ]
    )
    ingestion_pb2_grpc.add_IngestionServiceServicer_to_server(
        servicers.IngestionServicer(redis_client=redis), server
    )

    listen_addr = (
        f"{config.settings.INGESTION_HOST}:{config.settings.INGESTION_GRPC_PORT}"
    )
    server.add_insecure_port(listen_addr)

    await server.start()

    try:
        await server.wait_for_termination()
    finally:
        await server.stop(grace=5)

        await redis_client.close_redis()

        await database.close_db()


if __name__ == "__main__":
    asyncio.run(serve())
