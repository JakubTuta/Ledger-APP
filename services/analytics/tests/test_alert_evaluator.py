import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import analytics_workers.jobs.alert_evaluator as alert_evaluator
import analytics_workers.jobs.net_guard as net_guard


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _make_rule(
    rule_id=1,
    project_id=1,
    name="High error rate",
    metric="error_rate_all",
    comparator=">",
    threshold=5.0,
    unit="%",
    severity="warning",
    state="ok",
    for_minutes=0,
    cooldown_minutes=0,
    last_notified_at=None,
    pending_since=None,
    escalation_after_minutes=None,
    escalate_connector_id=None,
    escalated_at=None,
):
    return (
        rule_id,
        project_id,
        name,
        metric,
        comparator,
        threshold,
        unit,
        severity,
        state,
        for_minutes,
        cooldown_minutes,
        last_notified_at,
        pending_since,
        escalation_after_minutes,
        escalate_connector_id,
        escalated_at,
    )


class _FakeResult:
    def __init__(self, fetchall_value=None, scalar_value=None):
        self._fetchall_value = fetchall_value or []
        self._scalar_value = scalar_value

    def fetchall(self):
        return self._fetchall_value

    def fetchone(self):
        return self._fetchall_value[0] if self._fetchall_value else None

    def scalar(self):
        return self._scalar_value


def _make_auth_session(connectors=None, members=None, muted=None):
    """AsyncMock auth session whose .execute() routes based on the SQL text."""
    connectors = connectors if connectors is not None else []
    members = members if members is not None else []
    muted = muted if muted is not None else []

    session = AsyncMock()

    async def execute(query, params=None):
        sql = str(getattr(query, "text", query))
        if "FROM alert_rule_connectors" in sql:
            return _FakeResult(fetchall_value=connectors)
        if "FROM project_members" in sql:
            return _FakeResult(fetchall_value=[(m,) for m in members])
        if "FROM notification_preferences" in sql:
            return _FakeResult(fetchall_value=[(m,) for m in muted])
        return _FakeResult(fetchall_value=[], scalar_value=None)

    session.execute = AsyncMock(side_effect=execute)
    session.commit = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock()
    return session


@pytest.mark.asyncio
class TestEvaluateRuleStateMachine:
    async def test_first_breach_with_for_minutes_goes_pending_not_firing(self):
        rule = _make_rule(state="ok", for_minutes=5)
        auth_session = _make_auth_session()
        logs_session = AsyncMock()

        with patch.object(alert_evaluator, "_query_metric", AsyncMock(return_value=10.0)):
            await alert_evaluator._evaluate_rule(rule, logs_session, auth_session)

        update_calls = [
            c
            for c in auth_session.execute.call_args_list
            if "UPDATE alert_rules" in str(getattr(c.args[0], "text", c.args[0]))
        ]
        assert len(update_calls) == 1
        assert "'pending'" in str(update_calls[0].args[0].text)
        # no dispatch: connectors query must not have been issued
        connector_calls = [
            c
            for c in auth_session.execute.call_args_list
            if "FROM alert_rule_connectors" in str(getattr(c.args[0], "text", c.args[0]))
        ]
        assert connector_calls == []

    async def test_breach_fires_immediately_when_for_minutes_zero(self):
        rule = _make_rule(state="ok", for_minutes=0)
        auth_session = _make_auth_session(connectors=[], members=[])
        logs_session = AsyncMock()

        with patch.object(alert_evaluator, "_query_metric", AsyncMock(return_value=10.0)):
            await alert_evaluator._evaluate_rule(rule, logs_session, auth_session)

        sqls = [
            str(getattr(c.args[0], "text", c.args[0])) for c in auth_session.execute.call_args_list
        ]
        assert any("state = 'firing'" in s for s in sqls)
        assert any("INSERT INTO alert_events" in s for s in sqls)

    async def test_pending_fires_once_for_minutes_elapsed(self):
        pending_since = _now() - datetime.timedelta(minutes=10)
        rule = _make_rule(state="pending", for_minutes=5, pending_since=pending_since)
        auth_session = _make_auth_session(connectors=[], members=[])
        logs_session = AsyncMock()

        with patch.object(alert_evaluator, "_query_metric", AsyncMock(return_value=10.0)):
            await alert_evaluator._evaluate_rule(rule, logs_session, auth_session)

        sqls = [
            str(getattr(c.args[0], "text", c.args[0])) for c in auth_session.execute.call_args_list
        ]
        assert any("state = 'firing'" in s for s in sqls)

    async def test_pending_does_not_fire_before_for_minutes_elapsed(self):
        pending_since = _now() - datetime.timedelta(minutes=1)
        rule = _make_rule(state="pending", for_minutes=5, pending_since=pending_since)
        auth_session = _make_auth_session()
        logs_session = AsyncMock()

        with patch.object(alert_evaluator, "_query_metric", AsyncMock(return_value=10.0)):
            await alert_evaluator._evaluate_rule(rule, logs_session, auth_session)

        # _evaluate_rule always checks maintenance_windows before deciding whether
        # to fire, so a single (non-transitioning) query is now expected here.
        assert auth_session.execute.call_count == 1

    async def test_firing_does_not_refire_without_cooldown(self):
        rule = _make_rule(state="firing", cooldown_minutes=0, last_notified_at=_now())
        auth_session = _make_auth_session()
        logs_session = AsyncMock()

        with patch.object(alert_evaluator, "_query_metric", AsyncMock(return_value=10.0)):
            await alert_evaluator._evaluate_rule(rule, logs_session, auth_session)

        # The maintenance-window check plus the firing-state snooze lookup
        # (_get_snoozed_until) account for the two calls; cooldown_minutes=0
        # means _fire() is never reached regardless of snooze state.
        assert auth_session.execute.call_count == 2

    async def test_firing_refires_after_cooldown_elapsed(self):
        last_notified = _now() - datetime.timedelta(minutes=90)
        rule = _make_rule(state="firing", cooldown_minutes=60, last_notified_at=last_notified)
        auth_session = _make_auth_session(connectors=[], members=[])
        logs_session = AsyncMock()

        with patch.object(alert_evaluator, "_query_metric", AsyncMock(return_value=10.0)):
            await alert_evaluator._evaluate_rule(rule, logs_session, auth_session)

        sqls = [
            str(getattr(c.args[0], "text", c.args[0])) for c in auth_session.execute.call_args_list
        ]
        assert any("state = 'firing'" in s for s in sqls)

    async def test_recovery_resolves_and_emits_alert_resolved(self):
        rule = _make_rule(state="firing")
        auth_session = _make_auth_session(connectors=[], members=[])
        logs_session = AsyncMock()

        with patch.object(alert_evaluator, "_query_metric", AsyncMock(return_value=1.0)):
            await alert_evaluator._evaluate_rule(rule, logs_session, auth_session)

        sqls = [
            str(getattr(c.args[0], "text", c.args[0])) for c in auth_session.execute.call_args_list
        ]
        assert any("state = 'ok'" in s for s in sqls)
        assert any("'resolved'" in s for s in sqls)

    async def test_pending_clears_silently_when_breach_ends(self):
        rule = _make_rule(state="pending", pending_since=_now())
        auth_session = _make_auth_session()
        logs_session = AsyncMock()

        with patch.object(alert_evaluator, "_query_metric", AsyncMock(return_value=1.0)):
            await alert_evaluator._evaluate_rule(rule, logs_session, auth_session)

        sqls = [
            str(getattr(c.args[0], "text", c.args[0])) for c in auth_session.execute.call_args_list
        ]
        # First call is always the maintenance_windows check; the state-clearing
        # UPDATE follows it.
        assert len(sqls) == 2
        assert "maintenance_windows" in sqls[0]
        assert "state = 'ok'" in sqls[1]
        assert "alert_events" not in sqls[1]


@pytest.mark.asyncio
class TestNotificationRecipients:
    async def test_excludes_muted_members(self):
        auth_session = _make_auth_session(members=[1, 2, 3], muted=[2])

        recipients = await alert_evaluator._notification_recipients(
            project_id=1, rule_id=1, severity="warning", auth_session=auth_session
        )

        assert sorted(recipients) == [1, 3]

    async def test_no_members_returns_empty(self):
        auth_session = _make_auth_session(members=[])

        recipients = await alert_evaluator._notification_recipients(
            project_id=1, rule_id=1, severity="warning", auth_session=auth_session
        )

        assert recipients == []


@pytest.mark.asyncio
class TestPostWebhook:
    async def test_blocks_ssrf_target(self):
        delivered, error = await alert_evaluator._post_webhook(
            "https://169.254.169.254/hook", "secret", {"a": 1}
        )
        assert delivered is False
        assert "private/reserved" in error or "resolves to" in error

    async def test_delivers_successfully(self):
        mock_response = MagicMock()
        mock_response.status = 200

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch.object(net_guard, "validate_webhook_url", AsyncMock(return_value=None)):
            with patch("aiohttp.ClientSession", return_value=mock_session):
                delivered, error = await alert_evaluator._post_webhook(
                    "https://example.com/hook", "secret", {"a": 1}
                )

        assert delivered is True
        assert error is None

    async def test_reports_http_error_status(self):
        mock_response = MagicMock()
        mock_response.status = 500

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch.object(net_guard, "validate_webhook_url", AsyncMock(return_value=None)):
            with patch("aiohttp.ClientSession", return_value=mock_session):
                delivered, error = await alert_evaluator._post_webhook(
                    "https://example.com/hook", "secret", {"a": 1}
                )

        assert delivered is False
        assert "500" in error


@pytest.mark.asyncio
class TestPostSlack:
    async def test_blocks_ssrf_target(self):
        delivered, error = await alert_evaluator._post_slack(
            "https://169.254.169.254/hook", "High error rate is firing"
        )
        assert delivered is False
        assert "private/reserved" in error or "resolves to" in error

    async def test_sends_text_payload(self):
        mock_response = MagicMock()
        mock_response.status = 200

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch.object(net_guard, "validate_webhook_url", AsyncMock(return_value=None)):
            with patch("aiohttp.ClientSession", return_value=mock_session):
                delivered, error = await alert_evaluator._post_slack(
                    "https://hooks.slack.com/services/x", "High error rate is firing"
                )

        assert delivered is True
        assert error is None
        _, kwargs = mock_session.post.call_args
        assert kwargs["json"] == {"text": "High error rate is firing"}

    async def test_reports_http_error_status(self):
        mock_response = MagicMock()
        mock_response.status = 403

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch.object(net_guard, "validate_webhook_url", AsyncMock(return_value=None)):
            with patch("aiohttp.ClientSession", return_value=mock_session):
                delivered, error = await alert_evaluator._post_slack(
                    "https://hooks.slack.com/services/x", "message"
                )

        assert delivered is False
        assert "403" in error


@pytest.mark.asyncio
class TestPostDiscord:
    async def test_blocks_ssrf_target(self):
        delivered, error = await alert_evaluator._post_discord(
            "https://169.254.169.254/hook", "High error rate is firing"
        )
        assert delivered is False
        assert "private/reserved" in error or "resolves to" in error

    async def test_sends_content_payload(self):
        mock_response = MagicMock()
        mock_response.status = 200

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch.object(net_guard, "validate_webhook_url", AsyncMock(return_value=None)):
            with patch("aiohttp.ClientSession", return_value=mock_session):
                delivered, error = await alert_evaluator._post_discord(
                    "https://discord.com/api/webhooks/x", "High error rate is firing"
                )

        assert delivered is True
        assert error is None
        _, kwargs = mock_session.post.call_args
        assert kwargs["json"] == {"content": "High error rate is firing"}

    async def test_reports_http_error_status(self):
        mock_response = MagicMock()
        mock_response.status = 429

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch.object(net_guard, "validate_webhook_url", AsyncMock(return_value=None)):
            with patch("aiohttp.ClientSession", return_value=mock_session):
                delivered, error = await alert_evaluator._post_discord(
                    "https://discord.com/api/webhooks/x", "message"
                )

        assert delivered is False
        assert "429" in error


@pytest.mark.asyncio
class TestPostPagerduty:
    async def test_firing_sends_trigger_action(self):
        mock_response = MagicMock()
        mock_response.status = 200

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            delivered, error = await alert_evaluator._post_pagerduty(
                "integration-key", 42, "High error rate is firing", "critical", "firing"
            )

        assert delivered is True
        assert error is None
        _, kwargs = mock_session.post.call_args
        assert kwargs["json"] == {
            "routing_key": "integration-key",
            "event_action": "trigger",
            "dedup_key": "ledger-rule-42",
            "payload": {
                "summary": "High error rate is firing",
                "severity": "critical",
                "source": "ledger",
            },
        }

    async def test_resolved_sends_resolve_action(self):
        mock_response = MagicMock()
        mock_response.status = 200

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            delivered, error = await alert_evaluator._post_pagerduty(
                "integration-key", 42, "Recovered", "warning", "resolved"
            )

        assert delivered is True
        _, kwargs = mock_session.post.call_args
        assert kwargs["json"]["event_action"] == "resolve"
        assert kwargs["json"]["dedup_key"] == "ledger-rule-42"
        assert kwargs["json"]["payload"]["severity"] == "warning"

    async def test_non_critical_severity_maps_to_warning(self):
        mock_response = MagicMock()
        mock_response.status = 200

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            await alert_evaluator._post_pagerduty("key", 1, "summary", "info", "firing")

        _, kwargs = mock_session.post.call_args
        assert kwargs["json"]["payload"]["severity"] == "warning"

    async def test_reports_http_error_status(self):
        mock_response = MagicMock()
        mock_response.status = 400

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            delivered, error = await alert_evaluator._post_pagerduty(
                "key", 1, "summary", "critical", "firing"
            )

        assert delivered is False
        assert "400" in error


@pytest.mark.asyncio
class TestPostOpsgenie:
    async def test_firing_creates_alert_with_priority(self):
        mock_response = MagicMock()
        mock_response.status = 202

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            delivered, error = await alert_evaluator._post_opsgenie(
                "api-key", 42, "High error rate is firing", "critical", "firing"
            )

        assert delivered is True
        assert error is None
        args, kwargs = mock_session.post.call_args
        assert args[0] == alert_evaluator._OPSGENIE_ALERTS_URL
        assert kwargs["json"] == {
            "message": "High error rate is firing",
            "alias": "ledger-rule-42",
            "priority": "P1",
        }
        assert kwargs["headers"] == {"Authorization": "GenieKey api-key"}

    async def test_firing_non_critical_uses_p3_priority(self):
        mock_response = MagicMock()
        mock_response.status = 202

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            await alert_evaluator._post_opsgenie("api-key", 42, "message", "warning", "firing")

        _, kwargs = mock_session.post.call_args
        assert kwargs["json"]["priority"] == "P3"

    async def test_resolved_closes_alert_by_alias(self):
        mock_response = MagicMock()
        mock_response.status = 200

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            delivered, error = await alert_evaluator._post_opsgenie(
                "api-key", 42, "message", "critical", "resolved"
            )

        assert delivered is True
        args, kwargs = mock_session.post.call_args
        assert (
            args[0]
            == f"{alert_evaluator._OPSGENIE_ALERTS_URL}/ledger-rule-42/close?identifierType=alias"
        )
        assert kwargs["json"] == {}

    async def test_reports_http_error_status(self):
        mock_response = MagicMock()
        mock_response.status = 401

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            delivered, error = await alert_evaluator._post_opsgenie(
                "api-key", 1, "message", "critical", "firing"
            )

        assert delivered is False
        assert "401" in error


@pytest.mark.asyncio
class TestSendEmail:
    async def test_disabled_returns_false(self):
        mock_settings = MagicMock()
        mock_settings.EMAIL_ENABLED = False

        with patch.object(alert_evaluator.config, "get_settings", return_value=mock_settings):
            delivered, error = await alert_evaluator._send_email(
                "user@example.com", "rule", "metric", ">", 5.0, "%", 10.0, "warning", "firing"
            )

        assert delivered is False
        assert error == "Email delivery disabled"

    async def test_missing_credentials_returns_false(self):
        mock_settings = MagicMock()
        mock_settings.EMAIL_ENABLED = True
        mock_settings.SMTP_USER = None
        mock_settings.SMTP_PASSWORD = None

        with patch.object(alert_evaluator.config, "get_settings", return_value=mock_settings):
            delivered, error = await alert_evaluator._send_email(
                "user@example.com", "rule", "metric", ">", 5.0, "%", 10.0, "warning", "firing"
            )

        assert delivered is False
        assert error == "SMTP credentials not configured"


@pytest.mark.asyncio
class TestNetGuard:
    async def test_blocks_loopback(self):
        with pytest.raises(net_guard.UnsafeWebhookURLError):
            await net_guard.validate_webhook_url("https://127.0.0.1/hook")

    async def test_blocks_link_local_metadata_address(self):
        with pytest.raises(net_guard.UnsafeWebhookURLError):
            await net_guard.validate_webhook_url("https://169.254.169.254/hook")

    async def test_rejects_plain_http_by_default(self):
        with pytest.raises(net_guard.UnsafeWebhookURLError):
            await net_guard.validate_webhook_url("http://example.com/hook")

    async def test_allows_plain_http_when_explicitly_enabled(self):
        try:
            await net_guard.validate_webhook_url("http://example.com/hook", allow_http=True)
        except net_guard.UnsafeWebhookURLError as e:
            pytest.fail(f"Unexpected rejection with allow_http=True: {e}")
