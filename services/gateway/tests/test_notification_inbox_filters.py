import pytest

from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestNotificationInboxFilters(BaseGatewayTest):
    async def _list(self, query: str):
        session_token = self.make_session_token(account_id=1)
        return await self.client.get(
            f"/api/v1/notifications{query}",
            headers={"Authorization": f"Bearer {session_token}"},
        )

    async def test_filters_are_forwarded_to_the_auth_service(self):
        response = await self._list(
            "?project_id=3&kind=alert_resolved"
            "&created_after=2026-10-01T00:00:00Z&created_before=2026-10-02T00:00:00Z"
        )

        assert response.status_code == 200
        request = self.get_mock_auth_stub().last_list_notifications_request
        assert request.user_id == 1
        assert request.project_id == 3
        assert request.kind == "alert_resolved"
        assert request.created_after == "2026-10-01T00:00:00+00:00"
        assert request.created_before == "2026-10-02T00:00:00+00:00"

    async def test_unset_filters_are_not_sent(self):
        response = await self._list("")

        assert response.status_code == 200
        request = self.get_mock_auth_stub().last_list_notifications_request
        assert not request.HasField("project_id")
        assert not request.HasField("kind")
        assert not request.HasField("created_after")
        assert not request.HasField("created_before")

    async def test_unknown_kind_is_rejected(self):
        response = await self._list("?kind=bogus")

        assert response.status_code == 422

    async def test_invalid_instant_is_rejected(self):
        response = await self._list("?created_after=yesterday")

        assert response.status_code == 422
