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
    ">":  lambda v, t: v > t,
    "<":  lambda v, t: v < t,
    ">=": lambda v, t: v >= t,
    "<=": lambda v, t: v <= t,
}

_LOOKBACK_MINUTES = 10
_LATENCY_LOOKBACK_MINUTES = 60


async def evaluate_alert_rules() -> None:
    start = time.perf_counter()

    try:
        async with database.get_auth_session() as auth_session:
            rules_result = await auth_session.execute(
                sa.text(
                    """
                    SELECT id, project_id, name, metric_type, comparator,
                           threshold, unit, severity, state
                    FROM alert_rules
                    WHERE enabled = TRUE
                    ORDER BY id
                    """
                )
            )
            rules = rules_result.fetchall()

        if not rules:
            return

        for rule in rules:
            try:
                async with database.get_logs_session() as logs_session:
                    async with database.get_auth_session() as auth_session:
                        await _evaluate_rule(rule, logs_session, auth_session)
            except Exception as e:
                logger.error(f"Rule {rule[0]} evaluation failed: {e}", exc_info=True)

        elapsed = time.perf_counter() - start
        logger.info(f"Alert evaluation done in {elapsed:.2f}s for {len(rules)} rules")

    except Exception as e:
        logger.error(f"Alert evaluator failed: {e}", exc_info=True)
        raise


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

    value = await _query_metric(metric, project_id, logs_session)
    if value is None:
        return

    compare_fn = _COMPARATORS.get(comparator)
    if compare_fn is None:
        logger.warning(f"Unknown comparator '{comparator}' for rule {rule_id}")
        return

    normalized_threshold = _normalize_threshold(metric, threshold, unit)
    breached = compare_fn(value, normalized_threshold)
    now = datetime.datetime.now(datetime.timezone.utc)

    logger.info(
        f"Rule {rule_id} '{rule_name}' project={project_id} metric={metric} "
        f"value={value:.4f} {comparator} threshold={normalized_threshold:.4f} "
        f"breached={breached} state={state}"
    )

    if breached and state == "ok":
        await _record_and_dispatch(
            rule_id, project_id, rule_name, metric, comparator, threshold,
            unit, value, severity, "firing", auth_session,
        )
        await auth_session.execute(
            sa.text(
                "UPDATE alert_rules SET state = 'firing', last_fired_at = :now, "
                "fired_value = :val, updated_at = :now WHERE id = :id"
            ),
            {"now": now, "val": value, "id": rule_id},
        )
        await auth_session.commit()

    elif not breached and state == "firing":
        await _record_and_dispatch(
            rule_id, project_id, rule_name, metric, comparator, threshold,
            unit, value, severity, "resolved", auth_session,
        )
        await auth_session.execute(
            sa.text(
                "UPDATE alert_rules SET state = 'ok', updated_at = :now WHERE id = :id"
            ),
            {"now": now, "id": rule_id},
        )
        await auth_session.commit()


def _normalize_threshold(metric: str, threshold: float, unit: str) -> float:
    if metric in ("p95_latency", "p99_latency"):
        if unit == "s":
            return threshold * 1000.0
        return threshold
    return threshold


async def _query_metric(
    metric: str,
    project_id: int,
    session: sa.ext.asyncio.AsyncSession,
) -> float | None:
    now = datetime.datetime.now(datetime.timezone.utc)
    since = now - datetime.timedelta(minutes=_LOOKBACK_MINUTES)
    latency_since = now - datetime.timedelta(minutes=_LATENCY_LOOKBACK_MINUTES)

    if metric in ("p95_latency", "p99_latency"):
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

    logger.warning(f"Unknown metric type: {metric}")
    return None


async def _record_and_dispatch(
    rule_id: int,
    project_id: int,
    rule_name: str,
    metric: str,
    comparator: str,
    threshold: float,
    unit: str,
    value: float,
    severity: str,
    state: str,
    auth_session: sa.ext.asyncio.AsyncSession,
) -> None:
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

    owner_result = await auth_session.execute(
        sa.text("SELECT account_id FROM projects WHERE id = :pid"),
        {"pid": project_id},
    )
    owner_row = owner_result.fetchone()
    owner_id = owner_row[0] if owner_row else None

    kind = "alert_firing" if state == "firing" else "alert_resolved"
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "rule_id": rule_id,
        "name": rule_name,
        "metric": metric,
        "comparator": comparator,
        "threshold": threshold,
        "unit": unit,
        "value": value,
        "state": state,
        "fired_at": now.isoformat(),
    }

    connectors_sent: list[dict] = []
    for connector in connectors:
        connector_id = connector[0]
        connector_kind = connector[1]
        connector_name = connector[2]
        connector_config = connector[3] or {}

        if connector_kind == "in_app":
            if owner_id is not None:
                await auth_session.execute(
                    sa.text(
                        """
                        INSERT INTO notifications
                            (user_id, project_id, kind, severity, payload)
                        VALUES (:user_id, :project_id, :kind, :severity, :payload::jsonb)
                        """
                    ),
                    {
                        "user_id": owner_id,
                        "project_id": project_id,
                        "kind": kind,
                        "severity": severity,
                        "payload": json.dumps(payload),
                    },
                )
                await _publish_in_app(
                    project_id, rule_name, metric, comparator,
                    threshold, unit, value, severity, state, now,
                )
        elif connector_kind == "webhook":
            url = connector_config.get("url")
            secret = connector_config.get("hmac_secret", "")
            if url:
                await _post_webhook(url, secret, payload)
        elif connector_kind == "email":
            address = connector_config.get("address")
            if address:
                await _send_email(
                    address, rule_name, metric, comparator,
                    threshold, unit, value, severity, state,
                )

        connectors_sent.append(
            {"id": connector_id, "kind": connector_kind, "name": connector_name}
        )

    await auth_session.execute(
        sa.text(
            """
            INSERT INTO alert_events
                (rule_id, project_id, rule_name, metric_type, comparator,
                 threshold, unit, value, severity, state, connectors_sent, fired_at)
            VALUES
                (:rule_id, :project_id, :rule_name, :metric, :comparator,
                 :threshold, :unit, :value, :severity, :state,
                 :connectors_sent::jsonb, :fired_at)
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
            "state": state,
            "connectors_sent": json.dumps(connectors_sent),
            "fired_at": now,
        },
    )
    await auth_session.commit()


async def _publish_in_app(
    project_id: int,
    rule_name: str,
    metric: str,
    comparator: str,
    threshold: float,
    unit: str,
    value: float,
    severity: str,
    state: str,
    now: datetime.datetime,
) -> None:
    fmt_threshold = f"{threshold:g}{unit if unit != 'count' else ''}".strip()
    if state == "firing":
        message = (
            f"Alert firing: {rule_name} "
            f"({metric} {comparator} {fmt_threshold}, now {value:g})"
        )
        error_type = "Alert firing"
    else:
        message = f"Alert resolved: {rule_name}"
        error_type = "Alert resolved"

    notification = {
        "project_id": project_id,
        "level": _SEVERITY_TO_LEVEL.get(severity, "error"),
        "log_type": "alert",
        "message": message,
        "error_type": error_type,
        "timestamp": now.isoformat(),
        "alert_state": state,
        "severity": severity,
    }

    try:
        published = await redis_client.get_redis().publish(
            f"notifications:errors:{project_id}", json.dumps(notification)
        )
        logger.info(
            f"Published in_app alert to {published} SSE subscribers "
            f"(project {project_id}, state {state})"
        )
    except Exception as e:
        logger.warning(f"Failed to publish in_app alert to Redis: {e}")


async def _send_email(
    address: str,
    rule_name: str,
    metric: str,
    comparator: str,
    threshold: float,
    unit: str,
    value: float,
    severity: str,
    state: str,
) -> None:
    settings = config.get_settings()

    if not settings.EMAIL_ENABLED:
        logger.info(
            f"Email disabled (EMAIL_ENABLED=false); skipped alert to {address}"
        )
        return

    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured; cannot send email alert")
        return

    fmt_threshold = f"{threshold:g}{unit if unit != 'count' else ''}".strip()
    if state == "firing":
        subject = f"[Ledger] {severity.upper()} alert firing: {rule_name}"
        body = (
            f"Alert rule '{rule_name}' is firing.\n\n"
            f"Metric: {metric}\n"
            f"Condition: {metric} {comparator} {fmt_threshold}\n"
            f"Current value: {value:g}\n"
            f"Severity: {severity}\n"
        )
    else:
        subject = f"[Ledger] Alert resolved: {rule_name}"
        body = (
            f"Alert rule '{rule_name}' has resolved.\n\n"
            f"Metric: {metric}\n"
            f"Current value: {value:g}\n"
        )

    body += (
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
        logger.info(f"Sent email alert to {address} (state {state})")
    except Exception as e:
        logger.warning(f"Email delivery failed to {address}: {e}")


async def _post_webhook(url: str, secret: str, payload: dict) -> None:
    body = json.dumps(payload).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    try:
        async with aiohttp.ClientSession() as http:
            await http.post(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Ledger-Signature": f"sha256={sig}",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        logger.warning(f"Webhook delivery failed to {url}: {e}")
