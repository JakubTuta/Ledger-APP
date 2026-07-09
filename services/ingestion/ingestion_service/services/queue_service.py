import logging

import aio_pika
import aio_pika.abc
import msgpack

import ingestion_service.config as config
import ingestion_service.schemas as schemas
import ingestion_service.services.rabbitmq_client as rabbitmq_client

logger = logging.getLogger(__name__)


class QueueFullError(Exception):
    pass


def _build_log_dict(log: schemas.EnrichedLogEntry) -> dict:
    return {
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
        "log_id": log.log_entry.log_id,
    }


def _build_envelope(project_id: int, logs: list[dict]) -> bytes:
    envelope = {"v": 1, "project_id": project_id, "logs": logs}
    return msgpack.packb(envelope, use_bin_type=True)


async def _publish_envelope(
    channel: aio_pika.abc.AbstractChannel,
    exchange: aio_pika.abc.AbstractExchange,
    project_id: int,
    logs: list[dict],
) -> None:
    try:
        await exchange.publish(
            aio_pika.Message(
                body=_build_envelope(project_id, logs),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=f"logs.{project_id}",
        )
    except aio_pika.exceptions.DeliveryError as e:
        raise QueueFullError(f"Queue full for project {project_id}: broker rejected message") from e


async def enqueue_log(enriched_log: schemas.EnrichedLogEntry) -> None:
    pool = await rabbitmq_client.get_channel_pool()

    async with pool.acquire() as channel:
        exchange = await channel.get_exchange(config.settings.RABBITMQ_EXCHANGE)
        await _publish_envelope(
            channel, exchange, enriched_log.project_id, [_build_log_dict(enriched_log)]
        )


async def enqueue_logs_batch(enriched_logs: list[schemas.EnrichedLogEntry]) -> None:
    if not enriched_logs:
        return

    pool = await rabbitmq_client.get_channel_pool()
    chunk_size = config.settings.RABBITMQ_ENVELOPE_MAX_LOGS

    by_project: dict[int, list[dict]] = {}
    for log in enriched_logs:
        by_project.setdefault(log.project_id, []).append(_build_log_dict(log))

    async with pool.acquire() as channel:
        exchange = await channel.get_exchange(config.settings.RABBITMQ_EXCHANGE)
        for project_id, logs in by_project.items():
            for i in range(0, len(logs), chunk_size):
                await _publish_envelope(channel, exchange, project_id, logs[i : i + chunk_size])


def _build_spans_envelope(project_id: int, spans: list[dict]) -> bytes:
    envelope = {"v": 1, "project_id": project_id, "spans": spans}
    return msgpack.packb(envelope, use_bin_type=True)


async def _publish_spans_envelope(
    channel: aio_pika.abc.AbstractChannel,
    exchange: aio_pika.abc.AbstractExchange,
    project_id: int,
    spans: list[dict],
) -> None:
    try:
        await exchange.publish(
            aio_pika.Message(
                body=_build_spans_envelope(project_id, spans),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=f"spans.{project_id}",
        )
    except aio_pika.exceptions.DeliveryError as e:
        raise QueueFullError(
            f"Spans queue full for project {project_id}: broker rejected message"
        ) from e


async def enqueue_spans_envelope(project_id: int, spans: list[dict]) -> None:
    if not spans:
        return

    pool = await rabbitmq_client.get_channel_pool()
    chunk_size = config.settings.RABBITMQ_ENVELOPE_MAX_SPANS

    async with pool.acquire() as channel:
        exchange = await channel.get_exchange(config.settings.RABBITMQ_EXCHANGE)
        for i in range(0, len(spans), chunk_size):
            await _publish_spans_envelope(channel, exchange, project_id, spans[i : i + chunk_size])


def _build_metrics_envelope(project_id: int, points: list[dict]) -> bytes:
    envelope = {"v": 1, "project_id": project_id, "points": points}
    return msgpack.packb(envelope, use_bin_type=True)


async def _publish_metrics_envelope(
    channel: aio_pika.abc.AbstractChannel,
    exchange: aio_pika.abc.AbstractExchange,
    project_id: int,
    points: list[dict],
) -> None:
    try:
        await exchange.publish(
            aio_pika.Message(
                body=_build_metrics_envelope(project_id, points),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=f"metrics.{project_id}",
        )
    except aio_pika.exceptions.DeliveryError as e:
        raise QueueFullError(
            f"Metrics queue full for project {project_id}: broker rejected message"
        ) from e


async def enqueue_metrics_envelope(project_id: int, points: list[dict]) -> None:
    if not points:
        return

    pool = await rabbitmq_client.get_channel_pool()
    chunk_size = config.settings.RABBITMQ_ENVELOPE_MAX_METRICS

    async with pool.acquire() as channel:
        exchange = await channel.get_exchange(config.settings.RABBITMQ_EXCHANGE)
        for i in range(0, len(points), chunk_size):
            await _publish_metrics_envelope(
                channel, exchange, project_id, points[i : i + chunk_size]
            )


async def get_queue_depth(project_id: int) -> int:
    pool = await rabbitmq_client.get_channel_pool()

    async with pool.acquire() as channel:
        queue = await channel.declare_queue(
            config.settings.RABBITMQ_QUEUE,
            passive=True,
        )
        return queue.declaration_result.message_count
