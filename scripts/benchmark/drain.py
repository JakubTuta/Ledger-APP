import asyncio
import datetime
import time

import aio_pika
import asyncpg
import httpx

import config as benchmark_config
import models


async def get_queue_depth_amqp(cfg: benchmark_config.BenchmarkConfig) -> int:
    """
    Passively declares the queue over AMQP and reads message_count directly off
    the queue process. Unlike the management HTTP API (below), this isn't a
    sampled stats-DB read, so it can't report 0 while envelopes are actually
    still in flight.
    """
    connection = await aio_pika.connect_robust(cfg.rabbitmq_amqp_url, timeout=10.0)
    try:
        channel = await connection.channel()
        queue = await channel.declare_queue(cfg.rabbitmq_queue, passive=True)
        return queue.declaration_result.message_count
    finally:
        await connection.close()


async def get_queue_depth_http(
    client: httpx.AsyncClient,
    cfg: benchmark_config.BenchmarkConfig,
) -> int:
    url = f"{cfg.rabbitmq_management_url}/api/queues/%2F/{cfg.rabbitmq_queue}"
    r = await client.get(
        url,
        auth=(cfg.rabbitmq_user, cfg.rabbitmq_password),
        timeout=10.0,
    )
    r.raise_for_status()
    data = r.json()
    return int(data.get("messages", 0))


async def get_queue_depth(
    client: httpx.AsyncClient,
    cfg: benchmark_config.BenchmarkConfig,
) -> int:
    try:
        return await get_queue_depth_amqp(cfg)
    except Exception:
        return await get_queue_depth_http(client, cfg)


async def wait_for_drain(
    client: httpx.AsyncClient,
    cfg: benchmark_config.BenchmarkConfig,
    timeout: float,
) -> models.DrainResult:
    depth_series: list[int] = []
    max_depth = 0
    zero_streak = 0
    start = time.monotonic()

    while True:
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            return models.DrainResult(
                drained=False,
                drain_seconds=elapsed,
                max_depth=max_depth,
                depth_series=depth_series,
            )

        try:
            depth = await get_queue_depth(client, cfg)
        except Exception:
            await asyncio.sleep(1.0)
            continue

        depth_series.append(depth)
        if depth > max_depth:
            max_depth = depth

        if depth <= 0:
            zero_streak += 1
            if zero_streak >= 3:
                return models.DrainResult(
                    drained=True,
                    drain_seconds=time.monotonic() - start,
                    max_depth=max_depth,
                    depth_series=depth_series,
                )
        else:
            zero_streak = 0

        await asyncio.sleep(0.5)


async def count_log_rows(
    logs_db_dsn: str,
    project_id: int,
    since_unix: float,
) -> int:
    since_dt = datetime.datetime.fromtimestamp(since_unix, tz=datetime.timezone.utc)
    conn = await asyncpg.connect(logs_db_dsn)
    try:
        row = await conn.fetchrow(
            "SELECT count(*) AS n FROM logs WHERE project_id=$1 AND ingested_at>=$2",
            project_id,
            since_dt,
        )
        return int(row["n"])
    finally:
        await conn.close()


async def count_log_rows_by_id_prefix(
    logs_db_dsn: str,
    project_id: int,
    run_id: str,
) -> int:
    """
    Exact-accounting verification for --log-id-mode client: every sent record
    carries `log_id = f"{run_id}-{seq}"`, so this is set arithmetic, not a
    time-window scan - immune to host/container clock skew and to any
    ingested_at drift between the benchmark client and the server.
    """
    conn = await asyncpg.connect(logs_db_dsn)
    try:
        row = await conn.fetchrow(
            "SELECT count(*) AS n FROM logs WHERE project_id=$1 AND log_id LIKE $2",
            project_id,
            f"{run_id}-%",
        )
        return int(row["n"])
    finally:
        await conn.close()


async def wait_for_stable_count(
    logs_db_dsn: str,
    project_id: int,
    run_id: str | None,
    since_unix: float,
    stable_reads: int = 3,
    interval_seconds: float = 0.5,
    timeout_seconds: float = 30.0,
) -> int:
    """
    Polls the row count until it stops changing (`stable_reads` identical reads
    in a row) rather than reading once immediately after drain - the worker's
    commit for the last flushed batch can land a few hundred ms after the
    queue reports empty.
    """
    start = time.monotonic()
    last: int | None = None
    streak = 0
    while time.monotonic() - start < timeout_seconds:
        if run_id is not None:
            current = await count_log_rows_by_id_prefix(logs_db_dsn, project_id, run_id)
        else:
            current = await count_log_rows(logs_db_dsn, project_id, since_unix)
        if current == last:
            streak += 1
            if streak >= stable_reads:
                return current
        else:
            streak = 0
        last = current
        await asyncio.sleep(interval_seconds)
    return last if last is not None else 0


async def get_table_growth_stats(
    logs_db_dsn: str,
    stage_started_at: float,
) -> models.TableGrowthStats:
    """
    `logs` and `idx_logs_dedup` are both partitioned (monthly RANGE partitions,
    one partitioned index propagated to each). A partitioned table/index has no
    storage of its own - pg_relation_size('logs') and
    pg_stat_user_tables.relname='logs' are always 0/absent. Every query here
    goes through pg_inherits to sum across the actual per-partition relations.
    """
    conn = await asyncpg.connect(logs_db_dsn)
    try:
        total_bytes = await conn.fetchval(
            "SELECT COALESCE(SUM(pg_total_relation_size(inhrelid)), 0) "
            "FROM pg_inherits WHERE inhparent = 'logs'::regclass"
        )
        index_bytes = await conn.fetchval(
            "SELECT COALESCE(SUM(pg_relation_size(inhrelid)), 0) "
            "FROM pg_inherits WHERE inhparent = 'idx_logs_dedup'::regclass"
        )
        hit_row = await conn.fetchrow(
            "SELECT COALESCE(SUM(s.idx_blks_hit), 0) AS hit, "
            "COALESCE(SUM(s.idx_blks_read), 0) AS read "
            "FROM pg_inherits i "
            "JOIN pg_statio_user_indexes s ON s.indexrelid = i.inhrelid "
            "WHERE i.inhparent = 'idx_logs_dedup'::regclass"
        )
        hit_ratio = None
        if hit_row is not None:
            hit, read = hit_row["hit"], hit_row["read"]
            total = (hit or 0) + (read or 0)
            hit_ratio = (hit / total) if total > 0 else None

        stage_start_dt = datetime.datetime.fromtimestamp(stage_started_at, tz=datetime.timezone.utc)
        autovacuum_ran = await conn.fetchval(
            "SELECT COALESCE(bool_or(t.last_autovacuum >= $1), false) "
            "FROM pg_inherits i "
            "JOIN pg_stat_user_tables t ON t.relid = i.inhrelid "
            "WHERE i.inhparent = 'logs'::regclass",
            stage_start_dt,
        )

        return models.TableGrowthStats(
            total_relation_bytes=int(total_bytes or 0),
            dedup_index_bytes=int(index_bytes or 0),
            dedup_index_hit_ratio=hit_ratio,
            autovacuum_ran_during_stage=bool(autovacuum_ran),
        )
    finally:
        await conn.close()


async def truncate_project_partitions(logs_db_dsn: str, project_id: int, expect_db: str) -> None:
    """
    Deletes this project's rows so repeated A/B stages start from the same
    table size. Guarded to refuse against anything that doesn't look like the
    local dev logs DB - this runs DELETE against a real table, not a scratch one.
    """
    if "localhost:5433" not in logs_db_dsn and "127.0.0.1:5433" not in logs_db_dsn:
        raise RuntimeError(
            "--destructive-reset refused: DSN host is not the local dev logs DB (:5433)"
        )
    if expect_db not in logs_db_dsn:
        raise RuntimeError(
            f"--destructive-reset refused: --expect-db={expect_db!r} not found in DSN"
        )
    conn = await asyncpg.connect(logs_db_dsn)
    try:
        await conn.execute("DELETE FROM logs WHERE project_id = $1", project_id)
        await conn.execute("DELETE FROM error_groups WHERE project_id = $1", project_id)
    finally:
        await conn.close()
