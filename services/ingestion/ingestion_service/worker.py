import asyncio
import datetime
import hashlib
import json
import logging
import signal
import sys

import aio_pika
import aio_pika.abc
import msgpack

import ingestion_service.config as config
import ingestion_service.database as database
import ingestion_service.models as models
import ingestion_service.notifications as notifications
import ingestion_service.services.partition_manager as partition_manager
import ingestion_service.services.partition_scheduler as partition_scheduler
import ingestion_service.services.rabbitmq_client as rabbitmq_client
import ingestion_service.services.redis_client as redis_client
from sqlalchemy.dialects.postgresql import insert as pg_insert

logging.basicConfig(
    level=getattr(logging, config.settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

_LOG_COPY_COLUMNS = [
    "project_id",
    "timestamp",
    "ingested_at",
    "level",
    "log_type",
    "importance",
    "environment",
    "release",
    "message",
    "error_type",
    "error_message",
    "stack_trace",
    "attributes",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "sdk_version",
    "platform",
    "platform_version",
    "error_fingerprint",
    "log_id",
]

_LOGS_STAGING_DDL = """
    CREATE TEMP TABLE IF NOT EXISTS logs_staging (
        project_id BIGINT,
        timestamp TIMESTAMPTZ,
        ingested_at TIMESTAMPTZ,
        level VARCHAR(20),
        log_type VARCHAR(30),
        importance VARCHAR(20),
        environment VARCHAR(20),
        release VARCHAR(100),
        message TEXT,
        error_type VARCHAR(255),
        error_message TEXT,
        stack_trace TEXT,
        attributes JSONB,
        method VARCHAR(8),
        path VARCHAR(2048),
        status_code SMALLINT,
        duration_ms INTEGER,
        sdk_version VARCHAR(20),
        platform VARCHAR(50),
        platform_version VARCHAR(50),
        error_fingerprint CHAR(64),
        log_id VARCHAR(64)
    ) ON COMMIT DROP
"""

_LOGS_COPY_COLUMNS_SQL = ", ".join(_LOG_COPY_COLUMNS)

_SPAN_COPY_COLUMNS = [
    "span_id",
    "trace_id",
    "parent_span_id",
    "project_id",
    "service_name",
    "name",
    "kind",
    "start_time",
    "duration_ns",
    "status_code",
    "status_message",
    "attributes",
    "events",
    "error_fingerprint",
]

_SPANS_STAGING_DDL = """
    CREATE TEMP TABLE IF NOT EXISTS spans_staging (
        span_id           CHAR(16),
        trace_id          CHAR(32),
        parent_span_id    CHAR(16),
        project_id        BIGINT,
        service_name      TEXT,
        name              TEXT,
        kind              SMALLINT,
        start_time        TIMESTAMPTZ,
        duration_ns       BIGINT,
        status_code       SMALLINT,
        status_message    TEXT,
        attributes        JSONB,
        events            JSONB,
        error_fingerprint CHAR(64)
    ) ON COMMIT DROP
"""

_SPANS_COPY_COLUMNS_SQL = ", ".join(_SPAN_COPY_COLUMNS)

_METRIC_POINT_COPY_COLUMNS = [
    "project_id",
    "name",
    "type",
    "ts",
    "value",
    "count",
    "sum",
    "bucket_counts",
    "explicit_bounds",
    "tags",
    "tags_hash",
    "service_name",
]

_METRIC_POINTS_STAGING_DDL = """
    CREATE TEMP TABLE IF NOT EXISTS metric_points_staging (
        project_id      BIGINT,
        name            TEXT,
        type            SMALLINT,
        ts              TIMESTAMPTZ,
        value           DOUBLE PRECISION,
        count           BIGINT,
        sum             DOUBLE PRECISION,
        bucket_counts   JSONB,
        explicit_bounds JSONB,
        tags            JSONB,
        tags_hash       CHAR(16),
        service_name    TEXT
    ) ON COMMIT DROP
"""

_METRIC_POINTS_COPY_COLUMNS_SQL = ", ".join(_METRIC_POINT_COPY_COLUMNS)


def _encode_jsonb(value: object) -> bytes:
    text = value if isinstance(value, str) else json.dumps(value)
    return b"\x01" + text.encode("utf-8")


def _decode_jsonb(data: bytes) -> object:
    return json.loads(data[1:].decode("utf-8"))


def _fallback_log_id(record: dict) -> str:
    attributes = record.get("attributes") or {}
    source = (
        f"{record['project_id']}:{record['timestamp'].isoformat()}:"
        f"{record.get('message') or ''}:"
        f"{attributes.get('trace_id') or ''}:{attributes.get('span_id') or ''}"
    )
    return hashlib.sha256(source.encode()).hexdigest()


async def _copy_log_records(session, log_records: list[dict]) -> None:
    conn = await session.connection()
    raw_conn = await conn.get_raw_connection()
    asyncpg_conn = raw_conn.driver_connection

    await asyncpg_conn.set_type_codec(
        "jsonb",
        encoder=_encode_jsonb,
        decoder=_decode_jsonb,
        schema="pg_catalog",
        format="binary",
    )

    rows = [tuple(record[column] for column in _LOG_COPY_COLUMNS) for record in log_records]

    # A single explicit transaction is required here: each raw statement on this
    # connection auto-commits on its own otherwise, which would trigger the staging
    # table's ON COMMIT DROP right after CREATE, before TRUNCATE/COPY/INSERT can run.
    async with asyncpg_conn.transaction():
        await asyncpg_conn.execute(_LOGS_STAGING_DDL)
        await asyncpg_conn.execute("TRUNCATE logs_staging")
        await asyncpg_conn.copy_records_to_table(
            "logs_staging", records=rows, columns=_LOG_COPY_COLUMNS
        )
        await asyncpg_conn.execute(
            f"INSERT INTO logs ({_LOGS_COPY_COLUMNS_SQL}) "
            f"SELECT {_LOGS_COPY_COLUMNS_SQL} FROM logs_staging "
            f"ON CONFLICT (project_id, log_id, timestamp) WHERE log_id IS NOT NULL DO NOTHING"
        )


async def _copy_span_records(session, span_records: list[dict]) -> None:
    conn = await session.connection()
    raw_conn = await conn.get_raw_connection()
    asyncpg_conn = raw_conn.driver_connection

    await asyncpg_conn.set_type_codec(
        "jsonb",
        encoder=_encode_jsonb,
        decoder=_decode_jsonb,
        schema="pg_catalog",
        format="binary",
    )

    rows = [tuple(record[column] for column in _SPAN_COPY_COLUMNS) for record in span_records]

    # Same explicit-transaction requirement as _copy_log_records: without it each
    # raw statement auto-commits on its own, which fires the staging table's
    # ON COMMIT DROP before TRUNCATE/COPY/INSERT get a chance to run.
    async with asyncpg_conn.transaction():
        await asyncpg_conn.execute(_SPANS_STAGING_DDL)
        await asyncpg_conn.execute("TRUNCATE spans_staging")
        await asyncpg_conn.copy_records_to_table(
            "spans_staging", records=rows, columns=_SPAN_COPY_COLUMNS
        )
        await asyncpg_conn.execute(
            f"INSERT INTO spans ({_SPANS_COPY_COLUMNS_SQL}) "
            f"SELECT {_SPANS_COPY_COLUMNS_SQL} FROM spans_staging "
            f"ON CONFLICT (span_id, start_time) DO NOTHING"
        )


async def _copy_metric_points(session, metric_point_records: list[dict]) -> None:
    conn = await session.connection()
    raw_conn = await conn.get_raw_connection()
    asyncpg_conn = raw_conn.driver_connection

    await asyncpg_conn.set_type_codec(
        "jsonb",
        encoder=_encode_jsonb,
        decoder=_decode_jsonb,
        schema="pg_catalog",
        format="binary",
    )

    rows = [
        tuple(record[column] for column in _METRIC_POINT_COPY_COLUMNS)
        for record in metric_point_records
    ]

    # Same explicit-transaction requirement as _copy_log_records/_copy_span_records:
    # without it each raw statement auto-commits on its own, which fires the
    # staging table's ON COMMIT DROP before TRUNCATE/COPY/INSERT get a chance to run.
    async with asyncpg_conn.transaction():
        await asyncpg_conn.execute(_METRIC_POINTS_STAGING_DDL)
        await asyncpg_conn.execute("TRUNCATE metric_points_staging")
        await asyncpg_conn.copy_records_to_table(
            "metric_points_staging", records=rows, columns=_METRIC_POINT_COPY_COLUMNS
        )
        await asyncpg_conn.execute(
            f"INSERT INTO metric_points ({_METRIC_POINTS_COPY_COLUMNS_SQL}) "
            f"SELECT {_METRIC_POINTS_COPY_COLUMNS_SQL} FROM metric_points_staging "
            f"ON CONFLICT (project_id, name, tags_hash, ts) DO NOTHING"
        )


class StorageWorker:
    def __init__(self, worker_id: int):
        self.worker_id = worker_id
        self.running = False
        self.processed_count = 0
        self.failed_count = 0
        self.tail_publisher = notifications.TailPublisher(
            redis_client.get_redis_client(), enabled=config.settings.NOTIFICATIONS_ENABLED
        )

    @staticmethod
    def _build_log_record(log_data: dict) -> tuple[dict, datetime.date]:
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

        record = {
            "project_id": log_data["project_id"],
            "timestamp": timestamp,
            "ingested_at": datetime.datetime.fromisoformat(log_data["ingested_at"]),
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
        record["log_id"] = log_data.get("log_id") or _fallback_log_id(record)
        return record, timestamp.date()

    async def process_logs_batch(self, logs: list[dict]) -> None:
        if not logs:
            return

        log_records: list[dict] = []
        required_partitions: set[datetime.date] = set()
        error_groups: dict[tuple[int, str], dict] = {}

        for log_data in logs:
            record, partition_date = self._build_log_record(log_data)
            log_records.append(record)
            required_partitions.add(partition_date)

            fp = log_data.get("error_fingerprint")
            if fp:
                key = (log_data["project_id"], fp)
                ts = datetime.datetime.fromisoformat(log_data["timestamp"])
                if key not in error_groups:
                    error_groups[key] = {
                        "project_id": log_data["project_id"],
                        "fingerprint": fp,
                        "error_type": log_data.get("error_type", "UnknownError"),
                        "error_message": log_data.get("error_message"),
                        "first_seen": ts,
                        "last_seen": ts,
                        "occurrence_count": 1,
                        "sample_stack_trace": log_data.get("stack_trace"),
                    }
                else:
                    eg = error_groups[key]
                    eg["occurrence_count"] += 1
                    if ts < eg["first_seen"]:
                        eg["first_seen"] = ts
                    if ts > eg["last_seen"]:
                        eg["last_seen"] = ts

        async with database.get_session() as session:
            for partition_date in required_partitions:
                await partition_manager.ensure_partition_for_date(session, "logs", partition_date)

            await _copy_log_records(session, log_records)

            if error_groups:
                await self._upsert_error_groups_batch(session, list(error_groups.values()))

            await session.commit()
            self.processed_count += len(logs)

        await self._publish_tail(log_records)

    async def _publish_tail(self, log_records: list[dict]) -> None:
        by_project: dict[int, list[dict]] = {}
        for record in log_records:
            by_project.setdefault(record["project_id"], []).append(record)
        for project_id, records in by_project.items():
            await self.tail_publisher.publish_tail_batch(project_id, records)

    async def _upsert_error_groups_batch(self, session, groups: list[dict]) -> None:
        # Sort by conflict key so concurrent workers acquire row locks in the same
        # order; otherwise multi-row upserts touching the same fingerprints from
        # different batches can lock-order deadlock against each other.
        groups = sorted(groups, key=lambda g: (g["project_id"], g["fingerprint"]))
        stmt = pg_insert(models.ErrorGroup).values(groups)
        stmt = stmt.on_conflict_do_update(
            index_elements=["project_id", "fingerprint"],
            set_={
                "last_seen": stmt.excluded.last_seen,
                "occurrence_count": (
                    models.ErrorGroup.occurrence_count + stmt.excluded.occurrence_count
                ),
                "updated_at": datetime.datetime.now(datetime.timezone.utc),
            },
        )
        await session.execute(stmt)

    @staticmethod
    def _build_span_record(span_data: dict) -> tuple[dict, datetime.date]:
        start_time = datetime.datetime.fromisoformat(span_data["start_time"])

        record = {
            "span_id": span_data["span_id"],
            "trace_id": span_data["trace_id"],
            "parent_span_id": span_data.get("parent_span_id"),
            "project_id": span_data["project_id"],
            "service_name": span_data.get("service_name"),
            "name": span_data.get("name"),
            "kind": span_data.get("kind", 0),
            "start_time": start_time,
            "duration_ns": span_data.get("duration_ns", 0),
            "status_code": span_data.get("status_code", 0),
            "status_message": span_data.get("status_message"),
            "attributes": span_data.get("attributes") or {},
            "events": span_data.get("events"),
            "error_fingerprint": span_data.get("error_fingerprint"),
        }
        return record, start_time.date()

    async def process_spans_batch(self, spans: list[dict]) -> None:
        if not spans:
            return

        span_records: list[dict] = []
        required_partitions: set[datetime.date] = set()

        for span_data in spans:
            record, partition_date = self._build_span_record(span_data)
            span_records.append(record)
            required_partitions.add(partition_date)

        async with database.get_session() as session:
            for partition_date in required_partitions:
                await partition_manager.ensure_partition_for_date(session, "spans", partition_date)

            await _copy_span_records(session, span_records)

            await session.commit()
            self.processed_count += len(spans)

    @staticmethod
    def _build_metric_point_record(point_data: dict) -> tuple[dict, datetime.date]:
        ts = datetime.datetime.fromisoformat(point_data["ts"])

        record = {
            "project_id": point_data["project_id"],
            "name": point_data["name"],
            "type": point_data.get("type", 0),
            "ts": ts,
            "value": point_data.get("value"),
            "count": point_data.get("count"),
            "sum": point_data.get("sum"),
            "bucket_counts": point_data.get("bucket_counts"),
            "explicit_bounds": point_data.get("explicit_bounds"),
            "tags": point_data.get("tags") or {},
            "tags_hash": point_data["tags_hash"],
            "service_name": point_data.get("service_name"),
        }
        return record, ts.date()

    async def process_metric_points_batch(self, points: list[dict]) -> None:
        if not points:
            return

        point_records: list[dict] = []
        required_partitions: set[datetime.date] = set()

        for point_data in points:
            record, partition_date = self._build_metric_point_record(point_data)
            point_records.append(record)
            required_partitions.add(partition_date)

        async with database.get_session() as session:
            for partition_date in required_partitions:
                await partition_manager.ensure_partition_for_date(
                    session, "metric_points", partition_date
                )

            await _copy_metric_points(session, point_records)

            await session.commit()
            self.processed_count += len(points)

    @staticmethod
    def _decode_message(message: aio_pika.abc.AbstractIncomingMessage) -> list[dict]:
        payload = msgpack.unpackb(message.body, raw=False)
        if not isinstance(payload, dict) or "logs" not in payload:
            raise ValueError(
                f"Malformed log envelope: expected dict with 'logs' key, got {type(payload)}"
            )
        project_id = payload.get("project_id")
        logs = payload["logs"]
        if project_id is not None:
            for log in logs:
                log.setdefault("project_id", project_id)
        return logs

    @staticmethod
    def _decode_spans_message(message: aio_pika.abc.AbstractIncomingMessage) -> list[dict]:
        payload = msgpack.unpackb(message.body, raw=False)
        if not isinstance(payload, dict) or "spans" not in payload:
            raise ValueError(
                f"Malformed span envelope: expected dict with 'spans' key, got {type(payload)}"
            )
        project_id = payload.get("project_id")
        spans = payload["spans"]
        if project_id is not None:
            for span in spans:
                span.setdefault("project_id", project_id)
        return spans

    @staticmethod
    def _decode_metrics_message(message: aio_pika.abc.AbstractIncomingMessage) -> list[dict]:
        payload = msgpack.unpackb(message.body, raw=False)
        if not isinstance(payload, dict) or "points" not in payload:
            raise ValueError(
                f"Malformed metric envelope: expected dict with 'points' key, got {type(payload)}"
            )
        project_id = payload.get("project_id")
        points = payload["points"]
        if project_id is not None:
            for point in points:
                point.setdefault("project_id", project_id)
        return points

    async def _flush_batch(
        self,
        messages: list[aio_pika.abc.AbstractIncomingMessage],
        message_logs: list[list[dict]],
    ) -> None:
        payloads = [log for logs in message_logs for log in logs]
        try:
            await self.process_logs_batch(payloads)
            await messages[-1].ack(multiple=True)
            logger.debug(
                f"Worker {self.worker_id}: ACKed batch of {len(messages)} messages "
                f"({len(payloads)} logs)"
            )
        except Exception as e:
            logger.error(
                f"Worker {self.worker_id}: Batch of {len(messages)} messages failed, "
                f"falling back to per-message: {e}",
            )
            for message, logs in zip(messages, message_logs):
                try:
                    await self.process_logs_batch(logs)
                    await message.ack()
                except Exception as per_msg_err:
                    logger.warning(
                        f"Worker {self.worker_id}: Message failed, retrying once: {per_msg_err}",
                    )
                    try:
                        await self.process_logs_batch(logs)
                        await message.ack()
                    except Exception as retry_err:
                        logger.error(
                            f"Worker {self.worker_id}: Message failed after retry, dropping: {retry_err}",
                        )
                        self.failed_count += len(logs)
                        await message.nack(requeue=False)

    async def _flush_spans_batch(
        self,
        messages: list[aio_pika.abc.AbstractIncomingMessage],
        message_spans: list[list[dict]],
    ) -> None:
        payloads = [span for spans in message_spans for span in spans]
        try:
            await self.process_spans_batch(payloads)
            await messages[-1].ack(multiple=True)
            logger.debug(
                f"Worker {self.worker_id}: ACKed batch of {len(messages)} messages "
                f"({len(payloads)} spans)"
            )
        except Exception as e:
            logger.error(
                f"Worker {self.worker_id}: Span batch of {len(messages)} messages failed, "
                f"falling back to per-message: {e}",
            )
            for message, spans in zip(messages, message_spans):
                try:
                    await self.process_spans_batch(spans)
                    await message.ack()
                except Exception as per_msg_err:
                    logger.warning(
                        f"Worker {self.worker_id}: Span message failed, retrying once: {per_msg_err}",
                    )
                    try:
                        await self.process_spans_batch(spans)
                        await message.ack()
                    except Exception as retry_err:
                        logger.error(
                            f"Worker {self.worker_id}: Span message failed after retry, dropping: {retry_err}",
                        )
                        self.failed_count += len(spans)
                        await message.nack(requeue=False)

    async def _flush_metrics_batch(
        self,
        messages: list[aio_pika.abc.AbstractIncomingMessage],
        message_points: list[list[dict]],
    ) -> None:
        payloads = [point for points in message_points for point in points]
        try:
            await self.process_metric_points_batch(payloads)
            await messages[-1].ack(multiple=True)
            logger.debug(
                f"Worker {self.worker_id}: ACKed batch of {len(messages)} messages "
                f"({len(payloads)} metric points)"
            )
        except Exception as e:
            logger.error(
                f"Worker {self.worker_id}: Metric points batch of {len(messages)} "
                f"messages failed, falling back to per-message: {e}",
            )
            for message, points in zip(messages, message_points):
                try:
                    await self.process_metric_points_batch(points)
                    await message.ack()
                except Exception as per_msg_err:
                    logger.warning(
                        f"Worker {self.worker_id}: Metric points message failed, "
                        f"retrying once: {per_msg_err}",
                    )
                    try:
                        await self.process_metric_points_batch(points)
                        await message.ack()
                    except Exception as retry_err:
                        logger.error(
                            f"Worker {self.worker_id}: Metric points message failed after "
                            f"retry, dropping: {retry_err}",
                        )
                        self.failed_count += len(points)
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

        message_buffer: asyncio.Queue[aio_pika.abc.AbstractIncomingMessage] = asyncio.Queue()

        async def on_message(
            message: aio_pika.abc.AbstractIncomingMessage,
        ) -> None:
            await message_buffer.put(message)

        consumer_tag = await queue.consume(on_message)
        logger.info(f"Worker {self.worker_id}: consuming from {config.settings.RABBITMQ_QUEUE}")

        try:
            while self.running:
                batch_messages: list[aio_pika.abc.AbstractIncomingMessage] = []
                batch_message_logs: list[list[dict]] = []
                batch_log_count = 0

                try:
                    first_message = await asyncio.wait_for(
                        message_buffer.get(),
                        timeout=config.settings.BATCH_FLUSH_INTERVAL,
                    )
                except asyncio.TimeoutError:
                    continue

                try:
                    logs = self._decode_message(first_message)
                    batch_messages.append(first_message)
                    batch_message_logs.append(logs)
                    batch_log_count += len(logs)
                except Exception as e:
                    logger.error(f"Worker {self.worker_id}: Failed to decode message: {e}")
                    await first_message.nack(requeue=False)
                    continue

                while batch_log_count < config.settings.QUEUE_BATCH_SIZE:
                    try:
                        message = message_buffer.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    try:
                        logs = self._decode_message(message)
                        batch_messages.append(message)
                        batch_message_logs.append(logs)
                        batch_log_count += len(logs)
                    except Exception as e:
                        logger.error(f"Worker {self.worker_id}: Failed to decode message: {e}")
                        await message.nack(requeue=False)

                if batch_messages:
                    await self._flush_batch(batch_messages, batch_message_logs)

        finally:
            await queue.cancel(consumer_tag)
            await channel.close()

    async def run_spans(self) -> None:
        # Mirrors run() exactly, but against the dedicated spans queue/decoder/
        # flush path. Kept as a parallel method (rather than parameterizing run())
        # so the two message types stay independently readable and debuggable.
        self.running = True

        connection = await rabbitmq_client.get_connection()
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=config.settings.RABBITMQ_PREFETCH_COUNT)

        queue = await channel.declare_queue(
            config.settings.RABBITMQ_SPANS_QUEUE,
            passive=True,
        )

        message_buffer: asyncio.Queue[aio_pika.abc.AbstractIncomingMessage] = asyncio.Queue()

        async def on_message(
            message: aio_pika.abc.AbstractIncomingMessage,
        ) -> None:
            await message_buffer.put(message)

        consumer_tag = await queue.consume(on_message)
        logger.info(
            f"Worker {self.worker_id}: consuming from {config.settings.RABBITMQ_SPANS_QUEUE}"
        )

        try:
            while self.running:
                batch_messages: list[aio_pika.abc.AbstractIncomingMessage] = []
                batch_message_spans: list[list[dict]] = []
                batch_span_count = 0

                try:
                    first_message = await asyncio.wait_for(
                        message_buffer.get(),
                        timeout=config.settings.BATCH_FLUSH_INTERVAL,
                    )
                except asyncio.TimeoutError:
                    continue

                try:
                    spans = self._decode_spans_message(first_message)
                    batch_messages.append(first_message)
                    batch_message_spans.append(spans)
                    batch_span_count += len(spans)
                except Exception as e:
                    logger.error(f"Worker {self.worker_id}: Failed to decode span message: {e}")
                    await first_message.nack(requeue=False)
                    continue

                while batch_span_count < config.settings.QUEUE_BATCH_SIZE:
                    try:
                        message = message_buffer.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    try:
                        spans = self._decode_spans_message(message)
                        batch_messages.append(message)
                        batch_message_spans.append(spans)
                        batch_span_count += len(spans)
                    except Exception as e:
                        logger.error(f"Worker {self.worker_id}: Failed to decode span message: {e}")
                        await message.nack(requeue=False)

                if batch_messages:
                    await self._flush_spans_batch(batch_messages, batch_message_spans)

        finally:
            await queue.cancel(consumer_tag)
            await channel.close()

    async def run_metrics(self) -> None:
        # Mirrors run_spans() exactly, but against the dedicated metrics queue/
        # decoder/flush path. Kept as a parallel method so the three message
        # types stay independently readable, debuggable, and scalable.
        self.running = True

        connection = await rabbitmq_client.get_connection()
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=config.settings.RABBITMQ_PREFETCH_COUNT)

        queue = await channel.declare_queue(
            config.settings.RABBITMQ_METRICS_QUEUE,
            passive=True,
        )

        message_buffer: asyncio.Queue[aio_pika.abc.AbstractIncomingMessage] = asyncio.Queue()

        async def on_message(
            message: aio_pika.abc.AbstractIncomingMessage,
        ) -> None:
            await message_buffer.put(message)

        consumer_tag = await queue.consume(on_message)
        logger.info(
            f"Worker {self.worker_id}: consuming from {config.settings.RABBITMQ_METRICS_QUEUE}"
        )

        try:
            while self.running:
                batch_messages: list[aio_pika.abc.AbstractIncomingMessage] = []
                batch_message_points: list[list[dict]] = []
                batch_point_count = 0

                try:
                    first_message = await asyncio.wait_for(
                        message_buffer.get(),
                        timeout=config.settings.BATCH_FLUSH_INTERVAL,
                    )
                except asyncio.TimeoutError:
                    continue

                try:
                    points = self._decode_metrics_message(first_message)
                    batch_messages.append(first_message)
                    batch_message_points.append(points)
                    batch_point_count += len(points)
                except Exception as e:
                    logger.error(
                        f"Worker {self.worker_id}: Failed to decode metric point message: {e}"
                    )
                    await first_message.nack(requeue=False)
                    continue

                while batch_point_count < config.settings.QUEUE_BATCH_SIZE:
                    try:
                        message = message_buffer.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    try:
                        points = self._decode_metrics_message(message)
                        batch_messages.append(message)
                        batch_message_points.append(points)
                        batch_point_count += len(points)
                    except Exception as e:
                        logger.error(
                            f"Worker {self.worker_id}: Failed to decode metric point message: {e}"
                        )
                        await message.nack(requeue=False)

                if batch_messages:
                    await self._flush_metrics_batch(batch_messages, batch_message_points)

        finally:
            await queue.cancel(consumer_tag)
            await channel.close()

    async def stop(self) -> None:
        self.running = False


class WorkerManager:
    def __init__(self, worker_count: int, run_method: str = "run"):
        self.worker_count = worker_count
        self.run_method = run_method
        self.workers: list[StorageWorker] = []
        self.tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        for i in range(self.worker_count):
            worker = StorageWorker(worker_id=i)
            self.workers.append(worker)

            task = asyncio.create_task(getattr(worker, self.run_method)())
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
    # Spans and metric points each get their own small dedicated worker pool
    # (WORKER_SPANS_COUNT / WORKER_METRICS_COUNT, default 2) rather than folding
    # extra consume loops into each log worker instance: it keeps WorkerManager
    # reusable as-is and lets the three traffic classes scale and fail
    # independently (a stuck/slow consumer on one queue can't starve the others).
    spans_manager = WorkerManager(
        worker_count=config.settings.WORKER_SPANS_COUNT, run_method="run_spans"
    )
    metrics_manager = WorkerManager(
        worker_count=config.settings.WORKER_METRICS_COUNT, run_method="run_metrics"
    )

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.ensure_future(shutdown(manager, spans_manager, metrics_manager)),
        )

    await manager.start()
    await spans_manager.start()
    await metrics_manager.start()

    while True:
        await asyncio.sleep(1)


async def shutdown(
    manager: WorkerManager,
    spans_manager: WorkerManager,
    metrics_manager: WorkerManager,
):
    await manager.stop()
    await spans_manager.stop()
    await metrics_manager.stop()

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
