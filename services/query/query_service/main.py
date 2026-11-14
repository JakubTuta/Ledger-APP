import asyncio
import concurrent.futures
import logging
import signal

import grpc
import query_service.config as config
import query_service.database as database
import query_service.grpc.servicers as servicers
import query_service.proto.query_pb2_grpc as query_pb2_grpc
import ledger_common.redis_client as redis_client
import ledger_common.self_monitoring as self_monitoring

logging.basicConfig(
    level=getattr(logging, config.settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def serve():
    self_monitoring.start("query", config.settings)
    await database.init_db()

    await redis_client.init_redis(config.get_settings())

    server = grpc.aio.server(
        concurrent.futures.ThreadPoolExecutor(max_workers=config.settings.GRPC_MAX_WORKERS),
        interceptors=self_monitoring.rpc_interceptors("query"),
        options=config.settings.grpc_server_options,
    )

    query_pb2_grpc.add_QueryServiceServicer_to_server(
        servicers.QueryServiceServicer(),
        server,
    )

    server.add_insecure_port(f"{config.settings.QUERY_HOST}:{config.settings.QUERY_GRPC_PORT}")

    await server.start()

    async def shutdown(sig):
        await server.stop(grace=5)
        await redis_client.close_redis()
        await database.close_db()
        self_monitoring.stop()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        pass


def main():
    asyncio.run(serve())


if __name__ == "__main__":
    main()
