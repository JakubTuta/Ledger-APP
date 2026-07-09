import asyncio
import datetime
import json
import time
import typing

import aiohttp
import sqlalchemy as sa

import analytics_workers.config as config
import analytics_workers.database as database
import analytics_workers.jobs.net_guard as net_guard
import analytics_workers.redis_client as redis_client
import analytics_workers.utils.logging as logging

logger = logging.get_logger("jobs.monitor_checks")

_HTTP_CONCURRENCY = 20

_SEVERITY_TO_LEVEL: dict[str, str] = {
    "critical": "critical",
    "warning": "error",
    "info": "error",
}


async def check_monitors() -> None:
    """Run one pass of both http and heartbeat monitor checks."""
    start = time.perf_counter()

    try:
        async with database.get_auth_session() as auth_session:
            await _check_http_monitors(auth_session)
            await _check_heartbeat_monitors(auth_session)

        elapsed = time.perf_counter() - start
        logger.info(f"Monitor check pass done in {elapsed:.2f}s")

    except Exception as e:
        logger.error(f"Monitor checker failed: {e}", exc_info=True)
        raise


async def _check_http_monitors(auth_session: sa.ext.asyncio.AsyncSession) -> None:
    result = await auth_session.execute(
        sa.text(
            """
            SELECT m.id, m.project_id, m.name, m.target_url, m.interval_s,
                   m.timeout_s, m.expected_status, m.state,
                   (SELECT checked_at FROM monitor_checks mc
                    WHERE mc.monitor_id = m.id
                    ORDER BY mc.checked_at DESC LIMIT 1) AS last_checked_at
            FROM monitors m
            WHERE m.kind = 'http' AND m.enabled = TRUE
            """
        )
    )
    monitors = result.fetchall()
    if not monitors:
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    due = [
        m
        for m in monitors
        if m.last_checked_at is None or (now - m.last_checked_at).total_seconds() >= m.interval_s
    ]
    if not due:
        return

    settings = config.get_settings()
    semaphore = asyncio.Semaphore(_HTTP_CONCURRENCY)

    async with aiohttp.ClientSession() as http:

        async def _probe(m: typing.Any):
            async with semaphore:
                return await _probe_http(http, m, settings)

        results = await asyncio.gather(*[_probe(m) for m in due])

    for m, res in zip(due, results):
        try:
            await _record_http_check(auth_session, m, res)
        except Exception as e:
            logger.error(f"Failed to record http check for monitor {m.id}: {e}", exc_info=True)


async def _probe_http(
    http: aiohttp.ClientSession,
    m: typing.Any,
    settings: typing.Any,
) -> tuple[bool, int | None, int | None, str | None]:
    target_url = m.target_url
    if not target_url:
        return False, None, None, "Monitor has no target_url configured"

    try:
        await net_guard.validate_webhook_url(
            target_url, allow_http=settings.ALERT_WEBHOOK_ALLOW_HTTP
        )
    except net_guard.UnsafeWebhookURLError as e:
        logger.warning(f"Blocked unsafe monitor target URL {target_url}: {e}")
        return False, None, None, f"Blocked unsafe target URL: {e}"

    start = time.perf_counter()
    try:
        async with http.get(
            target_url,
            timeout=aiohttp.ClientTimeout(total=m.timeout_s),
            allow_redirects=True,
        ) as response:
            latency_ms = int((time.perf_counter() - start) * 1000)
            ok = response.status == m.expected_status
            error = None if ok else f"Expected status {m.expected_status}, got {response.status}"
            return ok, latency_ms, response.status, error

    except asyncio.TimeoutError:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return False, latency_ms, None, f"Request timed out after {m.timeout_s}s"

    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return False, latency_ms, None, str(e)


async def _record_http_check(
    auth_session: sa.ext.asyncio.AsyncSession,
    m: typing.Any,
    res: tuple[bool, int | None, int | None, str | None],
) -> None:
    ok, latency_ms, status_code, error = res
    now = datetime.datetime.now(datetime.timezone.utc)

    await auth_session.execute(
        sa.text(
            """
            INSERT INTO monitor_checks (monitor_id, checked_at, ok, latency_ms, status_code, error)
            VALUES (:mid, :now, :ok, :latency_ms, :status_code, :error)
            """
        ),
        {
            "mid": m.id,
            "now": now,
            "ok": ok,
            "latency_ms": latency_ms,
            "status_code": status_code,
            "error": error,
        },
    )

    await _apply_transition(
        auth_session,
        monitor_id=m.id,
        project_id=m.project_id,
        monitor_name=m.name,
        monitor_kind="http",
        prev_state=m.state,
        new_ok=ok,
        now=now,
    )
    await auth_session.commit()


async def _check_heartbeat_monitors(auth_session: sa.ext.asyncio.AsyncSession) -> None:
    result = await auth_session.execute(
        sa.text(
            """
            SELECT m.id, m.project_id, m.name, m.interval_s, m.grace_s, m.state, m.created_at,
                   (SELECT checked_at FROM monitor_checks mc
                    WHERE mc.monitor_id = m.id
                    ORDER BY mc.checked_at DESC LIMIT 1) AS last_ping_at
            FROM monitors m
            WHERE m.kind = 'heartbeat' AND m.enabled = TRUE
            """
        )
    )
    monitors = result.fetchall()
    if not monitors:
        return

    now = datetime.datetime.now(datetime.timezone.utc)

    for m in monitors:
        baseline = m.last_ping_at or m.created_at
        overdue = (now - baseline).total_seconds() > (m.interval_s + m.grace_s)
        new_ok = not overdue

        try:
            await _apply_transition(
                auth_session,
                monitor_id=m.id,
                project_id=m.project_id,
                monitor_name=m.name,
                monitor_kind="heartbeat",
                prev_state=m.state,
                new_ok=new_ok,
                now=now,
            )
            await auth_session.commit()
        except Exception as e:
            logger.error(f"Failed to evaluate heartbeat monitor {m.id}: {e}", exc_info=True)


async def _apply_transition(
    auth_session: sa.ext.asyncio.AsyncSession,
    *,
    monitor_id: int,
    project_id: int,
    monitor_name: str,
    monitor_kind: str,
    prev_state: str,
    new_ok: bool,
    now: datetime.datetime,
) -> None:
    new_state = "up" if new_ok else "down"
    if prev_state == new_state:
        return

    await auth_session.execute(
        sa.text("UPDATE monitors SET state = :state, updated_at = :now WHERE id = :id"),
        {"state": new_state, "now": now, "id": monitor_id},
    )

    # Only alert on a transition between two *known* states (up <-> down).
    # unknown -> up/down (first-ever check) sets a baseline quietly.
    if prev_state in ("up", "down"):
        await _notify_transition(
            auth_session, project_id, monitor_id, monitor_name, monitor_kind, new_state, now
        )


async def _notify_transition(
    auth_session: sa.ext.asyncio.AsyncSession,
    project_id: int,
    monitor_id: int,
    monitor_name: str,
    monitor_kind: str,
    new_state: typing.Literal["up", "down"],
    now: datetime.datetime,
) -> None:
    notification_kind = "alert_firing" if new_state == "down" else "alert_resolved"
    severity = "critical" if new_state == "down" else "info"

    payload = {
        "monitor_id": monitor_id,
        "monitor_name": monitor_name,
        "monitor_kind": monitor_kind,
        "state": new_state,
        "checked_at": now.isoformat(),
    }

    members_result = await auth_session.execute(
        sa.text("SELECT account_id FROM project_members WHERE project_id = :pid"),
        {"pid": project_id},
    )
    member_ids = [row[0] for row in members_result.fetchall()]

    for account_id in member_ids:
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
                "severity": severity,
                "payload": json.dumps(payload),
            },
        )
    await auth_session.commit()

    if new_state == "down":
        message = f"Monitor down: {monitor_name}"
        error_type = "Monitor down"
    else:
        message = f"Monitor recovered: {monitor_name}"
        error_type = "Monitor recovered"

    notification = {
        "project_id": project_id,
        "level": _SEVERITY_TO_LEVEL.get(severity, "error"),
        "log_type": "monitor",
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
            f"Published monitor {new_state} to {published} SSE subscribers "
            f"(project {project_id}, monitor {monitor_id})"
        )
    except Exception as e:
        logger.warning(f"Failed to publish monitor {new_state} to Redis: {e}")
