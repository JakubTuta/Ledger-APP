import logging

import aio_pika
import aio_pika.pool

import ingestion_service.config as config

logger = logging.getLogger(__name__)

_connection: aio_pika.abc.AbstractRobustConnection | None = None
_channel_pool: aio_pika.pool.Pool | None = None


async def get_connection() -> aio_pika.abc.AbstractRobustConnection:
    global _connection
    if _connection is None or _connection.is_closed:
        _connection = await aio_pika.connect_robust(
            config.settings.RABBITMQ_URL,
            reconnect_interval=5,
            heartbeat=120,
        )
        logger.info("RabbitMQ connection established")
    return _connection


async def _create_publish_channel() -> aio_pika.abc.AbstractChannel:
    connection = await get_connection()
    return await connection.channel(publisher_confirms=True)


async def get_channel_pool() -> aio_pika.pool.Pool:
    global _channel_pool
    if _channel_pool is None:
        _channel_pool = aio_pika.pool.Pool(
            _create_publish_channel,
            max_size=config.settings.RABBITMQ_CHANNEL_POOL_SIZE,
        )
    return _channel_pool


async def setup_topology() -> None:
    connection = await get_connection()

    async with connection.channel() as channel:
        exchange = await channel.declare_exchange(
            config.settings.RABBITMQ_EXCHANGE,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        queue = await channel.declare_queue(
            config.settings.RABBITMQ_QUEUE,
            durable=True,
            arguments={
                "x-max-length": config.settings.QUEUE_MAX_DEPTH,
                "x-overflow": "reject-publish",
            },
        )
        await queue.bind(exchange, routing_key="logs.*")

        # Spans reuse the existing "logs" topic exchange (routing is keyed off the
        # binding, not the exchange identity) but get their own queue so span
        # traffic can't crowd out log traffic in the shared queue depth budget.
        spans_queue = await channel.declare_queue(
            config.settings.RABBITMQ_SPANS_QUEUE,
            durable=True,
            arguments={
                "x-max-length": config.settings.QUEUE_MAX_DEPTH,
                "x-overflow": "reject-publish",
            },
        )
        await spans_queue.bind(exchange, routing_key="spans.*")

        # Metric points get the same treatment as spans: their own queue on the
        # shared "logs" topic exchange, so a stuck/slow metrics consumer or a
        # burst of metric traffic can't crowd out log or span consumption.
        metrics_queue = await channel.declare_queue(
            config.settings.RABBITMQ_METRICS_QUEUE,
            durable=True,
            arguments={
                "x-max-length": config.settings.QUEUE_MAX_DEPTH,
                "x-overflow": "reject-publish",
            },
        )
        await metrics_queue.bind(exchange, routing_key="metrics.*")

    logger.info(
        "RabbitMQ topology ready: exchange=%s queue=%s spans_queue=%s metrics_queue=%s",
        config.settings.RABBITMQ_EXCHANGE,
        config.settings.RABBITMQ_QUEUE,
        config.settings.RABBITMQ_SPANS_QUEUE,
        config.settings.RABBITMQ_METRICS_QUEUE,
    )


async def close() -> None:
    global _connection, _channel_pool
    if _channel_pool is not None:
        await _channel_pool.close()
        _channel_pool = None
    if _connection is not None and not _connection.is_closed:
        await _connection.close()
        _connection = None
    logger.info("RabbitMQ connection closed")
