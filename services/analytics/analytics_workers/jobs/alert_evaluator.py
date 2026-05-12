import datetime
import hashlib
import hmac
import json
import time
import typing

import aiohttp
import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.alert_evaluator")

_COMPARATORS: dict[str, typing.Callable[[float, float], bool]] = {
    ">":  lambda v, t: v > t,
    "<":  lambda v, t: v < t,
    ">=": lambda v, t: v >= t,
    "<=": lambda v, t: v <= t,
}


async def evaluate_alert_rules() -> None:
    start = time.perf_counter()

    try:
        async with database.get_auth_session() as auth_session:
            rules_result = await auth_session.execute(
                sa.text(
                    """
                    SELECT id, project_id, name, metric, tag_filter, comparator,
                           threshold, window_seconds, cooldown_seconds, severity,
                           channels, last_fired_at, last_state
                    FROM alert_rules
                    WHERE enabled = TRUE
                    ORDER BY id
                    """
                )
            )
            rules = rules_result.fetchall()

        if not rules:
            return

        async with database.get_logs_session() as logs_session:
            async with database.get_auth_session() as auth_session:
                for rule in rules:
                    try:
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
    tag_filter = rule[4] or {}
    comparator = rule[5]
    threshold = rule[6]
    window_seconds = rule[7]
    cooldown_seconds = rule[8]
    severity = rule[9]
    channels = rule[10] or []
    last_fired_at = rule[11]
    last_state = rule[12]

    value = await _query_metric(metric, project_id, tag_filter, window_seconds, logs_session)
    if value is None:
        return

    compare_fn = _COMPARATORS.get(comparator)
    if compare_fn is None:
        logger.warning(f"Unknown comparator '{comparator}' for rule {rule_id}")
        return

    breached = compare_fn(value, threshold)
    now = datetime.datetime.now(datetime.timezone.utc)

    if breached and last_state == "ok":
        cooldown_ok = (
            last_fired_at is None
            or (now - last_fired_at).total_seconds() >= cooldown_seconds
        )
        if cooldown_ok:
            await _fire_rule(rule_id, project_id, rule_name, metric, value, threshold,
                             severity, channels, auth_session)
            await auth_session.execute(
                sa.text(
                    "UPDATE alert_rules SET last_state = 'firing', last_fired_at = :now, "
                    "updated_at = :now WHERE id = :id"
                ),
                {"now": now, "id": rule_id},
            )
            await auth_session.commit()

    elif not breached and last_state == "firing":
        await _resolve_rule(rule_id, project_id, rule_name, metric, value, threshold,
                             severity, channels, auth_session)
        await auth_session.execute(
            sa.text(
                "UPDATE alert_rules SET last_state = 'ok', updated_at = :now WHERE id = :id"
            ),
            {"now": now, "id": rule_id},
        )
        await auth_session.commit()


async def _query_metric(
    metric: str,
    project_id: int,
    tag_filter: dict,
    window_seconds: int,
    session: sa.ext.asyncio.AsyncSession,
) -> float | None:
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=window_seconds)

    if metric == "error_rate":
        result = await session.execute(
            sa.text(
                """
                SELECT COALESCE(SUM(errors)::float / NULLIF(SUM(total), 0), 0)
                FROM error_rate_5m
                WHERE project_id = :pid AND bucket >= :since
                """
            ),
            {"pid": project_id, "since": since},
        )
        val = result.scalar()
        return float(val) if val is not None else None

    if metric == "log_volume":
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

    if metric == "endpoint_p95":
        result = await session.execute(
            sa.text(
                """
                SELECT COALESCE(AVG(p95_ms), 0)
                FROM endpoint_latency_1h
                WHERE project_id = :pid AND bucket >= :since
                """
            ),
            {"pid": project_id, "since": since},
        )
        val = result.scalar()
        return float(val) if val is not None else None

    if metric.startswith("custom:"):
        metric_name = metric[len("custom:"):]
        result = await session.execute(
            sa.text(
                """
                SELECT COALESCE(SUM(sum) / NULLIF(SUM(count), 0), 0)
                FROM custom_metrics_5m
                WHERE project_id = :pid
                  AND name = :name
                  AND bucket >= :since
                  AND (:tags = '{}'::jsonb OR tags @> :tags::jsonb)
                """
            ),
            {"pid": project_id, "name": metric_name, "since": since,
             "tags": json.dumps(tag_filter)},
        )
        val = result.scalar()
        return float(val) if val is not None else None

    logger.warning(f"Unknown metric type: {metric}")
    return None


async def _fire_rule(
    rule_id: int,
    project_id: int,
    rule_name: str,
    metric: str,
    value: float,
    threshold: float,
    severity: int,
    channels: list,
    auth_session: sa.ext.asyncio.AsyncSession,
) -> None:
    payload = {
        "rule_id": rule_id,
        "name": rule_name,
        "metric": metric,
        "value": value,
        "threshold": threshold,
        "fired_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    await _dispatch(rule_id, project_id, "alert_firing", severity, payload, channels, auth_session)


async def _resolve_rule(
    rule_id: int,
    project_id: int,
    rule_name: str,
    metric: str,
    value: float,
    threshold: float,
    severity: int,
    channels: list,
    auth_session: sa.ext.asyncio.AsyncSession,
) -> None:
    payload = {
        "rule_id": rule_id,
        "name": rule_name,
        "metric": metric,
        "value": value,
        "threshold": threshold,
        "resolved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    await _dispatch(rule_id, project_id, "alert_resolved", severity, payload, channels, auth_session)


async def _dispatch(
    rule_id: int,
    project_id: int,
    kind: str,
    severity: int,
    payload: dict,
    channel_ids: list,
    auth_session: sa.ext.asyncio.AsyncSession,
) -> None:
    if not channel_ids:
        return

    channels_result = await auth_session.execute(
        sa.text(
            """
            SELECT ac.id, ac.user_id, ac.kind, ac.config
            FROM alert_channels ac
            WHERE ac.id = ANY(:ids) AND ac.enabled = TRUE
            """
        ),
        {"ids": channel_ids},
    )
    channels = channels_result.fetchall()

    for channel in channels:
        channel_id = channel[0]
        user_id = channel[1]
        channel_kind = channel[2]
        channel_config = channel[3] or {}

        muted = await _is_muted(user_id, project_id, rule_id, severity, auth_session)
        if muted:
            continue

        if channel_kind == "in_app":
            await auth_session.execute(
                sa.text(
                    """
                    INSERT INTO notifications (user_id, project_id, kind, severity, payload)
                    VALUES (:user_id, :project_id, :kind, :severity, :payload::jsonb)
                    """
                ),
                {
                    "user_id": user_id,
                    "project_id": project_id,
                    "kind": kind,
                    "severity": severity,
                    "payload": json.dumps(payload),
                },
            )

        elif channel_kind == "webhook":
            url = channel_config.get("url")
            secret = channel_config.get("hmac_secret", "")
            if url:
                await _post_webhook(url, secret, payload)

        elif channel_kind == "email":
            logger.info(
                f"[email stub] Would send alert '{kind}' to {channel_config.get('email')} "
                f"for rule {rule_id}"
            )

    await auth_session.commit()


async def _is_muted(
    user_id: int,
    project_id: int,
    rule_id: int,
    severity: int,
    auth_session: sa.ext.asyncio.AsyncSession,
) -> bool:
    result = await auth_session.execute(
        sa.text(
            """
            SELECT muted FROM notification_preferences
            WHERE user_id = :user_id
              AND project_id = :project_id
              AND (rule_id IS NULL OR rule_id = :rule_id)
              AND (severity IS NULL OR severity = :severity)
            ORDER BY rule_id NULLS LAST
            LIMIT 1
            """
        ),
        {"user_id": user_id, "project_id": project_id, "rule_id": rule_id, "severity": severity},
    )
    row = result.fetchone()
    return bool(row[0]) if row else False


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
