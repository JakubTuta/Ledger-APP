import logging

import aio_pika
import msgpack

import ingestion_service.config as config
import ingestion_service.schemas as schemas
import ingestion_service.services.rabbitmq_client as rabbitmq_client

logger = logging.getLogger(__name__)


class QueueFullError(Exception):
    pass


def _build_payload(log: schemas.EnrichedLogEntry) -> bytes:
    payload = {
        "project_id": log.project_id,
        "timestamp": log.log_entry.timestamp.isoformat(),
        "ingested_at": log.ingested_at.isoformat(),
        "level": log.log_entry.level,
        "log_type": log.log_entry.log_type,
        "importance": log.log_entry.importance,
        "environment": log.log_entry.environment,
        "release": log.log_entry.release,
        "message": log.log_entry.message,
        "error_type": log.log_entry.error_type,
        "error_message": log.log_entry.error_message,
        "stack_trace": log.log_entry.stack_trace,
        "attributes": log.log_entry.attributes,
        "sdk_version": log.log_entry.sdk_version,
        "platform": log.log_entry.platform,
        "platform_version": log.log_entry.platform_version,
        "error_fingerprint": log.error_fingerprint,
    }
    return msgpack.packb(payload, use_bin_type=True)


async def enqueue_log(enriched_log: schemas.EnrichedLogEntry) -> None:
    pool = await rabbitmq_client.get_channel_pool()

    async with pool.acquire() as channel:
        exchange = await channel.get_exchange(config.settings.RABBITMQ_EXCHANGE)
        try:
            await exchange.publish(
                aio_pika.Message(
                    body=_build_payload(enriched_log),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=f"logs.{enriched_log.project_id}",
            )
        except aio_pika.exceptions.DeliveryError as e:
            raise QueueFullError(
                f"Queue full for project {enriched_log.project_id}: broker rejected message"
            ) from e


async def enqueue_logs_batch(enriched_logs: list[schemas.EnrichedLogEntry]) -> None:
    if not enriched_logs:
        return

    pool = await rabbitmq_client.get_channel_pool()

    async with pool.acquire() as channel:
        exchange = await channel.get_exchange(config.settings.RABBITMQ_EXCHANGE)
        for log in enriched_logs:
            try:
                await exchange.publish(
                    aio_pika.Message(
                        body=_build_payload(log),
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key=f"logs.{log.project_id}",
                )
            except aio_pika.exceptions.DeliveryError as e:
                raise QueueFullError(
                    f"Queue full for project {log.project_id}: broker rejected message"
                ) from e


async def get_queue_depth(project_id: int) -> int:
    pool = await rabbitmq_client.get_channel_pool()

    async with pool.acquire() as channel:
        queue = await channel.declare_queue(
            config.settings.RABBITMQ_QUEUE,
            passive=True,
        )
        return queue.declaration_result.message_count
