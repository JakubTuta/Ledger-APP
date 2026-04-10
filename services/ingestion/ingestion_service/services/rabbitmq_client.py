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
        )
        logger.info("RabbitMQ connection established")
    return _connection


async def _create_publish_channel() -> aio_pika.abc.AbstractChannel:
    connection = await get_connection()
    channel = await connection.channel()
    await channel.confirm_delivery()
    return channel


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
        dlx = await channel.declare_exchange(
            config.settings.RABBITMQ_DLX,
            aio_pika.ExchangeType.FANOUT,
            durable=True,
        )

        dlq = await channel.declare_queue(
            config.settings.RABBITMQ_DLQ,
            durable=True,
        )
        await dlq.bind(dlx)

        exchange = await channel.declare_exchange(
            config.settings.RABBITMQ_EXCHANGE,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        queue = await channel.declare_queue(
            config.settings.RABBITMQ_QUEUE,
            durable=True,
            arguments={
                "x-dead-letter-exchange": config.settings.RABBITMQ_DLX,
                "x-max-length": config.settings.QUEUE_MAX_DEPTH,
                "x-overflow": "reject-publish",
            },
        )
        await queue.bind(exchange, routing_key="logs.*")

    logger.info(
        "RabbitMQ topology ready: exchange=%s queue=%s dlx=%s dlq=%s",
        config.settings.RABBITMQ_EXCHANGE,
        config.settings.RABBITMQ_QUEUE,
        config.settings.RABBITMQ_DLX,
        config.settings.RABBITMQ_DLQ,
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
