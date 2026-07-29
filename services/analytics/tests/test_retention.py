import datetime
from unittest.mock import AsyncMock, patch

import pytest

import analytics_workers.jobs.retention as retention


class _FakeResult:
    def __init__(self, fetchall_value=None, rowcount=0):
        self._fetchall_value = fetchall_value or []
        self.rowcount = rowcount

    def fetchall(self):
        return self._fetchall_value


def _session_cm(mock_session):
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()
    return mock_session


@pytest.mark.asyncio
class TestEnforceRetention:
    async def test_no_projects_skips_enforcement(self):
        auth_session = AsyncMock()
        auth_session.execute = AsyncMock(return_value=_FakeResult(fetchall_value=[]))
        auth_session = _session_cm(auth_session)

        with patch("analytics_workers.database.get_auth_session", return_value=auth_session):
            with patch("analytics_workers.database.get_logs_session") as mock_logs:
                await retention.enforce_retention()
                mock_logs.assert_not_called()

    async def test_drops_partition_past_max_retention(self):
        auth_session = AsyncMock()
        auth_session.execute = AsyncMock(return_value=_FakeResult(fetchall_value=[(1, 30)]))
        auth_session = _session_cm(auth_session)

        old_month = (datetime.date.today() - datetime.timedelta(days=400)).strftime("%Y_%m")
        logs_session = AsyncMock()
        logs_session.execute = AsyncMock(
            side_effect=lambda query, params=None: (
                _FakeResult(fetchall_value=[(f"logs_{old_month}",)])
                if "pg_tables" in str(getattr(query, "text", query))
                else _FakeResult()
            )
        )
        logs_session = _session_cm(logs_session)

        with patch("analytics_workers.database.get_auth_session", return_value=auth_session):
            with patch("analytics_workers.database.get_logs_session", return_value=logs_session):
                await retention.enforce_retention()

        sqls = [
            str(getattr(c.args[0], "text", c.args[0])) for c in logs_session.execute.call_args_list
        ]
        assert any("DETACH PARTITION" in s for s in sqls)
        assert any("DROP TABLE IF EXISTS" in s for s in sqls)

    async def test_keeps_partition_within_retention(self):
        auth_session = AsyncMock()
        auth_session.execute = AsyncMock(return_value=_FakeResult(fetchall_value=[(1, 30)]))
        auth_session = _session_cm(auth_session)

        current_month = datetime.date.today().strftime("%Y_%m")
        logs_session = AsyncMock()
        logs_session.execute = AsyncMock(
            side_effect=lambda query, params=None: (
                _FakeResult(fetchall_value=[(f"logs_{current_month}",)])
                if "pg_tables" in str(getattr(query, "text", query))
                else _FakeResult()
            )
        )
        logs_session = _session_cm(logs_session)

        with patch("analytics_workers.database.get_auth_session", return_value=auth_session):
            with patch("analytics_workers.database.get_logs_session", return_value=logs_session):
                await retention.enforce_retention()

        sqls = [
            str(getattr(c.args[0], "text", c.args[0])) for c in logs_session.execute.call_args_list
        ]
        assert not any("DETACH PARTITION" in s for s in sqls)

    async def test_short_retention_project_gets_trimmed(self):
        auth_session = AsyncMock()
        auth_session.execute = AsyncMock(return_value=_FakeResult(fetchall_value=[(1, 90), (2, 7)]))
        auth_session = _session_cm(auth_session)

        call_log = []
        trim_marker = "DELETE FROM logs target"

        async def logs_execute(query, params=None):
            sql = str(getattr(query, "text", query))
            call_log.append((sql, params))
            if "pg_tables" in sql:
                return _FakeResult(fetchall_value=[])
            if trim_marker in sql and params.get("pid") == 2:
                # first call deletes a full batch, second call returns fewer than batch size
                deletes_so_far = sum(
                    1 for s, p in call_log if trim_marker in s and p.get("pid") == 2
                )
                return _FakeResult(
                    rowcount=retention._DELETE_BATCH_SIZE if deletes_so_far == 1 else 10
                )
            return _FakeResult()

        logs_session = AsyncMock()
        logs_session.execute = AsyncMock(side_effect=logs_execute)
        logs_session = _session_cm(logs_session)

        with patch("analytics_workers.database.get_auth_session", return_value=auth_session):
            with patch("analytics_workers.database.get_logs_session", return_value=logs_session):
                await retention.enforce_retention()

        trim_calls_pid2 = [p for s, p in call_log if trim_marker in s and p.get("pid") == 2]
        trim_calls_pid1 = [p for s, p in call_log if trim_marker in s and p.get("pid") == 1]
        assert len(trim_calls_pid2) == 2
        assert trim_calls_pid1 == []

    async def test_trim_batches_on_tableoid_and_ctid(self):
        """
        ctid alone is not unique across a partitioned table's partitions, so
        batching on it can delete a live row belonging to another partition
        (and another project).
        """
        auth_session = AsyncMock()
        auth_session.execute = AsyncMock(return_value=_FakeResult(fetchall_value=[(1, 90), (2, 7)]))
        auth_session = _session_cm(auth_session)

        logs_session = AsyncMock()
        logs_session.execute = AsyncMock(
            side_effect=lambda query, params=None: _FakeResult(
                fetchall_value=[] if "pg_tables" in str(getattr(query, "text", query)) else None
            )
        )
        logs_session = _session_cm(logs_session)

        with patch("analytics_workers.database.get_auth_session", return_value=auth_session):
            with patch("analytics_workers.database.get_logs_session", return_value=logs_session):
                await retention.enforce_retention()

        trim_sqls = [
            str(getattr(c.args[0], "text", c.args[0]))
            for c in logs_session.execute.call_args_list
            if "DELETE FROM logs target" in str(getattr(c.args[0], "text", c.args[0]))
        ]
        assert trim_sqls
        for sql in trim_sqls:
            assert "(target.tableoid, target.ctid)" in sql
            assert "source.tableoid, source.ctid" in sql

    async def test_prunes_error_groups_per_project_cutoff(self):
        auth_session = AsyncMock()
        auth_session.execute = AsyncMock(return_value=_FakeResult(fetchall_value=[(1, 30)]))
        auth_session = _session_cm(auth_session)

        logs_session = AsyncMock()
        logs_session.execute = AsyncMock(return_value=_FakeResult())
        logs_session = _session_cm(logs_session)

        with patch("analytics_workers.database.get_auth_session", return_value=auth_session):
            with patch("analytics_workers.database.get_logs_session", return_value=logs_session):
                await retention.enforce_retention()

        sqls = [
            str(getattr(c.args[0], "text", c.args[0])) for c in logs_session.execute.call_args_list
        ]
        assert any("DELETE FROM error_groups" in s for s in sqls)

    async def test_prunes_rollup_tables(self):
        auth_session = AsyncMock()
        auth_session.execute = AsyncMock(return_value=_FakeResult(fetchall_value=[(1, 30)]))
        auth_session = _session_cm(auth_session)

        logs_session = AsyncMock()
        logs_session.execute = AsyncMock(return_value=_FakeResult())
        logs_session = _session_cm(logs_session)

        with patch("analytics_workers.database.get_auth_session", return_value=auth_session):
            with patch("analytics_workers.database.get_logs_session", return_value=logs_session):
                await retention.enforce_retention()

        sqls = [
            str(getattr(c.args[0], "text", c.args[0])) for c in logs_session.execute.call_args_list
        ]
        for table, _column in retention._ROLLUP_TABLES:
            assert any(f"DELETE FROM {table}" in s for s in sqls)


class TestPartitionRangeEnd:
    def test_logs_partition_month_rollover(self):
        assert retention._partition_range_end("logs_2026_12") == datetime.date(2027, 1, 1)
        assert retention._partition_range_end("logs_2026_06") == datetime.date(2026, 7, 1)

    def test_spans_partition_is_monthly(self):
        # partition_manager creates spans partitions monthly, like logs; the
        # retention job used to expect a daily spans_YYYY_MM_DD name and so
        # never matched (and never dropped) a single spans partition.
        assert retention._partition_range_end("spans_2026_06") == datetime.date(2026, 7, 1)
        assert retention._partition_range_end("spans_2026_12") == datetime.date(2027, 1, 1)

    def test_metric_points_partition_month_rollover(self):
        assert retention._partition_range_end("metric_points_2026_12") == datetime.date(2027, 1, 1)
        assert retention._partition_range_end("metric_points_2026_06") == datetime.date(2026, 7, 1)

    def test_non_matching_name_returns_none(self):
        assert retention._partition_range_end("logs_backup") is None
        assert retention._partition_range_end("spans_2026_06_15") is None
        assert retention._partition_range_end("metric_points_backup") is None
        assert retention._partition_range_end("logs_staging") is None
