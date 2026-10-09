"""
Guards against an Alembic migration silently dropping/renaming an index or
constraint on the ingestion hot-path tables (logs/spans/metric_points/
error_groups), or a migration and ingestion_service/models.py drifting apart
on which columns exist.

Every other suite in this repo (ingestion's own tests, query-service's tests)
builds its schema from `ingestion_service.database.Base.metadata.create_all()`,
not from the Alembic migrations - see services/ingestion/tests/db_setup.py.
That path has no idea a migration exists at all, so `DROP INDEX idx_logs_dedup`
in a migration would pass the entire rest of the test suite. This test
migrates a real scratch database and inspects it directly.
"""

import asyncio

import asyncpg
import migration_service.config as migration_config
import migration_service.databases as databases
import migration_service.runner as runner
from sqlalchemy.engine import make_url

_SCRATCH_DB_NAME = "test_schema_parity_logs"

_HOT_PATH_TABLES = ("logs", "spans", "metric_points", "error_groups", "resources")

# Snapshot of `pg_indexes` for the hot-path tables at migration head 024.
# Update this alongside a migration that intentionally adds/drops/renames one
# of these indexes - and say so in the revision's message, since every index
# here is on the ingestion hot path and its removal/addition changes write cost.
_EXPECTED_INDEXES = {
    ("error_groups", "error_groups_pkey"): (
        "CREATE UNIQUE INDEX error_groups_pkey ON public.error_groups USING btree (id)"
    ),
    ("error_groups", "idx_error_groups_fingerprint"): (
        "CREATE UNIQUE INDEX idx_error_groups_fingerprint ON public.error_groups "
        "USING btree (project_id, fingerprint)"
    ),
    ("error_groups", "idx_error_groups_first_seen"): (
        "CREATE INDEX idx_error_groups_first_seen ON public.error_groups "
        "USING btree (project_id, first_seen DESC)"
    ),
    ("error_groups", "idx_error_groups_last_seen"): (
        "CREATE INDEX idx_error_groups_last_seen ON public.error_groups "
        "USING btree (project_id, last_seen DESC)"
    ),
    ("error_groups", "idx_error_groups_resolved"): (
        "CREATE INDEX idx_error_groups_resolved ON public.error_groups "
        "USING btree (project_id, resolved_at) WHERE (((status)::text = 'resolved'::text) "
        "AND (resolved_at IS NOT NULL))"
    ),
    ("error_groups", "idx_error_groups_status"): (
        "CREATE INDEX idx_error_groups_status ON public.error_groups "
        "USING btree (project_id, status, last_seen)"
    ),
    ("logs", "brin_logs_timestamp"): (
        'CREATE INDEX brin_logs_timestamp ON ONLY public.logs USING brin ("timestamp")'
    ),
    ("logs", "idx_logs_dedup"): (
        "CREATE UNIQUE INDEX idx_logs_dedup ON ONLY public.logs "
        'USING btree (project_id, log_id, "timestamp") WHERE (log_id IS NOT NULL)'
    ),
    ("logs", "idx_logs_error_fingerprint"): (
        "CREATE INDEX idx_logs_error_fingerprint ON ONLY public.logs "
        'USING btree (project_id, error_fingerprint, "timestamp" DESC) '
        "WHERE (error_fingerprint IS NOT NULL)"
    ),
    ("logs", "idx_logs_project_country"): (
        "CREATE INDEX idx_logs_project_country ON ONLY public.logs "
        'USING btree (project_id, "timestamp" DESC, client_country, client_channel) '
        "WHERE (client_country IS NOT NULL)"
    ),
    ("logs", "idx_logs_project_http"): (
        "CREATE INDEX idx_logs_project_http ON ONLY public.logs "
        'USING btree (project_id, "timestamp" DESC, status_code) '
        "WHERE (status_code IS NOT NULL)"
    ),
    ("logs", "idx_logs_project_level"): (
        "CREATE INDEX idx_logs_project_level ON ONLY public.logs "
        'USING btree (project_id, level, "timestamp" DESC) '
        "WHERE ((level)::text = ANY ((ARRAY['error'::character varying, "
        "'critical'::character varying])::text[]))"
    ),
    ("logs", "idx_logs_project_timestamp"): (
        "CREATE INDEX idx_logs_project_timestamp ON ONLY public.logs "
        'USING btree (project_id, "timestamp" DESC, id DESC)'
    ),
    ("logs", "logs_pkey"): (
        'CREATE UNIQUE INDEX logs_pkey ON ONLY public.logs USING btree (id, "timestamp")'
    ),
    ("metric_points", "brin_metric_points_ts"): (
        "CREATE INDEX brin_metric_points_ts ON ONLY public.metric_points USING brin (ts)"
    ),
    ("metric_points", "idx_metric_points_lookup"): (
        "CREATE INDEX idx_metric_points_lookup ON ONLY public.metric_points "
        "USING btree (project_id, name, ts DESC)"
    ),
    ("metric_points", "idx_metric_points_tags"): (
        "CREATE INDEX idx_metric_points_tags ON ONLY public.metric_points USING gin (tags)"
    ),
    ("metric_points", "metric_points_pkey"): (
        "CREATE UNIQUE INDEX metric_points_pkey ON ONLY public.metric_points "
        "USING btree (project_id, name, tags_hash, ts)"
    ),
    ("spans", "brin_spans_project_time"): (
        "CREATE INDEX brin_spans_project_time ON ONLY public.spans "
        "USING brin (project_id, start_time)"
    ),
    ("spans", "idx_spans_op"): (
        "CREATE INDEX idx_spans_op ON ONLY public.spans "
        "USING btree (project_id, service_name, name, start_time DESC)"
    ),
    ("spans", "idx_spans_project_trace"): (
        "CREATE INDEX idx_spans_project_trace ON ONLY public.spans "
        "USING btree (project_id, trace_id)"
    ),
    ("spans", "idx_spans_roots"): (
        "CREATE INDEX idx_spans_roots ON ONLY public.spans "
        "USING btree (project_id, start_time DESC) WHERE (parent_span_id IS NULL)"
    ),
    ("spans", "spans_pkey"): (
        "CREATE UNIQUE INDEX spans_pkey ON ONLY public.spans USING btree (span_id, start_time)"
    ),
    ("resources", "resources_pkey"): (
        "CREATE UNIQUE INDEX resources_pkey ON public.resources "
        "USING btree (project_id, resource_hash)"
    ),
}

# Snapshot of `pg_constraint` (contype: c=check, p=primary key) for the same
# tables. Unique indexes such as idx_logs_dedup are deliberately plain indexes,
# not table constraints, so they show up in _EXPECTED_INDEXES only.
_EXPECTED_CONSTRAINTS = {
    ("error_groups", "check_error_status"): "c",
    ("error_groups", "error_groups_pkey"): "p",
    ("logs", "check_importance"): "c",
    ("logs", "check_level"): "c",
    ("logs", "check_log_type"): "c",
    ("logs", "logs_pkey"): "p",
    ("metric_points", "metric_points_pkey"): "p",
    ("resources", "resources_pkey"): "p",
    ("spans", "spans_pkey"): "p",
}


def _connection_kwargs(target: databases.DatabaseTarget, database: str) -> dict:
    url = make_url(target.url)
    return {
        "host": url.host,
        "port": url.port,
        "user": url.username,
        "password": url.password,
        "database": database,
    }


async def _recreate_scratch_db(target: databases.DatabaseTarget) -> None:
    conn = await asyncpg.connect(**_connection_kwargs(target, "postgres"))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{_SCRATCH_DB_NAME}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{_SCRATCH_DB_NAME}"')
    finally:
        await conn.close()


async def _drop_scratch_db(target: databases.DatabaseTarget) -> None:
    conn = await asyncpg.connect(**_connection_kwargs(target, "postgres"))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{_SCRATCH_DB_NAME}" WITH (FORCE)')
    finally:
        await conn.close()


async def _fetch_indexes(target: databases.DatabaseTarget) -> dict[tuple[str, str], str]:
    conn = await asyncpg.connect(**_connection_kwargs(target, _SCRATCH_DB_NAME))
    try:
        rows = await conn.fetch(
            "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE tablename = ANY($1)",
            list(_HOT_PATH_TABLES),
        )
        return {(r["tablename"], r["indexname"]): r["indexdef"] for r in rows}
    finally:
        await conn.close()


async def _fetch_constraints(target: databases.DatabaseTarget) -> dict[tuple[str, str], str]:
    conn = await asyncpg.connect(**_connection_kwargs(target, _SCRATCH_DB_NAME))
    try:
        rows = await conn.fetch(
            "SELECT conrelid::regclass::text AS t, conname, contype::text AS ct "
            "FROM pg_constraint WHERE conrelid::regclass::text = ANY($1)",
            list(_HOT_PATH_TABLES),
        )
        return {(r["t"], r["conname"]): r["ct"] for r in rows}
    finally:
        await conn.close()


async def _fetch_db_columns(target: databases.DatabaseTarget, table: str) -> set[str]:
    conn = await asyncpg.connect(**_connection_kwargs(target, _SCRATCH_DB_NAME))
    try:
        rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = $1", table
        )
        return {r["column_name"] for r in rows}
    finally:
        await conn.close()


def test_migrated_schema_matches_index_and_constraint_snapshot(monkeypatch):
    target = databases.get_target("logs")
    monkeypatch.setattr(migration_config.settings, "LOGS_DB_NAME", _SCRATCH_DB_NAME)

    asyncio.run(_recreate_scratch_db(target))
    try:
        runner.upgrade(target, "head")

        actual_indexes = asyncio.run(_fetch_indexes(target))
        actual_constraints = asyncio.run(_fetch_constraints(target))

        missing_indexes = _EXPECTED_INDEXES.keys() - actual_indexes.keys()
        extra_indexes = actual_indexes.keys() - _EXPECTED_INDEXES.keys()
        assert not missing_indexes, f"Indexes dropped or renamed vs snapshot: {missing_indexes}"
        assert not extra_indexes, (
            f"New indexes not in snapshot: {extra_indexes}. If intentional, add them to "
            f"_EXPECTED_INDEXES in this file."
        )
        changed = {
            key: (_EXPECTED_INDEXES[key], actual_indexes[key])
            for key in _EXPECTED_INDEXES
            if _EXPECTED_INDEXES[key] != actual_indexes[key]
        }
        assert not changed, f"Index definitions changed vs snapshot: {changed}"

        assert actual_constraints == _EXPECTED_CONSTRAINTS
    finally:
        asyncio.run(_drop_scratch_db(target))


def test_migrated_schema_columns_match_orm_models(monkeypatch):
    target = databases.get_target("logs")
    monkeypatch.setattr(migration_config.settings, "LOGS_DB_NAME", _SCRATCH_DB_NAME)

    metadata = runner.load_metadata(target)
    if metadata is None:
        # Autogenerate/parity checks that need the owning service's models are
        # host-only (see DatabaseTarget.models_path) - the migration image
        # doesn't ship ingestion_service, so this is skipped there by design.
        import pytest

        pytest.skip(f"{target.models_module} not importable - not running from a repo checkout")

    asyncio.run(_recreate_scratch_db(target))
    try:
        runner.upgrade(target, "head")

        for table_name in _HOT_PATH_TABLES:
            db_columns = asyncio.run(_fetch_db_columns(target, table_name))
            orm_columns = set(metadata.tables[table_name].columns.keys())
            assert orm_columns == db_columns, (
                f"'{table_name}': ORM model columns {orm_columns} != migrated DB columns "
                f"{db_columns}. A migration added/removed a column without models.py "
                f"following, or vice versa."
            )
    finally:
        asyncio.run(_drop_scratch_db(target))
