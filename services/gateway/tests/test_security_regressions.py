"""Regression tests for the authorization and abuse-limit fixes."""

import asyncio
import gzip
import json
import socket
from unittest.mock import AsyncMock, patch

import grpc
import httpx
import pytest

import gateway_service.proto.auth_pb2 as auth_pb2
import gateway_service.proto.query_pb2 as query_pb2
import gateway_service.services.net_guard as net_guard
import tests.test_base as test_base

API_KEY = "ledger_test_key"


def _otlp_log_body() -> bytes:
    return json.dumps(
        {
            "resourceLogs": [
                {
                    "resource": {
                        "attributes": [{"key": "service.name", "value": {"stringValue": "svc"}}]
                    },
                    "scopeLogs": [
                        {"logRecords": [{"severityNumber": 9, "body": {"stringValue": "hi"}}]}
                    ],
                }
            ]
        }
    ).encode()


class _UnavailableError(grpc.RpcError):
    def code(self):
        return grpc.StatusCode.UNAVAILABLE

    def details(self):
        return "ingestion down"


@pytest.mark.asyncio
class TestApiKeyScope(test_base.BaseGatewayTest):
    async def test_api_key_cannot_read_account_data(self):
        await self.set_api_key_cache(API_KEY, project_id=1, account_id=1)

        response = await self.client.get("/api/v1/accounts/me", headers={"X-API-Key": API_KEY})

        assert response.status_code == 401

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/accounts/2fa/setup",
            "/api/v1/accounts/sessions/revoke-all",
            "/api/v1/projects/1/api-keys",
            "/api/v1/projects/1/invite-code",
        ],
    )
    async def test_api_key_cannot_mutate_outside_ingestion(self, path):
        await self.set_api_key_cache(API_KEY, project_id=1, account_id=1)

        response = await self.client.post(path, json={"name": "x"}, headers={"X-API-Key": API_KEY})

        assert response.status_code == 403

    async def test_api_key_still_ingests(self):
        await self.set_api_key_cache(API_KEY, project_id=1, account_id=1)

        response = await self.client.post(
            "/v1/logs",
            content=_otlp_log_body(),
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        )

        assert response.status_code == 200

    async def test_api_key_reads_only_its_own_project(self):
        await self.set_api_key_cache(API_KEY, project_id=1, account_id=1)

        own = await self.client.get(
            "/api/v1/logs?project_id=1&period=today", headers={"X-API-Key": API_KEY}
        )
        other = await self.client.get(
            "/api/v1/logs?project_id=2&period=today", headers={"X-API-Key": API_KEY}
        )

        assert own.status_code == 200
        assert other.status_code == 403


@pytest.mark.asyncio
class TestProjectScopedWrites(test_base.BaseGatewayTest):
    def _session(self) -> dict:
        return {"Authorization": f"Bearer {self.make_session_token(account_id=7)}"}

    def _not_a_member(self) -> None:
        self.get_mock_auth_stub().GetProjectRole = AsyncMock(
            return_value=auth_pb2.GetProjectRoleResponse(is_member=False, role="")
        )

    async def test_alert_rule_on_foreign_project_is_forbidden(self):
        self._not_a_member()
        stub = self.get_mock_auth_stub()
        stub.CreateAlertRule = AsyncMock()

        response = await self.client.post(
            "/api/v1/alerts/rules",
            json={
                "project_id": 99,
                "name": "r",
                "metric": "error_rate_all",
                "comparator": ">",
                "threshold": 1,
            },
            headers=self._session(),
        )

        assert response.status_code == 403
        stub.CreateAlertRule.assert_not_awaited()

    async def test_alert_rule_cannot_use_another_accounts_connector(self):
        stub = self.get_mock_auth_stub()
        stub.ListConnectors = AsyncMock(
            return_value=auth_pb2.ListConnectorsResponse(
                connectors=[auth_pb2.Connector(id=5, account_id=7, kind="in_app")]
            )
        )
        stub.CreateAlertRule = AsyncMock()

        response = await self.client.post(
            "/api/v1/alerts/rules",
            json={
                "project_id": 1,
                "name": "r",
                "metric": "error_rate_all",
                "comparator": ">",
                "threshold": 1,
                "connector_ids": [5],
                "escalate_connector_id": 6,
            },
            headers=self._session(),
        )

        assert response.status_code == 400
        assert "6" in response.json()["detail"]
        stub.CreateAlertRule.assert_not_awaited()

    async def test_maintenance_window_on_foreign_project_is_forbidden(self):
        self._not_a_member()
        stub = self.get_mock_auth_stub()
        stub.CreateMaintenanceWindow = AsyncMock()

        response = await self.client.post(
            "/api/v1/maintenance-windows",
            json={
                "project_id": 99,
                "name": "w",
                "starts_at": "2026-01-01T00:00:00+00:00",
                "ends_at": "2026-01-02T00:00:00+00:00",
            },
            headers=self._session(),
        )

        assert response.status_code == 403
        stub.CreateMaintenanceWindow.assert_not_awaited()

    async def test_health_summary_only_covers_own_projects(self):
        self.get_mock_auth_stub().get_projects_response = auth_pb2.GetProjectsResponse(
            projects=[auth_pb2.ProjectInfo(project_id=1)]
        )
        query_stub = self.get_mock_query_stub()
        query_stub.GetHealthSummary = AsyncMock(return_value=query_pb2.GetHealthSummaryResponse())

        response = await self.client.get(
            "/api/v1/dashboard/health-summary?project_ids=1&project_ids=2",
            headers=self._session(),
        )

        assert response.status_code == 200
        sent = query_stub.GetHealthSummary.await_args.args[0]
        assert list(sent.project_ids) == ["1"]


@pytest.mark.asyncio
class TestAttemptLimits(test_base.BaseGatewayTest):
    async def test_login_attempts_per_email_are_limited(self):
        body = {"email": "victim@example.com", "password": "WrongPass123"}
        statuses = [
            (await self.client.post("/api/v1/accounts/login", json=body)).status_code
            for _ in range(11)
        ]

        assert statuses[:10] == [200] * 10
        assert statuses[10] == 429

    async def test_totp_session_dies_after_five_codes(self):
        self.mock_redis.data["totp_session:tok"] = 1
        stub = self.get_mock_auth_stub()
        stub.VerifyTOTPLogin = AsyncMock(
            return_value=auth_pb2.VerifyTOTPLoginResponse(success=False, error_message="bad")
        )

        statuses = [
            (
                await self.client.post(
                    "/api/v1/accounts/2fa/login",
                    json={"totp_session_token": "tok", "code": "000000"},
                )
            ).status_code
            for _ in range(6)
        ]

        assert statuses[:5] == [401] * 5
        assert statuses[5] == 429
        assert "totp_session:tok" not in self.mock_redis.data


@pytest.mark.asyncio
class TestRequestBodyLimits(test_base.BaseGatewayTest):
    async def test_unauthenticated_gzip_body_is_rejected_before_inflating(self):
        with patch("gateway_service.middleware.gzip_request._inflate_gzip") as inflate:
            response = await self.client.post(
                "/v1/logs",
                content=gzip.compress(_otlp_log_body()),
                headers={"Content-Type": "application/json", "Content-Encoding": "gzip"},
            )

        assert response.status_code == 401
        inflate.assert_not_called()

    async def test_gzip_body_inflating_past_limit_is_rejected(self):
        await self.set_api_key_cache(API_KEY, project_id=1, account_id=1)

        with patch("gateway_service.config.Settings.MAX_REQUEST_BODY_BYTES", 1024):
            response = await self.client.post(
                "/v1/logs",
                content=gzip.compress(b" " * 4096),
                headers={
                    "X-API-Key": API_KEY,
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
            )

        assert response.status_code == 413

    async def test_declared_length_past_limit_is_rejected(self):
        await self.set_api_key_cache(API_KEY, project_id=1, account_id=1)

        with patch("gateway_service.config.Settings.MAX_REQUEST_BODY_BYTES", 16):
            response = await self.client.post(
                "/v1/logs",
                content=_otlp_log_body(),
                headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            )

        assert response.status_code == 413

    async def test_corrupt_gzip_is_a_client_error(self):
        await self.set_api_key_cache(API_KEY, project_id=1, account_id=1)

        response = await self.client.post(
            "/v1/logs",
            content=b"\x1f\x8b not really gzip",
            headers={
                "X-API-Key": API_KEY,
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
            },
        )

        assert response.status_code == 400


@pytest.mark.asyncio
class TestQuotaRefund(test_base.BaseGatewayTest):
    async def test_failed_forward_returns_the_reservation(self):
        await self.set_api_key_cache(API_KEY, project_id=1, account_id=1)
        self.mock_grpc_pool.get_stub("ingestion", None).IngestLogBatch = AsyncMock(
            side_effect=_UnavailableError()
        )

        response = await self.client.post(
            "/v1/logs",
            content=_otlp_log_body(),
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        )

        assert response.status_code == 500
        assert self.mock_redis.data.get("daily_usage:1:logs") == 0


def _resolves_to(*addresses: str):
    async def getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0)) for a in addresses]

    return getaddrinfo


@pytest.mark.asyncio
class TestConnectorTestFirePinning:
    async def test_post_dials_the_validated_address_with_original_host_and_sni(self):
        seen: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(204)

        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", _resolves_to("93.184.215.14")):
            async with httpx.AsyncClient(transport=httpx.MockTransport(record)) as http:
                response = await net_guard.post_to_public_host(
                    http, "https://hooks.example.com:8443/notify?x=1", json={"a": 1}
                )

        assert response.status_code == 204
        (request,) = seen
        assert request.url.host == "93.184.215.14"
        assert request.url.port == 8443
        assert request.url.path == "/notify"
        assert request.headers["Host"] == "hooks.example.com:8443"
        assert request.extensions["sni_hostname"] == "hooks.example.com"

    async def test_host_with_any_private_address_is_refused_before_connecting(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(204))
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", _resolves_to("93.184.215.14", "10.0.0.5")):
            async with httpx.AsyncClient(transport=transport) as http:
                with pytest.raises(net_guard.UnsafeWebhookURLError):
                    await net_guard.post_to_public_host(http, "https://hooks.example.com/x")
