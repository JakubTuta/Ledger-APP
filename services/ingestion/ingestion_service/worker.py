import asyncio
import datetime
import logging
import signal
import sys

from sqlalchemy import insert, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

import ingestion_service.config as config
import ingestion_service.database as database
import ingestion_service.models as models
import ingestion_service.services.partition_manager as partition_manager
import ingestion_service.services.partition_scheduler as partition_scheduler
import ingestion_service.services.queue_service as queue_service
import ingestion_service.services.redis_client as redis_client

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class StorageWorker:
    def __init__(self, worker_id: int):
        self.worker_id = worker_id
        self.running = False
        self.processed_count = 0
        self.failed_count = 0

    async def process_logs_batch(self, logs: list[dict]) -> None:
        if not logs:
            return

        async with database.get_session() as session:
            try:
                log_records = []
                required_partitions = set()

                for log_data in logs:
                    timestamp = datetime.datetime.fromisoformat(log_data["timestamp"])

                    log_record = {
                        "project_id": log_data["project_id"],
                        "timestamp": timestamp,
                        "ingested_at": datetime.datetime.fromisoformat(
                            log_data["ingested_at"]
                        ),
                        "level": log_data["level"],
                        "log_type": log_data["log_type"],
                        "importance": log_data["importance"],
                        "environment": log_data.get("environment"),
                        "release": log_data.get("release"),
                        "message": log_data.get("message"),
                        "error_type": log_data.get("error_type"),
                        "error_message": log_data.get("error_message"),
                        "stack_trace": log_data.get("stack_trace"),
                        "attributes": log_data.get("attributes"),
                        "sdk_version": log_data.get("sdk_version"),
                        "platform": log_data.get("platform"),
                        "platform_version": log_data.get("platform_version"),
                        "error_fingerprint": log_data.get("error_fingerprint"),
                    }
                    log_records.append(log_record)
                    required_partitions.add(timestamp.date())

                for partition_date in required_partitions:
                    await partition_manager.ensure_partition_for_date(
                        session, "logs", partition_date
                    )

                await session.execute(insert(models.Log).values(log_records))

                for log_data in logs:
                    if log_data.get("error_fingerprint"):
                        await self.upsert_error_group(session, log_data)

                await session.commit()
                self.processed_count += len(logs)
                logger.info(
                    f"Worker {self.worker_id}: Processed {len(logs)} logs (total: {self.processed_count})"
                )

            except Exception as e:
                await session.rollback()
                self.failed_count += len(logs)
                logger.error(
                    f"Worker {self.worker_id}: Failed to insert logs batch: {e}",
                    exc_info=True,
                )
                raise

    async def upsert_error_group(self, session, log_data: dict) -> None:
        try:
            stmt = pg_insert(models.ErrorGroup).values(
                project_id=log_data["project_id"],
                fingerprint=log_data["error_fingerprint"],
                error_type=log_data.get("error_type", "UnknownError"),
                error_message=log_data.get("error_message"),
                first_seen=datetime.datetime.fromisoformat(log_data["timestamp"]),
                last_seen=datetime.datetime.fromisoformat(log_data["timestamp"]),
                occurrence_count=1,
                sample_stack_trace=log_data.get("stack_trace"),
            )

            stmt = stmt.on_conflict_do_update(
                index_elements=["project_id", "fingerprint"],
                set_={
                    "last_seen": datetime.datetime.fromisoformat(log_data["timestamp"]),
                    "occurrence_count": models.ErrorGroup.occurrence_count + 1,
                    "updated_at": datetime.datetime.now(datetime.timezone.utc),
                },
            )

            await session.execute(stmt)

        except Exception as e:
            logger.error(
                f"Worker {self.worker_id}: Failed to upsert error group: {e}",
                exc_info=True,
            )

    async def run(self) -> None:
        self.running = True
        logger.info(f"Worker {self.worker_id} started")

        while self.running:
            try:
                redis_conn = redis_client.get_redis_client()
                all_project_keys = await redis_conn.keys("queue:logs:*")

                if not all_project_keys:
                    await asyncio.sleep(5)
                    continue

                for queue_key in all_project_keys:
                    if not self.running:
                        break

                    project_id_str = queue_key.decode().split(":")[-1]
                    project_id = int(project_id_str)

                    logs = await queue_service.dequeue_logs_batch(
                        project_id, batch_size=config.settings.QUEUE_BATCH_SIZE
                    )

                    if logs:
                        await self.process_logs_batch(logs)
                    else:
                        await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Worker {self.worker_id}: Error in main loop: {e}", exc_info=True)
                await asyncio.sleep(5)

        logger.info(
            f"Worker {self.worker_id} stopped (processed: {self.processed_count}, failed: {self.failed_count})"
        )

    async def stop(self) -> None:
        logger.info(f"Worker {self.worker_id} stopping...")
        self.running = False


class WorkerManager:
    def __init__(self, worker_count: int):
        self.worker_count = worker_count
        self.workers: list[StorageWorker] = []
        self.tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        logger.info(f"Starting {self.worker_count} storage workers...")

        for i in range(self.worker_count):
            worker = StorageWorker(worker_id=i)
            self.workers.append(worker)

            task = asyncio.create_task(worker.run())
            self.tasks.append(task)

        logger.info("All workers started")

    async def stop(self) -> None:
        logger.info("Stopping all workers...")

        for worker in self.workers:
            await worker.stop()

        await asyncio.gather(*self.tasks, return_exceptions=True)

        logger.info("All workers stopped")


async def main():
    logger.info("Initializing storage worker manager...")

    database.get_engine()
    logger.info("Database engine initialized")

    try:
        async with database.get_session() as session:
            await partition_manager.ensure_all_partitions(
                session,
                months_ahead=config.settings.PARTITION_MONTHS_AHEAD,
            )
        logger.info("Partition management complete")
    except Exception as e:
        logger.error(f"Failed to ensure partitions exist: {e}", exc_info=True)
        logger.warning("Worker will continue, but may fail if partitions are missing")

    if config.settings.ENABLE_PARTITION_SCHEDULER:
        scheduler = partition_scheduler.get_partition_scheduler()
        scheduler.start()
        logger.info("Partition scheduler started")
    else:
        logger.info("Partition scheduler disabled by configuration")

    redis_client.get_redis_client()
    logger.info("Redis client initialized")

    manager = WorkerManager(worker_count=config.settings.WORKER_COUNT)

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(shutdown(manager))

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    await manager.start()

    while True:
        await asyncio.sleep(1)


async def shutdown(manager: WorkerManager):
    await manager.stop()

    if config.settings.ENABLE_PARTITION_SCHEDULER:
        scheduler = partition_scheduler.get_partition_scheduler()
        scheduler.stop()
        logger.info("Partition scheduler stopped")

    await redis_client.close_redis()
    await database.close_db()
    logger.info("Shutdown complete")
    sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
