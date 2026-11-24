import re
import urllib.parse

import asyncpg

import config as benchmark_config
import models

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})
_BENCH_EMAIL = re.compile(r"bench-[0-9a-f]{12}@bench\.local")
_VACUUM_LOCK_TIMEOUT = "30s"

_PROJECT_TABLES_SQL = """
SELECT format('%I.%I', n.nspname, c.relname) AS name, c.relkind::text AS relkind
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'project_id' AND NOT a.attisdropped
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
ORDER BY c.relname
"""

_PARTITION_LEAVES_SQL = """
SELECT format('%I.%I', n.nspname, c.relname)
FROM pg_partition_tree($1::text::regclass) t
JOIN pg_class c ON c.oid = t.relid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE t.isleaf
"""


def _require_local_dsn(dsn: str, label: str) -> None:
    host = urllib.parse.urlparse(dsn).hostname
    if host not in _LOCAL_HOSTS:
        raise RuntimeError(f"cleanup refused: {label} DB host {host!r} is not the local dev stack")


def _rows_affected(command_status: str) -> int:
    return int(command_status.split()[-1])


async def _project_ids_of(auth_db_dsn: str, email: str) -> list[int]:
    conn = await asyncpg.connect(auth_db_dsn)
    try:
        rows = await conn.fetch(
            "SELECT p.id FROM projects p JOIN accounts a ON a.id = p.account_id WHERE a.email = $1",
            email,
        )
        return [int(row["id"]) for row in rows]
    finally:
        await conn.close()


async def _delete_project_rows(
    conn: asyncpg.Connection, project_ids: list[int]
) -> tuple[dict[str, int], list[asyncpg.Record]]:
    """Deletes the projects' rows from every Logs DB table that carries a project_id.

    Tables are discovered from the catalog so a table added later is covered without
    touching this module. Returns rows deleted per table and the tables that lost rows.
    """
    deleted: dict[str, int] = {}
    tables = await conn.fetch(_PROJECT_TABLES_SQL)
    async with conn.transaction():
        for table in tables:
            status = await conn.execute(
                f"DELETE FROM {table['name']} WHERE project_id = ANY($1::bigint[])", project_ids
            )
            count = _rows_affected(status)
            if count:
                deleted[table["name"]] = count
    shrunk = [table for table in tables if table["name"] in deleted]
    return deleted, shrunk


async def _vacuum_full(conn: asyncpg.Connection, table: asyncpg.Record) -> None:
    """Rewrites the table so the deleted rows' disk space goes back to the OS.

    A plain DELETE only marks rows dead; without this the bench data keeps its disk space.
    Partitioned tables are vacuumed leaf by leaf because VACUUM FULL takes an exclusive lock.
    """
    if table["relkind"] == "p":
        leaves = [row[0] for row in await conn.fetch(_PARTITION_LEAVES_SQL, table["name"])]
    else:
        leaves = [table["name"]]
    for leaf in leaves:
        await conn.execute(f"VACUUM (FULL) {leaf}")


async def _clean_logs_db(
    logs_db_dsn: str, project_ids: list[int]
) -> tuple[dict[str, int], int, int]:
    conn = await asyncpg.connect(logs_db_dsn)
    try:
        await conn.execute(f"SET lock_timeout = '{_VACUUM_LOCK_TIMEOUT}'")
        size_before = await conn.fetchval("SELECT pg_database_size(current_database())")
        deleted, shrunk_tables = await _delete_project_rows(conn, project_ids)
        for table in shrunk_tables:
            await _vacuum_full(conn, table)
        size_after = await conn.fetchval("SELECT pg_database_size(current_database())")
        return deleted, int(size_before), int(size_after)
    finally:
        await conn.close()


async def _delete_account(auth_db_dsn: str, email: str) -> None:
    """Projects, API keys, members and the rest cascade from the account row."""
    conn = await asyncpg.connect(auth_db_dsn)
    try:
        await conn.execute("DELETE FROM accounts WHERE email = $1", email)
    finally:
        await conn.close()


async def remove_provisioned_data(
    cfg: benchmark_config.BenchmarkConfig, email: str
) -> models.CleanupResult:
    """Removes everything a benchmark run provisioned: its account, projects and stored telemetry.

    Refuses anything that is not a benchmark-generated account on the local dev stack. Logs DB
    data goes first so a failure part-way leaves the account, and the project ids needed to
    retry, in place. Cached Redis entries for the key expire on their own TTL.
    """
    if _BENCH_EMAIL.fullmatch(email) is None:
        raise RuntimeError(f"cleanup refused: {email!r} is not a benchmark-provisioned account")
    _require_local_dsn(cfg.auth_db_dsn, "auth")
    _require_local_dsn(cfg.logs_db_dsn, "logs")

    project_ids = await _project_ids_of(cfg.auth_db_dsn, email)
    rows_deleted, size_before, size_after = await _clean_logs_db(cfg.logs_db_dsn, project_ids)
    await _delete_account(cfg.auth_db_dsn, email)
    return models.CleanupResult(
        email=email,
        project_ids=project_ids,
        rows_deleted=rows_deleted,
        logs_db_bytes_before=size_before,
        logs_db_bytes_after=size_after,
    )
