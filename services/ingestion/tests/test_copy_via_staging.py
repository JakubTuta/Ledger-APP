import datetime

import pytest
import sqlalchemy
from ingestion_service import database, models
from ingestion_service.worker import (
    _LOG_COPY_COLUMNS,
    StorageWorker,
    _copy_log_records,
    _copy_value,
)

from .test_base import BaseIngestionTest


def _log_record(project_id: int = 1, message: str = "hello") -> dict:
    now = datetime.datetime.now(datetime.timezone.utc)
    log_data = {
        "project_id": project_id,
        "timestamp": now.isoformat(),
        "ingested_at": now.isoformat(),
        "level": "info",
        "log_type": "console",
        "importance": "standard",
        "message": message,
    }
    record, _partition_date = StorageWorker._build_log_record(log_data)
    return record


class TestCopyValue:
    """Pure unit tests, no DB needed."""

    def test_passes_already_serialized_str_through_untouched(self):
        raw = '{"already": "json"}'
        assert _copy_value(raw, is_json=True) is raw

    def test_serializes_dict_for_json_columns(self):
        import json

        value = {"a": 1, "b": [1, 2]}
        result = _copy_value(value, is_json=True)
        assert isinstance(result, str)
        assert json.loads(result) == value

    def test_none_passes_through_for_json_columns(self):
        assert _copy_value(None, is_json=True) is None

    def test_non_json_columns_pass_through_unchanged(self):
        assert _copy_value(5, is_json=False) == 5
        assert _copy_value("plain", is_json=False) == "plain"
        assert _copy_value(None, is_json=False) is None


class TestLogCopyColumnsCompleteness:
    """`_LOG_COPY_COLUMNS` is used as a set of dict-key lookups against
    `_build_log_record`'s output (`record[column] for column in columns`), not
    positionally - so a column present in one but not the other fails with a
    KeyError deep in the COPY path rather than at the call site. Catch that
    drift directly instead."""

    def test_every_copy_column_exists_on_a_built_record(self):
        record = _log_record()
        missing = [c for c in _LOG_COPY_COLUMNS if c not in record]
        assert not missing, (
            f"_LOG_COPY_COLUMNS references fields _build_log_record omits: {missing}"
        )

    def test_built_record_has_no_extra_fields_beyond_copy_columns(self):
        record = _log_record()
        extra = [k for k in record if k not in _LOG_COPY_COLUMNS]
        assert not extra, f"_build_log_record produces fields not in _LOG_COPY_COLUMNS: {extra}"


async def _raw_connection(session):
    """The test engine uses NullPool (services/ingestion/tests/db_setup.py) -
    every session.commit() physically closes the connection and the next
    checkout is a brand new one, so a temp table (connection-scoped) would
    silently vanish across a commit boundary. Grab the raw asyncpg connection
    once and query it directly, never through session.execute() again, so
    verification can't accidentally observe a different physical connection
    than the one _copy_via_staging just used."""
    conn = await session.connection()
    raw_conn = await conn.get_raw_connection()
    return raw_conn.driver_connection


@pytest.mark.asyncio
class TestCopyViaStagingInvariants(BaseIngestionTest):
    async def test_staging_table_empty_between_two_consecutive_flushes(self):
        """ON COMMIT DELETE ROWS must actually clear the staging table between
        batches on the same connection - the whole point of not using
        ON COMMIT DROP is that the table is reused, not recreated. This checks
        _copy_via_staging's own internal commit (inside `asyncpg_conn.transaction()`),
        which fires independent of whether the caller's SQLAlchemy session
        later commits too."""
        async with database.get_session() as session:
            asyncpg_conn = await _raw_connection(session)

            await _copy_log_records(session, [_log_record(message="first batch")])
            assert await asyncpg_conn.fetchval("SELECT count(*) FROM logs_staging") == 0

            await _copy_log_records(session, [_log_record(message="second batch")])
            assert await asyncpg_conn.fetchval("SELECT count(*) FROM logs_staging") == 0

            await session.commit()

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(sqlalchemy.select(sqlalchemy.func.count(models.Log.id)))
            assert result.scalar() == 2

    async def test_ten_flushes_reuse_the_same_staging_table(self):
        """Guards the ON COMMIT DELETE ROWS vs ON COMMIT DROP choice: repeatedly
        creating/dropping a temp table at ingestion rates bloats pg_class."""
        async with database.get_session() as session:
            asyncpg_conn = await _raw_connection(session)

            for i in range(10):
                await _copy_log_records(session, [_log_record(message=f"flush {i}")])

            relation_count = await asyncpg_conn.fetchval(
                "SELECT count(*) FROM pg_class WHERE relname = 'logs_staging' "
                "AND relnamespace = pg_my_temp_schema()"
            )
            assert relation_count == 1

            await session.commit()

    async def test_copy_and_insert_are_atomic_under_injected_failure(self):
        """A failure in the INSERT..SELECT half must roll back the COPY half -
        no rows land in `logs` from a batch that didn't fully commit."""
        record = _log_record(message="should not persist")

        async with database.get_session() as session:
            with pytest.raises(Exception):
                await _inject_failing_copy(session, record)

        async with self.test_db_manager.session_factory() as session:
            result = await session.execute(
                sqlalchemy.select(models.Log).where(models.Log.message == "should not persist")
            )
            assert result.scalars().first() is None


async def _inject_failing_copy(session, record: dict) -> None:
    """Same shape as `_copy_log_records`, but with a conflict clause that
    references a nonexistent column so the INSERT..SELECT half fails after the
    COPY half has already populated the staging table."""
    import ingestion_service.worker as worker_module

    await worker_module._copy_via_staging(
        session,
        [record],
        staging_table="logs_staging",
        staging_ddl=worker_module._LOGS_STAGING_DDL,
        target_table="logs",
        columns=worker_module._LOG_COPY_COLUMNS,
        json_columns=worker_module._LOG_JSON_COLUMNS,
        columns_sql=worker_module._LOGS_COPY_COLUMNS_SQL,
        conflict_clause="ON CONFLICT (project_id, this_column_does_not_exist) DO NOTHING",
    )
