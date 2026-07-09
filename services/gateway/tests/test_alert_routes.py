import pytest

import gateway_service.proto.auth_pb2 as auth_pb2

from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestAckAlertEvent(BaseGatewayTest):
    async def test_ack_success(self, setup_method):
        token = self.make_session_token(account_id=1)

        response = await self.client.post(
            "/api/v1/alerts/history/42/ack?project_id=1",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 42
        assert data["acked_by"] == 1
        assert data["acked_at"] is not None

    async def test_ack_requires_auth(self, setup_method):
        response = await self.client.post("/api/v1/alerts/history/42/ack?project_id=1")
        assert response.status_code == 401

    async def test_ack_not_found(self, setup_method):
        token = self.make_session_token(account_id=1)
        stub = self.get_mock_auth_stub()

        async def not_found(request, timeout=None):
            return auth_pb2.AckAlertEventResponse(
                success=False, error_message="Alert event not found"
            )

        stub.AckAlertEvent = not_found

        response = await self.client.post(
            "/api/v1/alerts/history/999/ack?project_id=1",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


@pytest.mark.asyncio
class TestSnoozeAlertEvent(BaseGatewayTest):
    async def test_snooze_success(self, setup_method):
        token = self.make_session_token(account_id=1)

        response = await self.client.post(
            "/api/v1/alerts/history/42/snooze?project_id=1",
            headers={"Authorization": f"Bearer {token}"},
            json={"minutes": 60},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 42
        assert data["snoozed_until"] is not None

    async def test_snooze_rejects_zero_minutes(self, setup_method):
        token = self.make_session_token(account_id=1)

        response = await self.client.post(
            "/api/v1/alerts/history/42/snooze?project_id=1",
            headers={"Authorization": f"Bearer {token}"},
            json={"minutes": 0},
        )

        assert response.status_code == 422

    async def test_snooze_rejects_over_7_days(self, setup_method):
        token = self.make_session_token(account_id=1)

        response = await self.client.post(
            "/api/v1/alerts/history/42/snooze?project_id=1",
            headers={"Authorization": f"Bearer {token}"},
            json={"minutes": 7 * 24 * 60 + 1},
        )

        assert response.status_code == 422

    async def test_snooze_requires_auth(self, setup_method):
        response = await self.client.post(
            "/api/v1/alerts/history/42/snooze?project_id=1",
            json={"minutes": 60},
        )
        assert response.status_code == 401
