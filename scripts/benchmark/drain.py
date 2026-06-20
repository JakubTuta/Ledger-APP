import asyncio
import datetime
import time

import asyncpg
import httpx

import config as benchmark_config
import models


async def get_queue_depth(
    client: httpx.AsyncClient,
    cfg: benchmark_config.BenchmarkConfig,
    api_key: str,
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


async def wait_for_drain(
    client: httpx.AsyncClient,
    cfg: benchmark_config.BenchmarkConfig,
    api_key: str,
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
            depth = await get_queue_depth(client, cfg, api_key)
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
