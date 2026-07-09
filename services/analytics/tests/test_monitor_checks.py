import datetime
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from aiohttp import web
from aiohttp.test_utils import TestServer

import analytics_workers.database as database
import analytics_workers.jobs.monitor_checks as monitor_checks


async def _seed_account_project(auth_session) -> tuple[int, int]:
    result = await auth_session.execute(
        sa.text("""
            INSERT INTO accounts
                (email, password_hash, name, plan, status, email_verified, created_at, updated_at)
            VALUES
                ('monitor@example.com', 'x', 'Monitor Owner', 'free', 'active', TRUE, NOW(), NOW())
            RETURNING id
        """)
    )
    account_id = result.scalar()

    result = await auth_session.execute(
        sa.text("""
            INSERT INTO projects
                (account_id, name, slug, environment, retention_days, daily_quota, created_at, updated_at)
            VALUES
                (:account_id, 'Monitor Project', 'monitor-project', 'production', 30, 100000, NOW(), NOW())
            RETURNING id
        """),
        {"account_id": account_id},
    )
    project_id = result.scalar()

    await auth_session.execute(
        sa.text("""
            INSERT INTO project_members (project_id, account_id, role, joined_at)
            VALUES (:project_id, :account_id, 'owner', NOW())
        """),
        {"project_id": project_id, "account_id": account_id},
    )
    await auth_session.commit()
    return account_id, project_id


async def _insert_http_monitor(
    auth_session,
    project_id: int,
    target_url: str,
    expected_status: int = 200,
    interval_s: int = 60,
    timeout_s: int = 5,
    state: str = "unknown",
) -> int:
    result = await auth_session.execute(
        sa.text("""
            INSERT INTO monitors
                (project_id, kind, name, target_url, interval_s, timeout_s, expected_status, grace_s, state, enabled, created_at, updated_at)
            VALUES
                (:project_id, 'http', 'Test HTTP Monitor', :target_url, :interval_s, :timeout_s, :expected_status, 0, :state, TRUE, NOW(), NOW())
            RETURNING id
        """),
        {
            "project_id": project_id,
            "target_url": target_url,
            "interval_s": interval_s,
            "timeout_s": timeout_s,
            "expected_status": expected_status,
            "state": state,
        },
    )
    monitor_id = result.scalar()
    await auth_session.commit()
    return monitor_id


async def _insert_heartbeat_monitor(
    auth_session,
    project_id: int,
    interval_s: int = 60,
    grace_s: int = 0,
    state: str = "unknown",
    created_at: datetime.datetime | None = None,
) -> int:
    created_at = created_at or datetime.datetime.now(datetime.timezone.utc)
    result = await auth_session.execute(
        sa.text("""
            INSERT INTO monitors
                (project_id, kind, name, token, interval_s, timeout_s, expected_status, grace_s, state, enabled, created_at, updated_at)
            VALUES
                (:project_id, 'heartbeat', 'Test Heartbeat Monitor', :token, :interval_s, 10, 200, :grace_s, :state, TRUE, :created_at, NOW())
            RETURNING id
        """),
        {
            "project_id": project_id,
            "token": f"tok-{project_id}-{state}-{interval_s}",
            "interval_s": interval_s,
            "grace_s": grace_s,
            "state": state,
            "created_at": created_at,
        },
    )
    monitor_id = result.scalar()
    await auth_session.commit()
    return monitor_id


@pytest.fixture
def bypass_ssrf_guard():
    with patch(
        "analytics_workers.jobs.net_guard.validate_webhook_url",
        return_value=None,
    ):
        yield


@pytest.mark.asyncio
class TestHttpMonitorChecks:
    async def test_successful_check_transitions_unknown_to_up(self, test_dbs, bypass_ssrf_guard):
        app = web.Application()
        app.router.add_get("/health", lambda r: web.Response(status=200, text="ok"))
        server = TestServer(app)
        await server.start_server()
        try:
            async with database.get_auth_session() as auth_session:
                _account_id, project_id = await _seed_account_project(auth_session)
                monitor_id = await _insert_http_monitor(
                    auth_session,
                    project_id,
                    target_url=f"http://127.0.0.1:{server.port}/health",
                    expected_status=200,
                )

            await monitor_checks.check_monitors()

            async with database.get_auth_session() as auth_session:
                state = (
                    await auth_session.execute(
                        sa.text("SELECT state FROM monitors WHERE id = :id"), {"id": monitor_id}
                    )
                ).scalar()
                assert state == "up"

                check = (
                    await auth_session.execute(
                        sa.text(
                            "SELECT ok, status_code FROM monitor_checks WHERE monitor_id = :id"
                        ),
                        {"id": monitor_id},
                    )
                ).fetchone()
                assert check.ok is True
                assert check.status_code == 200
        finally:
            await server.close()

    async def test_unexpected_status_transitions_to_down(self, test_dbs, bypass_ssrf_guard):
        app = web.Application()
        app.router.add_get("/health", lambda r: web.Response(status=500, text="error"))
        server = TestServer(app)
        await server.start_server()
        try:
            async with database.get_auth_session() as auth_session:
                _account_id, project_id = await _seed_account_project(auth_session)
                monitor_id = await _insert_http_monitor(
                    auth_session,
                    project_id,
                    target_url=f"http://127.0.0.1:{server.port}/health",
                    expected_status=200,
                    state="up",
                )

            await monitor_checks.check_monitors()

            async with database.get_auth_session() as auth_session:
                state = (
                    await auth_session.execute(
                        sa.text("SELECT state FROM monitors WHERE id = :id"), {"id": monitor_id}
                    )
                ).scalar()
                assert state == "down"
        finally:
            await server.close()

    async def test_down_to_up_transition_creates_notification(self, test_dbs, bypass_ssrf_guard):
        app = web.Application()
        app.router.add_get("/health", lambda r: web.Response(status=200))
        server = TestServer(app)
        await server.start_server()
        try:
            async with database.get_auth_session() as auth_session:
                account_id, project_id = await _seed_account_project(auth_session)
                await _insert_http_monitor(
                    auth_session,
                    project_id,
                    target_url=f"http://127.0.0.1:{server.port}/health",
                    expected_status=200,
                    state="down",
                )

            await monitor_checks.check_monitors()

            async with database.get_auth_session() as auth_session:
                notification = (
                    await auth_session.execute(
                        sa.text("SELECT kind, severity FROM notifications WHERE user_id = :uid"),
                        {"uid": account_id},
                    )
                ).fetchone()
                assert notification is not None
                assert notification.kind == "alert_resolved"
                assert notification.severity == "info"
        finally:
            await server.close()

    async def test_same_state_produces_no_notification(self, test_dbs, bypass_ssrf_guard):
        app = web.Application()
        app.router.add_get("/health", lambda r: web.Response(status=200))
        server = TestServer(app)
        await server.start_server()
        try:
            async with database.get_auth_session() as auth_session:
                account_id, project_id = await _seed_account_project(auth_session)
                await _insert_http_monitor(
                    auth_session,
                    project_id,
                    target_url=f"http://127.0.0.1:{server.port}/health",
                    expected_status=200,
                    state="up",
                )

            await monitor_checks.check_monitors()

            async with database.get_auth_session() as auth_session:
                count = (
                    await auth_session.execute(
                        sa.text("SELECT COUNT(*) FROM notifications WHERE user_id = :uid"),
                        {"uid": account_id},
                    )
                ).scalar()
                assert count == 0
        finally:
            await server.close()

    async def test_not_due_monitor_is_skipped(self, test_dbs, bypass_ssrf_guard):
        async with database.get_auth_session() as auth_session:
            _account_id, project_id = await _seed_account_project(auth_session)
            monitor_id = await _insert_http_monitor(
                auth_session,
                project_id,
                target_url="http://127.0.0.1:9/unreachable",
                interval_s=3600,
                state="up",
            )
            # Record a very recent check so the monitor isn't due yet.
            await auth_session.execute(
                sa.text(
                    "INSERT INTO monitor_checks (monitor_id, checked_at, ok) "
                    "VALUES (:mid, :now, TRUE)"
                ),
                {"mid": monitor_id, "now": datetime.datetime.now(datetime.timezone.utc)},
            )
            await auth_session.commit()

        await monitor_checks.check_monitors()

        async with database.get_auth_session() as auth_session:
            count = (
                await auth_session.execute(
                    sa.text("SELECT COUNT(*) FROM monitor_checks WHERE monitor_id = :id"),
                    {"id": monitor_id},
                )
            ).scalar()
            # Only the manually-seeded check above - check_monitors() must not
            # have probed this monitor since it isn't due yet.
            assert count == 1


@pytest.mark.asyncio
class TestHeartbeatMonitorChecks:
    async def test_recent_ping_keeps_monitor_up(self, test_dbs):
        async with database.get_auth_session() as auth_session:
            _account_id, project_id = await _seed_account_project(auth_session)
            monitor_id = await _insert_heartbeat_monitor(
                auth_session, project_id, interval_s=60, grace_s=10, state="up"
            )
            await auth_session.execute(
                sa.text(
                    "INSERT INTO monitor_checks (monitor_id, checked_at, ok) "
                    "VALUES (:mid, :now, TRUE)"
                ),
                {"mid": monitor_id, "now": datetime.datetime.now(datetime.timezone.utc)},
            )
            await auth_session.commit()

        await monitor_checks.check_monitors()

        async with database.get_auth_session() as auth_session:
            state = (
                await auth_session.execute(
                    sa.text("SELECT state FROM monitors WHERE id = :id"), {"id": monitor_id}
                )
            ).scalar()
            assert state == "up"

    async def test_overdue_ping_transitions_to_down(self, test_dbs):
        stale_ping = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=120)
        async with database.get_auth_session() as auth_session:
            _account_id, project_id = await _seed_account_project(auth_session)
            monitor_id = await _insert_heartbeat_monitor(
                auth_session, project_id, interval_s=60, grace_s=10, state="up"
            )
            await auth_session.execute(
                sa.text(
                    "INSERT INTO monitor_checks (monitor_id, checked_at, ok) "
                    "VALUES (:mid, :now, TRUE)"
                ),
                {"mid": monitor_id, "now": stale_ping},
            )
            await auth_session.commit()

        await monitor_checks.check_monitors()

        async with database.get_auth_session() as auth_session:
            state = (
                await auth_session.execute(
                    sa.text("SELECT state FROM monitors WHERE id = :id"), {"id": monitor_id}
                )
            ).scalar()
            assert state == "down"

    async def test_first_ever_check_sets_baseline_without_notification(self, test_dbs):
        async with database.get_auth_session() as auth_session:
            account_id, project_id = await _seed_account_project(auth_session)
            monitor_id = await _insert_heartbeat_monitor(
                auth_session,
                project_id,
                interval_s=60,
                grace_s=10,
                state="unknown",
                created_at=datetime.datetime.now(datetime.timezone.utc),
            )

        await monitor_checks.check_monitors()

        async with database.get_auth_session() as auth_session:
            state = (
                await auth_session.execute(
                    sa.text("SELECT state FROM monitors WHERE id = :id"), {"id": monitor_id}
                )
            ).scalar()
            assert state == "up"

            count = (
                await auth_session.execute(
                    sa.text("SELECT COUNT(*) FROM notifications WHERE user_id = :uid"),
                    {"uid": account_id},
                )
            ).scalar()
            assert count == 0
