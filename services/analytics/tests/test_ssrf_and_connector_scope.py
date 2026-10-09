"""Regression tests for outbound-request hardening and connector ownership."""

import datetime
import ipaddress
import json
import urllib.parse
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
import sqlalchemy as sa
from aiohttp import web
from aiohttp.test_utils import TestServer

import analytics_workers.database as database
import analytics_workers.jobs.alert_evaluator as alert_evaluator
import analytics_workers.jobs.net_guard as net_guard


class TestBlockedAddresses:
    @pytest.mark.parametrize(
        "address",
        [
            "127.0.0.1",
            "::ffff:127.0.0.1",  # IPv4-mapped loopback
            "::ffff:169.254.169.254",  # IPv4-mapped cloud metadata
            "100.64.0.1",  # shared address space (CGNAT)
            "172.20.0.5",  # docker bridge
            "0.0.0.0",
            "224.0.0.1",
        ],
    )
    def test_non_public_addresses_are_blocked(self, address):
        assert net_guard.is_blocked_address(ipaddress.ip_address(address))

    @pytest.mark.parametrize("address", ["93.184.215.14", "2606:4700:4700::1111"])
    def test_public_addresses_are_allowed(self, address):
        assert not net_guard.is_blocked_address(ipaddress.ip_address(address))


@pytest.mark.asyncio
class TestRedirectHops:
    async def _local_server(self) -> TestServer:
        app = web.Application()
        app.router.add_get("/start", lambda r: web.HTTPFound("/final"))
        app.router.add_get("/final", lambda r: web.Response(status=204))
        app.router.add_get(
            "/to-metadata", lambda r: web.HTTPFound("http://169.254.169.254/latest/meta-data")
        )
        server = TestServer(app)
        await server.start_server()
        return server

    async def test_allowed_redirects_are_followed(self):
        server = await self._local_server()
        try:
            with patch.object(net_guard, "validate_webhook_url", AsyncMock(return_value=None)):
                async with net_guard.guarded_session() as http:
                    status = await net_guard.get_following_safe_redirects(
                        http,
                        f"http://127.0.0.1:{server.port}/start",
                        True,
                        aiohttp.ClientTimeout(total=5),
                    )
            assert status == 204
        finally:
            await server.close()

    async def test_redirect_into_internal_network_is_refused(self):
        server = await self._local_server()
        original = net_guard.validate_webhook_url

        async def allow_only_test_server(url: str, allow_http: bool = False) -> None:
            if urllib.parse.urlparse(url).hostname == "127.0.0.1":
                return
            await original(url, allow_http=allow_http)

        try:
            with patch.object(net_guard, "validate_webhook_url", allow_only_test_server):
                async with net_guard.guarded_session() as http:
                    with pytest.raises(net_guard.UnsafeWebhookURLError):
                        await net_guard.get_following_safe_redirects(
                            http,
                            f"http://127.0.0.1:{server.port}/to-metadata",
                            True,
                            aiohttp.ClientTimeout(total=5),
                        )
        finally:
            await server.close()


async def _insert(session, sql: str, **params) -> int:
    return (await session.execute(sa.text(sql), params)).scalar()


@pytest.mark.asyncio
class TestConnectorOwnership:
    async def test_rule_only_delivers_through_connectors_of_project_members(self, test_dbs):
        now = datetime.datetime.now(datetime.timezone.utc)
        async with database.get_auth_session() as session:
            account = (
                "INSERT INTO accounts (email, password_hash, name, plan, status, email_verified, "
                "created_at, updated_at) VALUES (:email, 'x', 'n', 'free', 'active', TRUE, :now, "
                ":now) RETURNING id"
            )
            member = await _insert(session, account, email="member@example.com", now=now)
            outsider = await _insert(session, account, email="outsider@example.com", now=now)
            project = await _insert(
                session,
                "INSERT INTO projects (account_id, name, slug, environment, retention_days, "
                "logs_daily_quota, spans_daily_quota, metrics_daily_quota, created_at, updated_at) "
                "VALUES (:a, 'p', 'p', 'production', 30, 100000, 300000, 100000, :now, :now) "
                "RETURNING id",
                a=member,
                now=now,
            )
            await session.execute(
                sa.text(
                    "INSERT INTO project_members (project_id, account_id, role, joined_at) "
                    "VALUES (:p, :a, 'owner', :now)"
                ),
                {"p": project, "a": member, "now": now},
            )
            connector = (
                "INSERT INTO connectors (account_id, kind, name, config, enabled, created_at, "
                "updated_at) VALUES (:a, 'webhook', 'hook', CAST(:config AS jsonb), TRUE, :now, "
                ":now) RETURNING id"
            )
            own = await _insert(
                session,
                connector,
                a=member,
                now=now,
                config=json.dumps({"url": "https://member.example/hook"}),
            )
            foreign = await _insert(
                session,
                connector,
                a=outsider,
                now=now,
                config=json.dumps({"url": "https://outsider.example/hook"}),
            )
            rule = await _insert(
                session,
                "INSERT INTO alert_rules (project_id, name, metric_type, comparator, threshold, "
                "unit, severity, enabled, state, for_minutes, cooldown_minutes, created_at, "
                "updated_at) VALUES (:p, 'r', 'error_rate_all', '>', 1, '%', 'warning', TRUE, "
                "'ok', 0, 0, :now, :now) RETURNING id",
                p=project,
                now=now,
            )
            for connector_id in (own, foreign):
                await session.execute(
                    sa.text(
                        "INSERT INTO alert_rule_connectors (rule_id, connector_id) VALUES (:r, :c)"
                    ),
                    {"r": rule, "c": connector_id},
                )
            await session.commit()

        delivered_to: list[str] = []

        async def record_webhook(url, secret, payload):
            delivered_to.append(url)
            return True, None

        with patch.object(alert_evaluator, "_post_webhook", side_effect=record_webhook):
            async with database.get_auth_session() as session:
                sent = await alert_evaluator._dispatch(
                    rule,
                    project,
                    "r",
                    "error_rate_all",
                    ">",
                    1,
                    "%",
                    2.0,
                    "warning",
                    now,
                    session,
                    event_state="firing",
                )

        assert delivered_to == ["https://member.example/hook"]
        assert [c["id"] for c in sent] == [own]
