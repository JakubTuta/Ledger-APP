import asyncio
import datetime
import hashlib
import json
import logging
import signal
import sys
import time
import typing

import aio_pika
import aio_pika.abc
import msgpack

import ingestion_service.config as config
import ingestion_service.database as database
import ingestion_service.notifications as notifications
import ingestion_service.services.db_errors as db_errors
import ingestion_service.services.ip_country as ip_country
import ingestion_service.services.partition_manager as partition_manager
import ingestion_service.services.partition_scheduler as partition_scheduler
import ingestion_service.services.rabbitmq_client as rabbitmq_client
import ingestion_service.services.redis_client as redis_client
import ingestion_service.services.self_monitoring as self_monitoring

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
    "client_channel",
    "client_country",
    "resource_hash",
    "service_name",
    "trace_id",
    "span_id",
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
        log_id VARCHAR(64),
        client_channel VARCHAR(20),
        client_country CHAR(2),
        resource_hash BIGINT,
        service_name VARCHAR(255),
        trace_id CHAR(32),
        span_id CHAR(16)
    ) ON COMMIT DELETE ROWS
"""

_LOGS_COPY_COLUMNS_SQL = ", ".join(_LOG_COPY_COLUMNS)
_LOG_JSON_COLUMNS = frozenset({"attributes"})

# Aggregate phase timing is logged every N flushes rather than per-flush, so it's
# cheap enough to leave on permanently and still gives an accurate on-CPU-vs-DB-wait
# breakdown of process_logs_batch under real load.
_TIMING_LOG_EVERY = 50

# While the database is unreachable a worker holds its batch (unacked, so
# RabbitMQ keeps it and stops delivering more) and retries with backoff. Past
# the budget the batch takes the regular per-message/drop path, so a
# misclassified permanent error cannot stall a worker forever.
_DB_RETRY_INITIAL_DELAY_SECONDS = 1.0
_DB_RETRY_MAX_DELAY_SECONDS = 30.0
_DB_RETRY_BUDGET_SECONDS = 15 * 60


class _WorkerStoppingError(Exception):
    """Shutdown arrived while waiting for the database; the batch goes back to the queue."""


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
    "resource_hash",
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
        error_fingerprint CHAR(64),
        resource_hash     BIGINT
    ) ON COMMIT DELETE ROWS
"""

_SPANS_COPY_COLUMNS_SQL = ", ".join(_SPAN_COPY_COLUMNS)
_SPAN_JSON_COLUMNS = frozenset({"attributes", "events"})

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
    "temporality",
    "resource_hash",
    "exp_histogram",
    "quantiles",
    "exemplars",
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
        service_name    TEXT,
        temporality     SMALLINT,
        resource_hash   BIGINT,
        exp_histogram   JSONB,
        quantiles       JSONB,
        exemplars       JSONB
    ) ON COMMIT DELETE ROWS
"""

_METRIC_POINTS_COPY_COLUMNS_SQL = ", ".join(_METRIC_POINT_COPY_COLUMNS)
_METRIC_POINT_JSON_COLUMNS = frozenset(
    {"bucket_counts", "explicit_bounds", "tags", "exp_histogram", "quantiles", "exemplars"}
)

# Resources are stored once per (project, resource_hash). last_seen drives
# retention, so it is refreshed - at most daily, to keep the hot path from
# rewriting the row on every batch.
_RESOURCE_UPSERT_SQL = """
    INSERT INTO resources (project_id, resource_hash, attributes, first_seen, last_seen)
    VALUES ($1, $2, $3::jsonb, $4, $4)
    ON CONFLICT (project_id, resource_hash) DO UPDATE SET last_seen = EXCLUDED.last_seen
    WHERE resources.last_seen < EXCLUDED.last_seen - INTERVAL '1 day'
"""

# A worker re-upserts a resource it already wrote at most this often; the
# upsert itself is what keeps last_seen (and so the row) alive.
_RESOURCE_RECHECK_SECONDS = 3600
_RESOURCE_CACHE_MAX_ENTRIES = 100_000

_ERROR_GROUP_UPSERT_SQL = """
    INSERT INTO error_groups
        (project_id, fingerprint, error_type, error_message, first_seen, last_seen,
         occurrence_count, sample_stack_trace, status, created_at, updated_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'unresolved', $9, $9)
    ON CONFLICT (project_id, fingerprint) DO UPDATE SET
        last_seen = EXCLUDED.last_seen,
        occurrence_count = error_groups.occurrence_count + EXCLUDED.occurrence_count,
        updated_at = $9
"""


def _fallback_log_id(record: dict) -> str:
    # blake2b/16-hex (64 bits), not sha256/64-hex (256 bits): log_id is
    # non-NULL for every row that reaches here (this is the fallback path),
    # which makes idx_logs_dedup's WHERE log_id IS NOT NULL predicate
    # non-selective - the index is effectively full-width and randomly keyed.
    # A 64-bit fallback id keeps redelivery dedup working (still astronomically
    # unlikely to collide for one message) while roughly quartering the index's
    # per-row key size. No migration needed - log_id is VARCHAR(64), so
    # existing 64-hex-char sha256 ids stay valid alongside new 16-char ones.
    # Accepted per this project's tolerance for a rare duplicate/missing row at
    # log-analytics volumes (see CLAUDE.md's ingestion durability notes).
    # Envelopes queued before trace ids got their own fields carry them in
    # the attributes instead.
    attributes = record.get("attributes") or {}
    trace_id = record.get("trace_id") or attributes.get("trace_id") or ""
    span_id = record.get("span_id") or attributes.get("span_id") or ""
    source = (
        f"{record['project_id']}:{record['timestamp'].isoformat()}:"
        f"{record.get('message') or ''}:{trace_id}:{span_id}"
    )
    return hashlib.blake2b(source.encode(), digest_size=8).hexdigest()


def _copy_value(value: object, is_json: bool) -> object:
    # SQLAlchemy's asyncpg dialect installs its own jsonb codec on every
    # connection, and that codec expects an already-serialized str (it just
    # prefixes the jsonb version byte). Serialize here rather than re-binding a
    # dict-aware codec per batch: asyncpg's set_type_codec introspects pg_type
    # on each call, which is a round trip on the hottest path in the system.
    if is_json and value is not None and not isinstance(value, str):
        return json.dumps(value)
    return value


async def _copy_via_staging(
    session,
    records: list[dict],
    staging_table: str,
    staging_ddl: str,
    target_table: str,
    columns: list[str],
    json_columns: frozenset[str],
    columns_sql: str,
    conflict_clause: str,
    timings: dict[str, float] | None = None,
) -> None:
    """
    Bulk-load `records` through a session-local staging table using asyncpg's
    binary COPY, then move them into `target_table` with the caller's
    ON CONFLICT clause.

    The staging tables are declared ON COMMIT DELETE ROWS rather than
    ON COMMIT DROP, so a pooled connection creates each one at most once and
    every later batch reuses it - repeatedly creating and dropping a temp table
    at ingestion rates bloats pg_class/pg_attribute.

    `timings`, if given, accumulates elapsed seconds under "staging_ddl_ms",
    "copy_records_ms", "insert_select_ms" - split out so profiling can tell
    apart the COPY itself from the ON CONFLICT dedup scan that follows it.
    """
    conn = await session.connection()
    raw_conn = await conn.get_raw_connection()
    asyncpg_conn = raw_conn.driver_connection

    rows = [
        tuple(_copy_value(record[column], column in json_columns) for column in columns)
        for record in records
    ]

    # A single explicit transaction is required here: each raw statement on this
    # connection would otherwise commit on its own, emptying the staging table
    # between the COPY and the INSERT ... SELECT that drains it.
    async with asyncpg_conn.transaction():
        t0 = time.perf_counter()
        await asyncpg_conn.execute(staging_ddl)
        t1 = time.perf_counter()
        await asyncpg_conn.copy_records_to_table(staging_table, records=rows, columns=columns)
        t2 = time.perf_counter()
        await asyncpg_conn.execute(
            f"INSERT INTO {target_table} ({columns_sql}) "
            f"SELECT {columns_sql} FROM {staging_table} {conflict_clause}"
        )
        t3 = time.perf_counter()

    if timings is not None:
        timings["staging_ddl_ms"] = timings.get("staging_ddl_ms", 0.0) + (t1 - t0) * 1000
        timings["copy_records_ms"] = timings.get("copy_records_ms", 0.0) + (t2 - t1) * 1000
        timings["insert_select_ms"] = timings.get("insert_select_ms", 0.0) + (t3 - t2) * 1000


def _resources_of(items: list[dict]) -> dict[tuple[int, int], str]:
    """(project_id, resource_hash) -> attributes JSON for the resources `items` use."""
    return {
        (item["project_id"], item["resource_hash"]): item["resource"]
        for item in items
        if item.get("resource") is not None
    }


# (project_id, resource_hash) -> monotonic time this process last upserted it.
# Shared by every worker in the process; only written after a commit, so a
# rolled-back batch never marks a resource as stored.
_resource_upserted_at: dict[tuple[int, int], float] = {}


def _resources_needing_upsert(resources: dict[tuple[int, int], str]) -> list[tuple]:
    now = time.monotonic()
    return sorted(
        (project_id, resource_hash, attributes)
        for (project_id, resource_hash), attributes in resources.items()
        if now - _resource_upserted_at.get((project_id, resource_hash), -1e18)
        > _RESOURCE_RECHECK_SECONDS
    )


async def _upsert_resources(session, pending: list[tuple]) -> None:
    # Sorted by key (see _resources_needing_upsert) so concurrent workers take
    # row locks in the same order.
    if not pending:
        return
    seen_at = datetime.datetime.now(datetime.timezone.utc)
    conn = await session.connection()
    raw_conn = await conn.get_raw_connection()
    await raw_conn.driver_connection.executemany(
        _RESOURCE_UPSERT_SQL,
        [
            (project_id, resource_hash, attributes, seen_at)
            for project_id, resource_hash, attributes in pending
        ],
    )


def _mark_resources_stored(pending: list[tuple]) -> None:
    if len(_resource_upserted_at) > _RESOURCE_CACHE_MAX_ENTRIES:
        _resource_upserted_at.clear()
    now = time.monotonic()
    for project_id, resource_hash, _attributes in pending:
        _resource_upserted_at[(project_id, resource_hash)] = now


def _attach_resources(items: list[dict], payload: dict) -> None:
    """Point each item at its resource's attributes JSON (shared, not copied)."""
    resources = {
        resource_hash: attributes for resource_hash, attributes in payload.get("resources") or []
    }
    if not resources:
        return
    for item in items:
        resource_hash = item.get("resource_hash")
        if resource_hash is not None:
            item["resource"] = resources.get(resource_hash)


async def _copy_log_records(
    session, log_records: list[dict], timings: dict[str, float] | None = None
) -> None:
    await _copy_via_staging(
        session,
        log_records,
        staging_table="logs_staging",
        staging_ddl=_LOGS_STAGING_DDL,
        target_table="logs",
        columns=_LOG_COPY_COLUMNS,
        json_columns=_LOG_JSON_COLUMNS,
        columns_sql=_LOGS_COPY_COLUMNS_SQL,
        conflict_clause=(
            "ON CONFLICT (project_id, log_id, timestamp) WHERE log_id IS NOT NULL DO NOTHING"
        ),
        timings=timings,
    )


async def _copy_span_records(session, span_records: list[dict]) -> None:
    await _copy_via_staging(
        session,
        span_records,
        staging_table="spans_staging",
        staging_ddl=_SPANS_STAGING_DDL,
        target_table="spans",
        columns=_SPAN_COPY_COLUMNS,
        json_columns=_SPAN_JSON_COLUMNS,
        columns_sql=_SPANS_COPY_COLUMNS_SQL,
        conflict_clause="ON CONFLICT (span_id, start_time) DO NOTHING",
    )


async def _copy_metric_points(session, metric_point_records: list[dict]) -> None:
    await _copy_via_staging(
        session,
        metric_point_records,
        staging_table="metric_points_staging",
        staging_ddl=_METRIC_POINTS_STAGING_DDL,
        target_table="metric_points",
        columns=_METRIC_POINT_COPY_COLUMNS,
        json_columns=_METRIC_POINT_JSON_COLUMNS,
        columns_sql=_METRIC_POINTS_COPY_COLUMNS_SQL,
        conflict_clause="ON CONFLICT (project_id, name, tags_hash, ts) DO NOTHING",
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
        self._timing_totals: dict[str, float] = {}
        self._timing_flushes = 0
        self._timing_logs = 0

    def _record_batch_timing(self, logs_in_batch: int, phase_ms: dict[str, float]) -> None:
        for key, value in phase_ms.items():
            self._timing_totals[key] = self._timing_totals.get(key, 0.0) + value
        self._timing_flushes += 1
        self._timing_logs += logs_in_batch

        if self._timing_flushes % _TIMING_LOG_EVERY == 0:
            parts = ", ".join(
                f"{key}={value:.1f}ms" for key, value in sorted(self._timing_totals.items())
            )
            logger.info(
                f"Worker {self.worker_id}: phase timing over last {self._timing_flushes} "
                f"flushes ({self._timing_logs} logs): {parts}"
            )
            self._timing_totals = {}
            self._timing_flushes = 0
            self._timing_logs = 0

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

        client_country = log_data.get("client_country")
        if client_country is None and attributes:
            ip_prefix = (attributes.get("client") or {}).get("ip_prefix")
            if ip_prefix:
                client_country = ip_country.get_lookup().lookup(ip_prefix)

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
            "client_channel": log_data.get("client_channel"),
            "client_country": client_country,
            "resource_hash": log_data.get("resource_hash"),
            "service_name": log_data.get("service_name"),
            "trace_id": log_data.get("trace_id"),
            "span_id": log_data.get("span_id"),
        }
        record["log_id"] = log_data.get("log_id") or _fallback_log_id(record)
        return record, timestamp.date()

    async def process_logs_batch(self, logs: list[dict]) -> None:
        if not logs:
            return

        phase_ms: dict[str, float] = {}
        t_start = time.perf_counter()

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

        pending_resources = _resources_needing_upsert(_resources_of(logs))

        t_build = time.perf_counter()
        phase_ms["build_ms"] = (t_build - t_start) * 1000

        async with database.get_session() as session:
            for partition_date in required_partitions:
                await partition_manager.ensure_partition_for_date(session, "logs", partition_date)

            t_partition = time.perf_counter()
            phase_ms["partition_ms"] = (t_partition - t_build) * 1000

            await _upsert_resources(session, pending_resources)
            await _copy_log_records(session, log_records, timings=phase_ms)

            t_copy = time.perf_counter()

            if error_groups:
                await self._upsert_error_groups_batch(session, list(error_groups.values()))

            t_errgroup = time.perf_counter()
            phase_ms["errgroup_ms"] = (t_errgroup - t_copy) * 1000

            await session.commit()
            _mark_resources_stored(pending_resources)
            self.processed_count += len(logs)

            t_commit = time.perf_counter()
            phase_ms["commit_ms"] = (t_commit - t_errgroup) * 1000

        await self._publish_tail(log_records)

        t_tail = time.perf_counter()
        phase_ms["tail_ms"] = (t_tail - t_commit) * 1000

        self._record_batch_timing(len(logs), phase_ms)

    async def _publish_tail(self, log_records: list[dict]) -> None:
        # Best-effort, and deliberately swallows its own failures: it runs after
        # the batch has already been committed, so letting an exception escape
        # would send _flush_batch down the per-message retry path and re-run
        # process_logs_batch on rows that are already stored. The COPY dedups on
        # log_id, but the error_groups upsert does not - it would add the same
        # occurrences a second time.
        by_project: dict[int, list[dict]] = {}
        for record in log_records:
            by_project.setdefault(record["project_id"], []).append(record)
        for project_id, records in by_project.items():
            try:
                await self.tail_publisher.publish_tail_batch(project_id, records)
            except Exception as e:
                logger.error(
                    f"Worker {self.worker_id}: tail publish failed for project {project_id}: {e}",
                    exc_info=True,
                )

    async def _upsert_error_groups_batch(self, session, groups: list[dict]) -> None:
        # Sort by conflict key so concurrent workers acquire row locks in the same
        # order; otherwise multi-row upserts touching the same fingerprints from
        # different batches can lock-order deadlock against each other.
        groups = sorted(groups, key=lambda g: (g["project_id"], g["fingerprint"]))

        # Raw asyncpg with a fixed single-row statement, not SQLAlchemy Core's
        # pg_insert(...).values(groups): a profile under sustained load showed
        # 50%+ of the worker's on-CPU time inside the SQL compiler visitor chain
        # (_compiler_dispatch/visit_bindparam/...) because the ORM statement's
        # VALUES clause has a different row count on almost every batch (one row
        # per distinct fingerprint seen), which misses SQLAlchemy's compiled-
        # statement cache and forces a full recompile every call. A statement
        # with a fixed shape reuses asyncpg's client-side prepared-statement
        # cache across calls on the same pooled connection instead.
        # Set explicitly rather than leaning on either schema's DEFAULT NOW():
        # the Alembic-migrated DB has one on created_at/updated_at, but the
        # test DB's ORM-generated schema (metadata.create_all(), no
        # server_default on these Python-side-default columns) doesn't - so
        # relying on it would make correctness depend on which of the two
        # schema-creation paths built the table.
        now = datetime.datetime.now(datetime.timezone.utc)

        conn = await session.connection()
        raw_conn = await conn.get_raw_connection()
        asyncpg_conn = raw_conn.driver_connection
        await asyncpg_conn.executemany(
            _ERROR_GROUP_UPSERT_SQL,
            [
                (
                    g["project_id"],
                    g["fingerprint"],
                    g["error_type"],
                    g["error_message"],
                    g["first_seen"],
                    g["last_seen"],
                    g["occurrence_count"],
                    g["sample_stack_trace"],
                    now,
                )
                for g in groups
            ],
        )

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
            "resource_hash": span_data.get("resource_hash"),
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

        pending_resources = _resources_needing_upsert(_resources_of(spans))

        async with database.get_session() as session:
            for partition_date in required_partitions:
                await partition_manager.ensure_partition_for_date(session, "spans", partition_date)

            await _upsert_resources(session, pending_resources)
            await _copy_span_records(session, span_records)

            await session.commit()
            _mark_resources_stored(pending_resources)
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
            "temporality": point_data.get("temporality") or None,
            "resource_hash": point_data.get("resource_hash"),
            "exp_histogram": point_data.get("exp_histogram"),
            "quantiles": point_data.get("quantiles"),
            "exemplars": point_data.get("exemplars"),
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

        pending_resources = _resources_needing_upsert(_resources_of(points))

        async with database.get_session() as session:
            for partition_date in required_partitions:
                await partition_manager.ensure_partition_for_date(
                    session, "metric_points", partition_date
                )

            await _upsert_resources(session, pending_resources)
            await _copy_metric_points(session, point_records)

            await session.commit()
            _mark_resources_stored(pending_resources)
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
        _attach_resources(logs, payload)
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
        _attach_resources(spans, payload)
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
        _attach_resources(points, payload)
        return points

    async def _flush_batch(
        self,
        messages: list[aio_pika.abc.AbstractIncomingMessage],
        message_logs: list[list[dict]],
    ) -> None:
        await self._flush(messages, message_logs, self.process_logs_batch, "logs")

    async def _flush_spans_batch(
        self,
        messages: list[aio_pika.abc.AbstractIncomingMessage],
        message_spans: list[list[dict]],
    ) -> None:
        await self._flush(messages, message_spans, self.process_spans_batch, "spans")

    async def _flush_metrics_batch(
        self,
        messages: list[aio_pika.abc.AbstractIncomingMessage],
        message_points: list[list[dict]],
    ) -> None:
        await self._flush(
            messages, message_points, self.process_metric_points_batch, "metric points"
        )

    async def _flush(
        self,
        messages: list[aio_pika.abc.AbstractIncomingMessage],
        message_items: list[list[dict]],
        process: typing.Callable[[list[dict]], typing.Awaitable[None]],
        kind: str,
    ) -> None:
        """Store one batch of envelopes, then ack them.

        A database that is down, restarting or out of connection slots says
        nothing about the data, so those failures are retried with backoff and
        the messages stay unacked (consumption pauses, the queue absorbs the
        backlog). Any other failure falls back to per-message processing so one
        bad envelope only costs itself, and is dropped after one retry.
        """
        payloads = [item for items in message_items for item in items]
        signal_tag = {"signal": kind.replace(" ", "_")}
        started = time.perf_counter()
        try:
            await self._process_until_db_available(process, payloads)
            await messages[-1].ack(multiple=True)
            self_monitoring.increment("ledger.storage.rows", len(payloads), signal_tag)
            self_monitoring.record(
                "ledger.storage.batch_ms", (time.perf_counter() - started) * 1000, signal_tag
            )
            logger.debug(
                f"Worker {self.worker_id}: ACKed batch of {len(messages)} messages "
                f"({len(payloads)} {kind})"
            )
            return
        except _WorkerStoppingError:
            await self._requeue(messages)
            return
        except Exception as e:
            logger.error(
                f"Worker {self.worker_id}: {kind} batch of {len(messages)} messages failed, "
                f"falling back to per-message: {e}",
            )

        for index, (message, items) in enumerate(zip(messages, message_items)):
            try:
                await self._process_with_one_retry(process, items, kind)
                await message.ack()
                self_monitoring.increment("ledger.storage.rows", len(items), signal_tag)
            except _WorkerStoppingError:
                await self._requeue(messages[index:])
                return
            except Exception as retry_err:
                logger.error(
                    f"Worker {self.worker_id}: {kind} message failed after retry, "
                    f"dropping: {retry_err}",
                )
                self.failed_count += len(items)
                self_monitoring.increment("ledger.storage.dropped", len(items), signal_tag)
                await message.nack(requeue=False)

    async def _process_with_one_retry(
        self,
        process: typing.Callable[[list[dict]], typing.Awaitable[None]],
        items: list[dict],
        kind: str,
    ) -> None:
        try:
            await self._process_until_db_available(process, items)
        except _WorkerStoppingError:
            raise
        except Exception as first_err:
            logger.warning(
                f"Worker {self.worker_id}: {kind} message failed, retrying once: {first_err}"
            )
            await self._process_until_db_available(process, items)

    async def _process_until_db_available(
        self,
        process: typing.Callable[[list[dict]], typing.Awaitable[None]],
        items: list[dict],
    ) -> None:
        """Run `process`, waiting out database outages for up to _DB_RETRY_BUDGET_SECONDS."""
        delay = _DB_RETRY_INITIAL_DELAY_SECONDS
        deadline = time.monotonic() + _DB_RETRY_BUDGET_SECONDS
        while True:
            try:
                await process(items)
                return
            except Exception as e:
                if not db_errors.is_transient(e) or time.monotonic() >= deadline:
                    raise
                if not self.running:
                    raise _WorkerStoppingError from e
                logger.warning(
                    f"Worker {self.worker_id}: database unavailable, retrying in {delay:.0f}s: {e}"
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, _DB_RETRY_MAX_DELAY_SECONDS)

    async def _requeue(self, messages: list[aio_pika.abc.AbstractIncomingMessage]) -> None:
        for message in messages:
            await message.nack(requeue=True)

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


_ip_country_refresh_task: asyncio.Task | None = None


async def _refresh_ip_country_loop() -> None:
    while True:
        await asyncio.sleep(config.settings.IP_COUNTRY_REFRESH_INTERVAL_SECONDS)
        try:
            async with database.get_session() as session:
                await ip_country.reload_from_db(session)
        except Exception as e:
            logger.error(f"Failed to refresh ip_country table: {e}", exc_info=True)


async def main():
    self_monitoring.start("ingestion-worker")
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

    try:
        async with database.get_session() as session:
            await ip_country.reload_from_db(session)
    except Exception as e:
        logger.error(f"Failed to load ip_country table: {e}", exc_info=True)
        logger.warning("Worker will continue; country resolution will yield NULL until it loads")

    # Held in a module global rather than a bare create_task(): asyncio only
    # keeps a weak reference to a running task, so an unreferenced one can be
    # garbage collected mid-await and stop refreshing silently. Holding it also
    # lets shutdown() cancel the loop before the DB pool is closed under it.
    global _ip_country_refresh_task
    _ip_country_refresh_task = asyncio.create_task(_refresh_ip_country_loop())

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

    if _ip_country_refresh_task is not None:
        _ip_country_refresh_task.cancel()

    if config.settings.ENABLE_PARTITION_SCHEDULER:
        scheduler = partition_scheduler.get_partition_scheduler()
        scheduler.stop()

    await rabbitmq_client.close()
    await database.close_db()
    self_monitoring.stop()
    sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
