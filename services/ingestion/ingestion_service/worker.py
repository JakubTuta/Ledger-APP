import asyncio
import datetime
import logging
import signal
import sys

import aio_pika
import aio_pika.abc
import msgpack

import ingestion_service.config as config
import ingestion_service.database as database
import ingestion_service.models as models
import ingestion_service.services.partition_manager as partition_manager
import ingestion_service.services.partition_scheduler as partition_scheduler
import ingestion_service.services.rabbitmq_client as rabbitmq_client
from sqlalchemy import insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

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

                    method = None
                    path = None
                    status_code = None
                    duration_ms = None
                    attributes = log_data.get("attributes")
                    if log_data.get("log_type") in ("endpoint", "network") and attributes:
                        ep = attributes.get("endpoint") or {}
                        method = ep.get("method")
                        path = ep.get("path")
                        raw_status = ep.get("status_code")
                        raw_duration = ep.get("duration_ms")
                        if raw_status is not None:
                            try:
                                status_code = int(raw_status)
                            except (TypeError, ValueError):
                                pass
                        if raw_duration is not None:
                            try:
                                duration_ms = round(float(raw_duration))
                            except (TypeError, ValueError):
                                pass

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
                        "attributes": attributes,
                        "sdk_version": log_data.get("sdk_version"),
                        "platform": log_data.get("platform"),
                        "platform_version": log_data.get("platform_version"),
                        "error_fingerprint": log_data.get("error_fingerprint"),
                        "method": method,
                        "path": path,
                        "status_code": status_code,
                        "duration_ms": duration_ms,
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
            )

    async def _flush_batch(
        self,
        messages: list[aio_pika.abc.AbstractIncomingMessage],
        payloads: list[dict],
    ) -> None:
        try:
            await self.process_logs_batch(payloads)
            await messages[-1].ack(multiple=True)
            logger.debug(
                f"Worker {self.worker_id}: ACKed batch of {len(messages)} messages"
            )
        except Exception as e:
            logger.error(
                f"Worker {self.worker_id}: Batch of {len(messages)} failed, sending to DLQ: {e}",
            )
            self.failed_count += len(messages)
            for message in messages:
                await message.nack(requeue=False)

    async def run(self) -> None:
        self.running = True

        connection = await rabbitmq_client.get_connection()
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=config.settings.RABBITMQ_PREFETCH_COUNT)

        queue = await channel.declare_queue(
            config.settings.RABBITMQ_QUEUE,
            passive=True,
        )

        message_buffer: asyncio.Queue[aio_pika.abc.AbstractIncomingMessage] = (
            asyncio.Queue()
        )

        async def on_message(
            message: aio_pika.abc.AbstractIncomingMessage,
        ) -> None:
            await message_buffer.put(message)

        consumer_tag = await queue.consume(on_message)
        logger.info(f"Worker {self.worker_id}: consuming from {config.settings.RABBITMQ_QUEUE}")

        try:
            while self.running:
                batch_messages: list[aio_pika.abc.AbstractIncomingMessage] = []
                batch_payloads: list[dict] = []

                try:
                    first_message = await asyncio.wait_for(
                        message_buffer.get(),
                        timeout=config.settings.BATCH_FLUSH_INTERVAL,
                    )
                except asyncio.TimeoutError:
                    continue

                try:
                    payload = msgpack.unpackb(first_message.body, raw=False)
                    batch_messages.append(first_message)
                    batch_payloads.append(payload)
                except Exception as e:
                    logger.error(f"Worker {self.worker_id}: Failed to decode message: {e}")
                    await first_message.nack(requeue=False)
                    continue

                while len(batch_messages) < config.settings.QUEUE_BATCH_SIZE:
                    try:
                        message = message_buffer.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    try:
                        payload = msgpack.unpackb(message.body, raw=False)
                        batch_messages.append(message)
                        batch_payloads.append(payload)
                    except Exception as e:
                        logger.error(f"Worker {self.worker_id}: Failed to decode message: {e}")
                        await message.nack(requeue=False)

                if batch_messages:
                    await self._flush_batch(batch_messages, batch_payloads)

        finally:
            await queue.cancel(consumer_tag)
            await channel.close()

    async def stop(self) -> None:
        self.running = False


class WorkerManager:
    def __init__(self, worker_count: int):
        self.worker_count = worker_count
        self.workers: list[StorageWorker] = []
        self.tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        for i in range(self.worker_count):
            worker = StorageWorker(worker_id=i)
            self.workers.append(worker)

            task = asyncio.create_task(worker.run())
            self.tasks.append(task)

    async def stop(self) -> None:
        for worker in self.workers:
            await worker.stop()

        await asyncio.gather(*self.tasks, return_exceptions=True)


async def main():
    database.get_engine()

    try:
        async with database.get_session() as session:
            await partition_manager.ensure_all_partitions(
                session,
                months_ahead=config.settings.PARTITION_MONTHS_AHEAD,
            )
    except Exception as e:
        logger.error(f"Failed to ensure partitions exist: {e}", exc_info=True)
        logger.warning("Worker will continue, but may fail if partitions are missing")

    if config.settings.ENABLE_PARTITION_SCHEDULER:
        scheduler = partition_scheduler.get_partition_scheduler()
        scheduler.start()
    else:
        logger.warning("Partition scheduler disabled by configuration")

    await rabbitmq_client.setup_topology()

    manager = WorkerManager(worker_count=config.settings.WORKER_COUNT)

    def signal_handler(sig, frame):
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

    await rabbitmq_client.close()
    await database.close_db()
    sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
