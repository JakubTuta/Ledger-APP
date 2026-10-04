import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import analytics_workers.jobs.alert_evaluator as alert_evaluator
import analytics_workers.jobs.monitor_checks as monitor_checks


def _fake_redis() -> MagicMock:
    redis = MagicMock()
    redis.publish = AsyncMock(return_value=1)
    return redis


def _published_notification(redis: MagicMock) -> dict:
    return json.loads(redis.publish.call_args.args[1])


async def _publish_rule_alert(event_state: str) -> dict:
    redis = _fake_redis()
    with patch.object(alert_evaluator.redis_client, "get_redis", return_value=redis):
        await alert_evaluator._publish_in_app(
            1,
            "High error rate",
            "error_rate_all",
            ">",
            5.0,
            "%",
            12.5,
            "warning",
            datetime.datetime.now(datetime.timezone.utc),
            event_state,
        )
    return _published_notification(redis)


async def _publish_monitor_transition(new_state: str) -> dict:
    redis = _fake_redis()
    auth_session = AsyncMock()
    auth_session.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: [(1,)]))
    with patch.object(monitor_checks.redis_client, "get_redis", return_value=redis):
        await monitor_checks._notify_transition(
            auth_session,
            1,
            7,
            "API health",
            "http",
            new_state,
            datetime.datetime.now(datetime.timezone.utc),
        )
    return _published_notification(redis)


@pytest.mark.asyncio
class TestLiveNotificationKind:
    async def test_rule_alert_firing_is_published_as_alert_firing(self):
        assert (await _publish_rule_alert("firing"))["kind"] == "alert_firing"

    async def test_rule_alert_resolved_is_published_as_alert_resolved(self):
        assert (await _publish_rule_alert("resolved"))["kind"] == "alert_resolved"

    async def test_monitor_down_is_published_as_alert_firing(self):
        assert (await _publish_monitor_transition("down"))["kind"] == "alert_firing"

    async def test_monitor_recovery_is_published_as_alert_resolved(self):
        assert (await _publish_monitor_transition("up"))["kind"] == "alert_resolved"
