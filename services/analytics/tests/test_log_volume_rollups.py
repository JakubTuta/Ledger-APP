import datetime

import analytics_workers.database as database
import analytics_workers.jobs.log_volume_1d_rollup as rollup_1d
import analytics_workers.jobs.log_volume_1h_rollup as rollup_1h
import pytest
import sqlalchemy as sa

_PROJECT_ID = 1
_FIVE_MINUTES = datetime.timedelta(minutes=5)
_ONE_HOUR = datetime.timedelta(hours=1)

# Whole past days, so every bucket under test is complete and sits inside the
# jobs' default lookback.
_DAY = datetime.datetime.now(datetime.timezone.utc).replace(
    hour=0, minute=0, second=0, microsecond=0
) - datetime.timedelta(days=2)


async def _insert_volume(table: str, buckets: list[datetime.datetime], count: int) -> None:
    async with database.get_logs_session() as session:
        await session.execute(
            sa.text(
                f"INSERT INTO {table} (project_id, level, bucket, count) "
                "VALUES (:project_id, 'info', :bucket, :count)"
            ),
            [{"project_id": _PROJECT_ID, "bucket": b, "count": count} for b in buckets],
        )
        await session.commit()


async def _read_counts(table: str) -> dict:
    async with database.get_logs_session() as session:
        result = await session.execute(
            sa.text(
                f"SELECT bucket, SUM(count) FROM {table} WHERE project_id = :p GROUP BY bucket"
            ),
            {"p": _PROJECT_ID},
        )
        return {bucket: int(total) for bucket, total in result.fetchall()}


def _span(
    start: datetime.datetime, step: datetime.timedelta, steps: int
) -> list[datetime.datetime]:
    return [start + step * i for i in range(steps)]


@pytest.mark.asyncio
class TestLogVolumeHourlyRollup:
    async def test_rerun_inside_an_hour_does_not_shrink_it_to_the_tail(self, test_dbs):
        await _insert_volume("log_volume_5m", _span(_DAY, _FIVE_MINUTES, 12), count=10)

        await rollup_1h.rollup_log_volume_1h()
        await rollup_1h.rollup_log_volume_1h()

        assert await _read_counts("log_volume_1h") == {_DAY: 120}

    async def test_new_buckets_extend_the_open_hour_and_start_the_next(self, test_dbs):
        await _insert_volume("log_volume_5m", _span(_DAY, _FIVE_MINUTES, 6), count=10)
        await rollup_1h.rollup_log_volume_1h()

        await _insert_volume(
            "log_volume_5m", _span(_DAY + 6 * _FIVE_MINUTES, _FIVE_MINUTES, 8), count=10
        )
        await rollup_1h.rollup_log_volume_1h()

        assert await _read_counts("log_volume_1h") == {_DAY: 120, _DAY + _ONE_HOUR: 20}


@pytest.mark.asyncio
class TestLogVolumeDailyRollup:
    async def test_rerun_inside_a_day_does_not_shrink_it_to_the_tail(self, test_dbs):
        await _insert_volume("log_volume_1h", _span(_DAY, _ONE_HOUR, 24), count=100)

        await rollup_1d.rollup_log_volume_1d()
        await rollup_1d.rollup_log_volume_1d()

        assert await _read_counts("log_volume_1d") == {_DAY.date(): 2400}

    async def test_new_hours_extend_the_open_day_and_start_the_next(self, test_dbs):
        await _insert_volume("log_volume_1h", _span(_DAY, _ONE_HOUR, 20), count=100)
        await rollup_1d.rollup_log_volume_1d()

        await _insert_volume("log_volume_1h", _span(_DAY + 20 * _ONE_HOUR, _ONE_HOUR, 6), count=100)
        await rollup_1d.rollup_log_volume_1d()

        assert await _read_counts("log_volume_1d") == {
            _DAY.date(): 2400,
            (_DAY + datetime.timedelta(days=1)).date(): 200,
        }
