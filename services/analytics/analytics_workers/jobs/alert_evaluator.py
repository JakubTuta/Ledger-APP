import asyncio
import datetime
import hashlib
import hmac
import json
import time
import typing

import email.message

import aiohttp
import aiosmtplib

import analytics_workers.config as config
import analytics_workers.database as database
import analytics_workers.jobs.net_guard as net_guard
import analytics_workers.redis_client as redis_client
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.alert_evaluator")

_SEVERITY_TO_LEVEL: dict[str, str] = {
    "critical": "critical",
    "warning": "error",
    "info": "error",
}

_COMPARATORS: dict[str, typing.Callable[[float, float], bool]] = {
    ">": lambda v, t: v > t,
    "<": lambda v, t: v < t,
    ">=": lambda v, t: v >= t,
    "<=": lambda v, t: v <= t,
}

_LOOKBACK_MINUTES = 10
_LATENCY_LOOKBACK_MINUTES = 60
_HEARTBEAT_KEY = "analytics:alert_evaluator:last_run"
_HEARTBEAT_TTL_SECONDS = 300
_DELIVERY_RETRY_BACKOFF_SECONDS = 0.5


async def _with_retry(
    send: typing.Callable[[], typing.Awaitable[tuple[bool, str | None]]],
) -> tuple[bool, str | None]:
    delivered, error = await send()
    if delivered:
        return delivered, error

    await asyncio.sleep(_DELIVERY_RETRY_BACKOFF_SECONDS)
    return await send()


async def _get_snoozed_until(
    rule_id: int, auth_session: sa.ext.asyncio.AsyncSession
) -> datetime.datetime | None:
    """Snooze state lives on the most recent alert_event for this rule (set via
    the gateway's /alerts/history/{event_id}/snooze endpoint), not on the rule
    itself - it's per-incident, not a standing rule setting."""
    result = await auth_session.execute(
        sa.text(
            "SELECT snoozed_until FROM alert_events WHERE rule_id = :rule_id "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"rule_id": rule_id},
    )
    row = result.fetchone()
    return row[0] if row else None


async def evaluate_alert_rules() -> None:
    start = time.perf_counter()

    try:
        async with database.get_auth_session() as auth_session:
            rules_result = await auth_session.execute(
                sa.text(
                    """
                    SELECT id, project_id, name, metric_type, comparator,
                           threshold, unit, severity, state,
                           for_minutes, cooldown_minutes, last_notified_at, pending_since,
                           escalation_after_minutes, escalate_connector_id, escalated_at
                    FROM alert_rules
                    WHERE enabled = TRUE
                    ORDER BY id
                    """
                )
            )
            rules = rules_result.fetchall()

        if rules:
            for rule in rules:
                try:
                    async with database.get_logs_session() as logs_session:
                        async with database.get_auth_session() as auth_session:
                            await _evaluate_rule(rule, logs_session, auth_session)
                except Exception as e:
                    logger.error(f"Rule {rule[0]} evaluation failed: {e}", exc_info=True)

        elapsed = time.perf_counter() - start
        logger.info(f"Alert evaluation done in {elapsed:.2f}s for {len(rules)} rules")

        await _write_heartbeat()

    except Exception as e:
        logger.error(f"Alert evaluator failed: {e}", exc_info=True)
        raise


async def _write_heartbeat() -> None:
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        await redis_client.get_redis().set(
            _HEARTBEAT_KEY, now.isoformat(), ex=_HEARTBEAT_TTL_SECONDS
        )
    except Exception as e:
        logger.warning(f"Failed to write alert evaluator heartbeat: {e}")


async def _evaluate_rule(
    rule: typing.Any,
    logs_session: sa.ext.asyncio.AsyncSession,
    auth_session: sa.ext.asyncio.AsyncSession,
) -> None:
    rule_id = rule[0]
    project_id = rule[1]
    rule_name = rule[2]
    metric = rule[3]
    comparator = rule[4]
    threshold = rule[5]
    unit = rule[6]
    severity = rule[7]
    state = rule[8]
    for_minutes = rule[9]
    cooldown_minutes = rule[10]
    last_notified_at = rule[11]
    pending_since = rule[12]
    escalation_after_minutes = rule[13]
    escalate_connector_id = rule[14]
    escalated_at = rule[15]

    value = await _query_metric(metric, project_id, logs_session)
    if value is None:
        return

    compare_fn = _COMPARATORS.get(comparator)
    if compare_fn is None:
        logger.warning(f"Unknown comparator '{comparator}' for rule {rule_id}")
        return

    normalized_threshold = _normalize_threshold(metric, threshold, unit)
    breached = compare_fn(value, normalized_threshold)
    display_value = _to_display_value(metric, value, unit)
    now = datetime.datetime.now(datetime.timezone.utc)

    logger.info(
        f"Rule {rule_id} '{rule_name}' project={project_id} metric={metric} "
        f"value={value:.4f} {comparator} threshold={normalized_threshold:.4f} "
        f"breached={breached} state={state}"
    )

    in_maintenance = await _in_maintenance_window(project_id, now, auth_session)
    if in_maintenance:
        logger.info(
            f"Rule {rule_id} project={project_id} is inside an active maintenance "
            "window; notifications will be suppressed"
        )

    if breached:
        if state == "ok":
            if for_minutes > 0:
                await auth_session.execute(
                    sa.text(
                        "UPDATE alert_rules SET state = 'pending', pending_since = :now, "
                        "updated_at = :now WHERE id = :id"
                    ),
                    {"now": now, "id": rule_id},
                )
                await auth_session.commit()
            else:
                await _fire(
                    rule_id,
                    project_id,
                    rule_name,
                    metric,
                    comparator,
                    threshold,
                    unit,
                    display_value,
                    severity,
                    now,
                    auth_session,
                    suppress_notifications=in_maintenance,
                )
        elif state == "pending":
            elapsed_minutes = (
                (now - pending_since).total_seconds() / 60.0 if pending_since else for_minutes
            )
            if elapsed_minutes >= for_minutes:
                await _fire(
                    rule_id,
                    project_id,
                    rule_name,
                    metric,
                    comparator,
                    threshold,
                    unit,
                    display_value,
                    severity,
                    now,
                    auth_session,
                    suppress_notifications=in_maintenance,
                )
        elif state == "firing":
            snoozed_until = await _get_snoozed_until(rule_id, auth_session)
            is_snoozed = snoozed_until is not None and snoozed_until > now

            cooldown_elapsed = (
                (now - last_notified_at).total_seconds() / 60.0
                if last_notified_at
                else float("inf")
            )
            if not is_snoozed and cooldown_minutes > 0 and cooldown_elapsed >= cooldown_minutes:
                await _fire(
                    rule_id,
                    project_id,
                    rule_name,
                    metric,
                    comparator,
                    threshold,
                    unit,
                    display_value,
                    severity,
                    now,
                    auth_session,
                    suppress_notifications=in_maintenance,
                )
            if not in_maintenance and not is_snoozed:
                await _maybe_escalate(
                    rule_id,
                    project_id,
                    rule_name,
                    metric,
                    comparator,
                    threshold,
                    unit,
                    display_value,
                    severity,
                    now,
                    escalation_after_minutes,
                    escalate_connector_id,
                    escalated_at,
                    auth_session,
                )
    else:
        if state == "firing":
            await _resolve(
                rule_id,
                project_id,
                rule_name,
                metric,
                comparator,
                threshold,
                unit,
                display_value,
                severity,
                now,
                auth_session,
                suppress_notifications=in_maintenance,
            )
        elif state == "pending":
            await auth_session.execute(
                sa.text(
                    "UPDATE alert_rules SET state = 'ok', pending_since = NULL, "
                    "updated_at = :now WHERE id = :id"
                ),
                {"now": now, "id": rule_id},
            )
            await auth_session.commit()


async def _in_maintenance_window(
    project_id: int,
    now: datetime.datetime,
    auth_session: sa.ext.asyncio.AsyncSession,
) -> bool:
    """
    Simple maintenance-window check (no RRULE engine): 'none'/NULL windows are
    matched by absolute timestamp range; 'daily' windows match only the
    time-of-day component; 'weekly' windows additionally match day-of-week
    (taken from starts_at). Windows are assumed not to cross midnight.
    """
    result = await auth_session.execute(
        sa.text(
            "SELECT starts_at, ends_at, recurrence FROM maintenance_windows WHERE project_id = :pid"
        ),
        {"pid": project_id},
    )
    windows = result.fetchall()
    if not windows:
        return False

    now_time = now.timetz()
    for starts_at, ends_at, recurrence in windows:
        if recurrence in (None, "none"):
            if starts_at <= now <= ends_at:
                return True
        elif recurrence == "daily":
            if starts_at.timetz() <= now_time <= ends_at.timetz():
                return True
        elif recurrence == "weekly":
            if (
                now.weekday() == starts_at.weekday()
                and starts_at.timetz() <= now_time <= ends_at.timetz()
            ):
                return True
    return False


async def _firing_episode_start(
    rule_id: int,
    auth_session: sa.ext.asyncio.AsyncSession,
) -> datetime.datetime | None:
    """
    The earliest still-open 'firing' alert_events row for this rule, i.e. the
    start of the current firing episode: the earliest firing event inserted
    after the most recent resolved event (or the first ever, if never
    resolved). Re-fires from cooldown re-notification insert additional
    'firing' rows but don't move this earlier bound.
    """
    result = await auth_session.execute(
        sa.text(
            """
            SELECT MIN(fired_at) FROM alert_events
            WHERE rule_id = :rid AND state = 'firing'
              AND id > COALESCE(
                  (SELECT MAX(id) FROM alert_events
                   WHERE rule_id = :rid AND state = 'resolved'),
                  0
              )
            """
        ),
        {"rid": rule_id},
    )
    return result.scalar()


async def _maybe_escalate(
    rule_id: int,
    project_id: int,
    rule_name: str,
    metric: str,
    comparator: str,
    threshold: float,
    unit: str,
    value: float,
    severity: str,
    now: datetime.datetime,
    escalation_after_minutes: int | None,
    escalate_connector_id: int | None,
    escalated_at: datetime.datetime | None,
    auth_session: sa.ext.asyncio.AsyncSession,
) -> None:
    if not escalate_connector_id or not escalation_after_minutes:
        return
    if escalated_at is not None:
        return  # already escalated once for this firing episode

    episode_start = await _firing_episode_start(rule_id, auth_session)
    if episode_start is None:
        return
    elapsed_minutes = (now - episode_start).total_seconds() / 60.0
    if elapsed_minutes < escalation_after_minutes:
        return

    connector_result = await auth_session.execute(
        sa.text("SELECT id, kind, name, config FROM connectors WHERE id = :cid AND enabled = TRUE"),
        {"cid": escalate_connector_id},
    )
    connector = connector_result.fetchone()
    if connector is None:
        logger.warning(
            f"Rule {rule_id} escalate_connector_id={escalate_connector_id} "
            "not found or disabled; skipping escalation"
        )
        return

    await _dispatch_to_connectors(
        [connector],
        rule_id,
        project_id,
        rule_name,
        metric,
        comparator,
        threshold,
        unit,
        value,
        severity,
        now,
        auth_session,
        event_state="firing",
    )
    await auth_session.execute(
        sa.text("UPDATE alert_rules SET escalated_at = :now WHERE id = :id"),
        {"now": now, "id": rule_id},
    )
    await auth_session.commit()
    logger.info(
        f"Rule {rule_id} escalated to connector {escalate_connector_id} after "
        f"{elapsed_minutes:.1f}m firing"
    )


def _normalize_threshold(metric: str, threshold: float, unit: str) -> float:
    if metric in ("p95_latency", "p99_latency"):
        if unit == "s":
            return threshold * 1000.0
        return threshold
    return threshold


def _to_display_value(metric: str, value: float, unit: str) -> float:
    if metric in ("p95_latency", "p99_latency") and unit == "s":
        return value / 1000.0
    return value


async def _query_metric(
    metric: str,
    project_id: int,
    session: sa.ext.asyncio.AsyncSession,
) -> float | None:
    now = datetime.datetime.now(datetime.timezone.utc)
    since = now - datetime.timedelta(minutes=_LOOKBACK_MINUTES)
    latency_since = now - datetime.timedelta(minutes=_LATENCY_LOOKBACK_MINUTES)

    if metric in ("p95_latency", "p99_latency"):
        column = "p95_ms" if metric == "p95_latency" else "p99_ms"
        rollup_result = await session.execute(
            sa.text(
                f"""
                SELECT MAX({column})
                FROM endpoint_latency_1h
                WHERE project_id = :pid AND bucket >= :since AND count > 0
                """
            ),
            {"pid": project_id, "since": latency_since},
        )
        rollup_val = rollup_result.scalar()
        if rollup_val is not None:
            return float(rollup_val)

        pct = 0.95 if metric == "p95_latency" else 0.99
        result = await session.execute(
            sa.text(
                """
                SELECT COALESCE(
                    PERCENTILE_CONT(:pct) WITHIN GROUP (
                        ORDER BY (attributes->'endpoint'->>'duration_ms')::float
                    ), 0)
                FROM logs
                WHERE project_id = :pid
                  AND timestamp >= :since
                  AND log_type = 'endpoint'
                  AND attributes->'endpoint'->>'duration_ms' IS NOT NULL
                """
            ),
            {"pid": project_id, "since": latency_since, "pct": pct},
        )
        val = result.scalar()
        return float(val) if val is not None else None

    if metric in ("error_rate_5xx", "error_rate_4xx"):
        low, high = (500, 599) if metric == "error_rate_5xx" else (400, 499)
        result = await session.execute(
            sa.text(
                """
                SELECT COALESCE(
                    100.0 * count(*) FILTER (WHERE status_code BETWEEN :low AND :high)
                    / NULLIF(count(*) FILTER (WHERE status_code IS NOT NULL), 0), 0)
                FROM logs
                WHERE project_id = :pid AND timestamp >= :since
                """
            ),
            {"pid": project_id, "since": since, "low": low, "high": high},
        )
        val = result.scalar()
        return float(val) if val is not None else None

    if metric == "error_rate_all":
        result = await session.execute(
            sa.text(
                """
                SELECT COALESCE(100.0 * SUM(errors)::float / NULLIF(SUM(total), 0), 0)
                FROM error_rate_5m
                WHERE project_id = :pid AND bucket >= :since
                """
            ),
            {"pid": project_id, "since": since},
        )
        val = result.scalar()
        return float(val) if val is not None else None

    if metric == "request_volume":
        result = await session.execute(
            sa.text(
                """
                SELECT COALESCE(SUM(count), 0)
                FROM log_volume_5m
                WHERE project_id = :pid AND bucket >= :since
                """
            ),
            {"pid": project_id, "since": since},
        )
        val = result.scalar()
        return float(val) if val is not None else None

    if metric == "new_error_type":
        # Counts error groups whose *first* occurrence fell within the lookback
        # window (i.e. genuinely new fingerprints), scoped to this project —
        # not just error groups that merely recurred (last_seen bump).
        result = await session.execute(
            sa.text(
                """
                SELECT COUNT(*)
                FROM error_groups
                WHERE project_id = :pid AND first_seen >= :since
                """
            ),
            {"pid": project_id, "since": since},
        )
        val = result.scalar()
        return float(val) if val is not None else 0.0

    logger.warning(f"Unknown metric type: {metric}")
    return None


async def _fire(
    rule_id: int,
    project_id: int,
    rule_name: str,
    metric: str,
    comparator: str,
    threshold: float,
    unit: str,
    value: float,
    severity: str,
    now: datetime.datetime,
    auth_session: sa.ext.asyncio.AsyncSession,
    suppress_notifications: bool = False,
) -> None:
    if suppress_notifications:
        logger.info(f"Rule {rule_id} fire notification suppressed (maintenance window)")
        connectors_sent: list[dict] = []
    else:
        connectors_sent = await _dispatch(
            rule_id,
            project_id,
            rule_name,
            metric,
            comparator,
            threshold,
            unit,
            value,
            severity,
            now,
            auth_session,
            event_state="firing",
        )

    await auth_session.execute(
        sa.text(
            "UPDATE alert_rules SET state = 'firing', last_fired_at = :now, "
            "fired_value = :val, last_notified_at = :now, pending_since = NULL, "
            "updated_at = :now WHERE id = :id"
        ),
        {"now": now, "val": value, "id": rule_id},
    )

    await auth_session.execute(
        sa.text(
            """
            INSERT INTO alert_events
                (rule_id, project_id, rule_name, metric_type, comparator,
                 threshold, unit, value, severity, state, connectors_sent, fired_at)
            VALUES
                (:rule_id, :project_id, :rule_name, :metric, :comparator,
                 :threshold, :unit, :value, :severity, 'firing',
                 CAST(:connectors_sent AS jsonb), :fired_at)
            """
        ),
        {
            "rule_id": rule_id,
            "project_id": project_id,
            "rule_name": rule_name,
            "metric": metric,
            "comparator": comparator,
            "threshold": threshold,
            "unit": unit,
            "value": value,
            "severity": severity,
            "connectors_sent": json.dumps(connectors_sent),
            "fired_at": now,
        },
    )
    await auth_session.commit()


async def _resolve(
    rule_id: int,
    project_id: int,
    rule_name: str,
    metric: str,
    comparator: str,
    threshold: float,
    unit: str,
    value: float,
    severity: str,
    now: datetime.datetime,
    auth_session: sa.ext.asyncio.AsyncSession,
    suppress_notifications: bool = False,
) -> None:
    if suppress_notifications:
        logger.info(f"Rule {rule_id} resolve notification suppressed (maintenance window)")
        connectors_sent: list[dict] = []
    else:
        connectors_sent = await _dispatch(
            rule_id,
            project_id,
            rule_name,
            metric,
            comparator,
            threshold,
            unit,
            value,
            severity,
            now,
            auth_session,
            event_state="resolved",
        )

    await auth_session.execute(
        sa.text(
            "UPDATE alert_rules SET state = 'ok', pending_since = NULL, "
            "escalated_at = NULL, updated_at = :now WHERE id = :id"
        ),
        {"now": now, "id": rule_id},
    )

    await auth_session.execute(
        sa.text(
            """
            INSERT INTO alert_events
                (rule_id, project_id, rule_name, metric_type, comparator,
                 threshold, unit, value, severity, state, connectors_sent, fired_at)
            VALUES
                (:rule_id, :project_id, :rule_name, :metric, :comparator,
                 :threshold, :unit, :value, :severity, 'resolved',
                 CAST(:connectors_sent AS jsonb), :fired_at)
            """
        ),
        {
            "rule_id": rule_id,
            "project_id": project_id,
            "rule_name": rule_name,
            "metric": metric,
            "comparator": comparator,
            "threshold": threshold,
            "unit": unit,
            "value": value,
            "severity": severity,
            "connectors_sent": json.dumps(connectors_sent),
            "fired_at": now,
        },
    )
    await auth_session.commit()


async def _dispatch(
    rule_id: int,
    project_id: int,
    rule_name: str,
    metric: str,
    comparator: str,
    threshold: float,
    unit: str,
    value: float,
    severity: str,
    now: datetime.datetime,
    auth_session: sa.ext.asyncio.AsyncSession,
    event_state: typing.Literal["firing", "resolved"],
) -> list[dict]:
    connectors_result = await auth_session.execute(
        sa.text(
            """
            SELECT c.id, c.kind, c.name, c.config
            FROM alert_rule_connectors arc
            JOIN connectors c ON c.id = arc.connector_id
            WHERE arc.rule_id = :rid AND c.enabled = TRUE
            """
        ),
        {"rid": rule_id},
    )
    connectors = connectors_result.fetchall()
    return await _dispatch_to_connectors(
        connectors,
        rule_id,
        project_id,
        rule_name,
        metric,
        comparator,
        threshold,
        unit,
        value,
        severity,
        now,
        auth_session,
        event_state=event_state,
    )


async def _dispatch_to_connectors(
    connectors: typing.Sequence[typing.Any],
    rule_id: int,
    project_id: int,
    rule_name: str,
    metric: str,
    comparator: str,
    threshold: float,
    unit: str,
    value: float,
    severity: str,
    now: datetime.datetime,
    auth_session: sa.ext.asyncio.AsyncSession,
    event_state: typing.Literal["firing", "resolved"],
) -> list[dict]:
    """
    Deliver one firing/resolved notification to each connector row given.
    Used both for the rule's normally-linked connectors (via `_dispatch`) and
    for a single ad-hoc escalation connector.
    """
    notification_kind = "alert_firing" if event_state == "firing" else "alert_resolved"
    notification_severity = severity if event_state == "firing" else "info"

    payload = {
        "rule_id": rule_id,
        "name": rule_name,
        "metric": metric,
        "comparator": comparator,
        "threshold": threshold,
        "unit": unit,
        "value": value,
        "state": event_state,
        "fired_at": now.isoformat(),
    }

    message_text = _format_alert_message(
        rule_name, metric, comparator, threshold, unit, value, event_state
    )

    recipients = await _notification_recipients(project_id, rule_id, severity, auth_session)

    connectors_sent: list[dict] = []
    for connector in connectors:
        connector_id = connector[0]
        connector_kind = connector[1]
        connector_name = connector[2]
        connector_config = connector[3] or {}

        delivered = True
        error: str | None = None

        if connector_kind == "in_app":
            for account_id in recipients:
                await auth_session.execute(
                    sa.text(
                        """
                        INSERT INTO notifications
                            (user_id, project_id, kind, severity, payload)
                        VALUES (:user_id, :project_id, :kind, :severity, CAST(:payload AS jsonb))
                        """
                    ),
                    {
                        "user_id": account_id,
                        "project_id": project_id,
                        "kind": notification_kind,
                        "severity": notification_severity,
                        "payload": json.dumps(payload),
                    },
                )
            await _publish_in_app(
                project_id,
                rule_name,
                metric,
                comparator,
                threshold,
                unit,
                value,
                notification_severity,
                now,
                event_state,
            )
        elif connector_kind == "webhook":
            url = connector_config.get("url")
            secret = connector_config.get("hmac_secret", "")
            if url:
                delivered, error = await _with_retry(lambda: _post_webhook(url, secret, payload))
            else:
                delivered, error = False, "Webhook connector missing url"
        elif connector_kind == "email":
            address = connector_config.get("address")
            if address:
                delivered, error = await _with_retry(
                    lambda: _send_email(
                        address,
                        rule_name,
                        metric,
                        comparator,
                        threshold,
                        unit,
                        value,
                        severity,
                        event_state,
                    )
                )
            else:
                delivered, error = False, "Email connector missing address"
        elif connector_kind == "slack":
            url = connector_config.get("url")
            if url:
                delivered, error = await _with_retry(lambda: _post_slack(url, message_text))
            else:
                delivered, error = False, "Slack connector missing url"
        elif connector_kind == "discord":
            url = connector_config.get("url")
            if url:
                delivered, error = await _with_retry(lambda: _post_discord(url, message_text))
            else:
                delivered, error = False, "Discord connector missing url"
        elif connector_kind == "pagerduty":
            integration_key = connector_config.get("integration_key")
            if isinstance(integration_key, str) and integration_key:
                delivered, error = await _with_retry(
                    lambda: _post_pagerduty(
                        integration_key,
                        rule_id,
                        message_text,
                        severity,
                        event_state,
                    )
                )
            else:
                delivered, error = False, "PagerDuty connector missing integration_key"
        elif connector_kind == "opsgenie":
            api_key = connector_config.get("api_key")
            if isinstance(api_key, str) and api_key:
                delivered, error = await _with_retry(
                    lambda: _post_opsgenie(
                        api_key,
                        rule_id,
                        message_text,
                        severity,
                        event_state,
                    )
                )
            else:
                delivered, error = False, "Opsgenie connector missing api_key"
        else:
            delivered, error = False, f"Unknown connector kind '{connector_kind}'"
            logger.warning(
                f"Rule {rule_id} connector {connector_id} has unrecognized kind "
                f"'{connector_kind}'; skipping delivery"
            )

        connectors_sent.append(
            {
                "id": connector_id,
                "kind": connector_kind,
                "name": connector_name,
                "delivered": delivered,
                "error": error,
            }
        )

    return connectors_sent


def _format_alert_message(
    rule_name: str,
    metric: str,
    comparator: str,
    threshold: float,
    unit: str,
    value: float,
    event_state: typing.Literal["firing", "resolved"],
) -> str:
    fmt_threshold = f"{threshold:g}{unit if unit != 'count' else ''}".strip()
    if event_state == "firing":
        return f"Alert firing: {rule_name} ({metric} {comparator} {fmt_threshold}, now {value:g})"
    return f"Alert resolved: {rule_name} (now {value:g})"


async def _notification_recipients(
    project_id: int,
    rule_id: int,
    severity: str,
    auth_session: sa.ext.asyncio.AsyncSession,
) -> list[int]:
    members_result = await auth_session.execute(
        sa.text("SELECT account_id FROM project_members WHERE project_id = :pid"),
        {"pid": project_id},
    )
    member_ids = [row[0] for row in members_result.fetchall()]
    if not member_ids:
        return []

    prefs_result = await auth_session.execute(
        sa.text(
            """
            SELECT user_id FROM notification_preferences
            WHERE project_id = :pid AND user_id = ANY(:member_ids)
              AND (rule_id IS NULL OR rule_id = :rule_id)
              AND (severity IS NULL OR severity = :severity)
              AND muted = TRUE
            """
        ),
        {"pid": project_id, "member_ids": member_ids, "rule_id": rule_id, "severity": severity},
    )
    muted_ids = {row[0] for row in prefs_result.fetchall()}

    return [account_id for account_id in member_ids if account_id not in muted_ids]


async def _publish_in_app(
    project_id: int,
    rule_name: str,
    metric: str,
    comparator: str,
    threshold: float,
    unit: str,
    value: float,
    severity: str,
    now: datetime.datetime,
    event_state: typing.Literal["firing", "resolved"],
) -> None:
    fmt_threshold = f"{threshold:g}{unit if unit != 'count' else ''}".strip()
    if event_state == "firing":
        message = (
            f"Alert firing: {rule_name} ({metric} {comparator} {fmt_threshold}, now {value:g})"
        )
        error_type = "Alert firing"
    else:
        message = f"Alert resolved: {rule_name} (now {value:g})"
        error_type = "Alert resolved"

    notification = {
        "project_id": project_id,
        "level": _SEVERITY_TO_LEVEL.get(severity, "error"),
        "log_type": "alert",
        "message": message,
        "error_type": error_type,
        "timestamp": now.isoformat(),
        "severity": severity,
    }

    try:
        published = await redis_client.get_redis().publish(
            f"notifications:errors:{project_id}", json.dumps(notification)
        )
        logger.info(
            f"Published {event_state} alert to {published} SSE subscribers (project {project_id})"
        )
    except Exception as e:
        logger.warning(f"Failed to publish {event_state} alert to Redis: {e}")


async def _send_email(
    address: str,
    rule_name: str,
    metric: str,
    comparator: str,
    threshold: float,
    unit: str,
    value: float,
    severity: str,
    event_state: typing.Literal["firing", "resolved"],
) -> tuple[bool, str | None]:
    settings = config.get_settings()

    if not settings.EMAIL_ENABLED:
        logger.info(f"Email disabled (EMAIL_ENABLED=false); skipped alert to {address}")
        return False, "Email delivery disabled"

    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured; cannot send email alert")
        return False, "SMTP credentials not configured"

    fmt_threshold = f"{threshold:g}{unit if unit != 'count' else ''}".strip()
    if event_state == "firing":
        subject = f"[Ledger] {severity.upper()} alert firing: {rule_name}"
        body = (
            f"Alert rule '{rule_name}' is firing.\n\n"
            f"Metric: {metric}\n"
            f"Condition: {metric} {comparator} {fmt_threshold}\n"
            f"Current value: {value:g}\n"
            f"Severity: {severity}\n"
            "\n—\n"
            "Ledger automated alert. Do not reply.\n"
            "Manage rules: https://ledger.jtuta.cloud/alerts\n"
        )
    else:
        subject = f"[Ledger] Resolved: {rule_name}"
        body = (
            f"Alert rule '{rule_name}' has recovered.\n\n"
            f"Metric: {metric}\n"
            f"Current value: {value:g}\n"
            "\n—\n"
            "Ledger automated alert. Do not reply.\n"
            "Manage rules: https://ledger.jtuta.cloud/alerts\n"
        )

    message = email.message.EmailMessage()
    message["From"] = settings.SMTP_FROM or settings.SMTP_USER
    message["To"] = address
    message["Subject"] = subject
    message.set_content(body)

    tls_kwargs: dict = {}
    if settings.SMTP_PORT == 465:
        tls_kwargs["use_tls"] = True
    else:
        tls_kwargs["start_tls"] = settings.SMTP_USE_TLS

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            timeout=15,
            **tls_kwargs,
        )
        logger.info(f"Sent email alert to {address}")
        return True, None
    except Exception as e:
        logger.warning(f"Email delivery failed to {address}: {e}")
        return False, str(e)


async def _post_webhook(url: str, secret: str, payload: dict) -> tuple[bool, str | None]:
    settings = config.get_settings()

    try:
        await net_guard.validate_webhook_url(url, allow_http=settings.ALERT_WEBHOOK_ALLOW_HTTP)
    except net_guard.UnsafeWebhookURLError as e:
        logger.warning(f"Blocked unsafe webhook URL {url}: {e}")
        return False, str(e)

    body = json.dumps(payload).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    try:
        async with aiohttp.ClientSession() as http:
            response = await http.post(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Ledger-Signature": f"sha256={sig}",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            )
            if response.status >= 400:
                return False, f"Webhook returned HTTP {response.status}"
            return True, None
    except Exception as e:
        logger.warning(f"Webhook delivery failed to {url}: {e}")
        return False, str(e)


async def _post_slack(url: str, message: str) -> tuple[bool, str | None]:
    settings = config.get_settings()

    try:
        await net_guard.validate_webhook_url(url, allow_http=settings.ALERT_WEBHOOK_ALLOW_HTTP)
    except net_guard.UnsafeWebhookURLError as e:
        logger.warning(f"Blocked unsafe Slack webhook URL {url}: {e}")
        return False, str(e)

    try:
        async with aiohttp.ClientSession() as http:
            response = await http.post(
                url,
                json={"text": message},
                timeout=aiohttp.ClientTimeout(total=10),
            )
            if response.status >= 400:
                return False, f"Slack webhook returned HTTP {response.status}"
            return True, None
    except Exception as e:
        logger.warning(f"Slack delivery failed to {url}: {e}")
        return False, str(e)


async def _post_discord(url: str, message: str) -> tuple[bool, str | None]:
    settings = config.get_settings()

    try:
        await net_guard.validate_webhook_url(url, allow_http=settings.ALERT_WEBHOOK_ALLOW_HTTP)
    except net_guard.UnsafeWebhookURLError as e:
        logger.warning(f"Blocked unsafe Discord webhook URL {url}: {e}")
        return False, str(e)

    try:
        async with aiohttp.ClientSession() as http:
            response = await http.post(
                url,
                json={"content": message},
                timeout=aiohttp.ClientTimeout(total=10),
            )
            if response.status >= 400:
                return False, f"Discord webhook returned HTTP {response.status}"
            return True, None
    except Exception as e:
        logger.warning(f"Discord delivery failed to {url}: {e}")
        return False, str(e)


_PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"


async def _post_pagerduty(
    integration_key: str,
    rule_id: int,
    summary: str,
    severity: str,
    event_state: typing.Literal["firing", "resolved"],
) -> tuple[bool, str | None]:
    # events.pagerduty.com is a fixed vendor API host, not a user-supplied
    # URL, so the net_guard SSRF check (meant for arbitrary webhook/slack/
    # discord URLs) doesn't apply here.
    event_action = "trigger" if event_state == "firing" else "resolve"
    pd_severity = "critical" if severity == "critical" else "warning"
    body = {
        "routing_key": integration_key,
        "event_action": event_action,
        # dedup_key ties the trigger and the later resolve to the same
        # PagerDuty incident so it auto-resolves instead of staying open.
        "dedup_key": f"ledger-rule-{rule_id}",
        "payload": {
            "summary": summary,
            "severity": pd_severity,
            "source": "ledger",
        },
    }

    try:
        async with aiohttp.ClientSession() as http:
            response = await http.post(
                _PAGERDUTY_EVENTS_URL,
                json=body,
                timeout=aiohttp.ClientTimeout(total=10),
            )
            if response.status >= 400:
                return False, f"PagerDuty returned HTTP {response.status}"
            return True, None
    except Exception as e:
        logger.warning(f"PagerDuty delivery failed for rule {rule_id}: {e}")
        return False, str(e)


_OPSGENIE_ALERTS_URL = "https://api.opsgenie.com/v2/alerts"


async def _post_opsgenie(
    api_key: str,
    rule_id: int,
    message: str,
    severity: str,
    event_state: typing.Literal["firing", "resolved"],
) -> tuple[bool, str | None]:
    # api.opsgenie.com is a fixed vendor API host, not user-supplied -> no
    # net_guard SSRF check needed here either.
    alias = f"ledger-rule-{rule_id}"
    headers = {"Authorization": f"GenieKey {api_key}"}

    try:
        async with aiohttp.ClientSession() as http:
            if event_state == "firing":
                priority = "P1" if severity == "critical" else "P3"
                response = await http.post(
                    _OPSGENIE_ALERTS_URL,
                    json={"message": message, "alias": alias, "priority": priority},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                )
            else:
                # Close-by-alias: same alias pairs the resolve with the
                # earlier trigger, mirroring PagerDuty's dedup_key scheme.
                response = await http.post(
                    f"{_OPSGENIE_ALERTS_URL}/{alias}/close?identifierType=alias",
                    json={},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                )
            if response.status >= 400:
                return False, f"Opsgenie returned HTTP {response.status}"
            return True, None
    except Exception as e:
        logger.warning(f"Opsgenie delivery failed for rule {rule_id}: {e}")
        return False, str(e)
