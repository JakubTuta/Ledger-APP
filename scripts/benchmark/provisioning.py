import asyncio
import hashlib
import json
import uuid

import asyncpg
import httpx

import config as benchmark_config


async def provision(
    client: httpx.AsyncClient,
    cfg: benchmark_config.BenchmarkConfig,
) -> tuple[str, int, str]:
    """
    Creates a fresh account/project/api-key via REST, then raises limits in Auth DB.
    Returns (full_key, project_id, email).
    """
    email = f"bench-{uuid.uuid4().hex[:12]}@bench.local"
    password = "BenchPass123"

    r = await client.post(
        f"{cfg.base_url}/api/v1/accounts/register",
        json={"email": email, "password": password, "name": "Benchmark Runner"},
    )
    r.raise_for_status()
    reg_data = r.json()
    access_token: str = reg_data["access_token"]

    auth_headers = {"Authorization": f"Bearer {access_token}"}
    slug = f"bench-{uuid.uuid4().hex[:12]}"
    r = await client.post(
        f"{cfg.base_url}/api/v1/projects",
        headers=auth_headers,
        json={"name": f"Benchmark {slug}", "slug": slug, "environment": "production"},
    )
    r.raise_for_status()
    project_id: int = r.json()["project_id"]

    r = await client.post(
        f"{cfg.base_url}/api/v1/projects/{project_id}/api-keys",
        headers=auth_headers,
        json={"name": "benchmark"},
    )
    r.raise_for_status()
    full_key: str = r.json()["full_key"]

    if not cfg.respect_limits:
        await _raise_limits(cfg, project_id, full_key)

    await _warmup_api_key(client, cfg, full_key)

    return full_key, project_id, email


async def _warmup_api_key(
    client: httpx.AsyncClient,
    cfg: benchmark_config.BenchmarkConfig,
    full_key: str,
) -> None:
    """
    Sends a single ingest request to prime the gateway's Redis cache for this API key.

    Gateway uses SETEX (STRING) and auth service uses HSET (HASH) on the same
    api_key:{hash} Redis key. Under concurrent first use, auth service can call
    HGETALL on a key the gateway just overwrote to STRING -> WRONGTYPE error.
    One serial warmup request ensures the key is cached as STRING before load starts.
    """
    warmup_log = {
        "logs": [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "level": "debug",
                "log_type": "console",
                "message": "benchmark warmup",
            }
        ]
    }
    headers = {
        "Authorization": f"Bearer {full_key}",
        "Content-Type": "application/json",
    }
    try:
        await client.post(
            f"{cfg.base_url}/api/v1/ingest/batch",
            content=json.dumps(warmup_log).encode(),
            headers=headers,
            timeout=15.0,
        )
    except Exception:
        pass
    await asyncio.sleep(0.5)


async def _raise_limits(
    cfg: benchmark_config.BenchmarkConfig,
    project_id: int,
    full_key: str,
) -> None:
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    conn = await asyncpg.connect(cfg.auth_db_dsn)
    try:
        await conn.execute(
            "UPDATE api_keys SET rate_limit_per_minute=$2, rate_limit_per_hour=$3 WHERE key_hash=$1",
            key_hash,
            cfg.per_minute_limit,
            cfg.per_hour_limit,
        )
        await conn.execute(
            "UPDATE projects SET daily_quota=$2 WHERE id=$1",
            project_id,
            cfg.daily_quota,
        )
    finally:
        await conn.close()


async def resolve_existing_key(
    cfg: benchmark_config.BenchmarkConfig,
    full_key: str,
) -> int:
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    conn = await asyncpg.connect(cfg.auth_db_dsn)
    try:
        row = await conn.fetchrow(
            "SELECT project_id FROM api_keys WHERE key_hash=$1 AND status='active'",
            key_hash,
        )
        if row is None:
            raise RuntimeError("No active API key found matching the provided key")
        return int(row["project_id"])
    finally:
        await conn.close()
