import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import analytics_workers.jobs.log_facets_1h as log_facets_job
import pytest


def _mock_session():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()
    return mock_session


@pytest.mark.asyncio
async def test_rollup_recomputes_the_fixed_trailing_window():
    """
    No watermark: every run just re-derives `since` from wall-clock minus the
    fixed window and re-upserts it, so a missed run or late-arriving rows
    self-heal on the next tick without any state to reconcile.
    """
    mock_session = _mock_session()
    before = dt.datetime.now(dt.timezone.utc)

    with patch("analytics_workers.database.get_logs_session") as mock_get_session:
        mock_get_session.return_value = mock_session
        await log_facets_job.rollup_log_facets_1h()

    after = dt.datetime.now(dt.timezone.utc)
    params = mock_session.execute.call_args[0][1]
    expected_earliest = before - dt.timedelta(days=log_facets_job._WINDOW_DAYS)
    expected_latest = after - dt.timedelta(days=log_facets_job._WINDOW_DAYS)

    assert expected_earliest <= params["since"] <= expected_latest
    mock_session.commit.assert_awaited_once()
