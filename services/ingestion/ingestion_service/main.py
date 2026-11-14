import asyncio
import logging

import grpc
import ingestion_service.config as config
import ingestion_service.grpc.servicers as servicers
import ingestion_service.proto.ingestion_pb2_grpc as ingestion_pb2_grpc
import ingestion_service.services.rabbitmq_client as rabbitmq_client
import ingestion_service.services.redis_client as redis_client
import ledger_common.self_monitoring as self_monitoring

logging.basicConfig(
    level=getattr(logging, config.settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def serve():
    self_monitoring.start("ingestion", config.settings)
    redis = redis_client.get_redis_client()
    await redis.ping()

    await rabbitmq_client.setup_topology()

    server = grpc.aio.server(
        interceptors=self_monitoring.rpc_interceptors("ingestion"),
        options=config.settings.grpc_server_options,
    )
    ingestion_pb2_grpc.add_IngestionServiceServicer_to_server(
        servicers.IngestionServicer(redis_client=redis), server
    )

    listen_addr = f"{config.settings.INGESTION_HOST}:{config.settings.INGESTION_GRPC_PORT}"
    server.add_insecure_port(listen_addr)

    await server.start()

    try:
        await server.wait_for_termination()
    finally:
        await server.stop(grace=5)

        await rabbitmq_client.close()
        await redis_client.close_redis()

        self_monitoring.stop()


if __name__ == "__main__":
    asyncio.run(serve())
