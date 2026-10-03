import pytest

from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestDashboardPanelRoutes(BaseGatewayTest):
    async def _post_panel(self, **fields):
        token = self.make_session_token(account_id=1)
        body = {
            "name": "Panel",
            "index": 0,
            "project_id": "1",
            "period": "last7days",
            **fields,
        }
        return await self.client.post(
            "/api/v1/dashboard/panels", json=body, headers={"Authorization": f"Bearer {token}"}
        )

    async def _put_panel(self, panel_id: str, **fields):
        token = self.make_session_token(account_id=1)
        body = {
            "name": "Panel",
            "index": 0,
            "project_id": "1",
            "period": "last7days",
            **fields,
        }
        return await self.client.put(
            f"/api/v1/dashboard/panels/{panel_id}",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )

    async def test_metric_panel_forwards_the_chosen_metric(self):
        response = await self._post_panel(type="metric_series", metric_name="orders_processed")

        assert response.status_code == 201
        assert response.json()["metric_name"] == "orders_processed"
        forwarded = self.get_mock_auth_stub().last_create_dashboard_panel_request
        assert forwarded.metric_name == "orders_processed"

    async def test_metric_panel_without_a_metric_is_accepted(self):
        response = await self._post_panel(type="metric_series")

        assert response.status_code == 201
        assert response.json()["metric_name"] is None

    async def test_error_list_panel_forwards_the_client_error_choice(self):
        response = await self._post_panel(type="error_list", include_client_errors=False)

        assert response.status_code == 201
        assert response.json()["include_client_errors"] is False
        forwarded = self.get_mock_auth_stub().last_create_dashboard_panel_request
        assert forwarded.HasField("include_client_errors")
        assert forwarded.include_client_errors is False

    async def test_error_list_panel_leaves_the_choice_unset_when_omitted(self):
        response = await self._post_panel(type="error_list")

        assert response.status_code == 201
        assert response.json()["include_client_errors"] is None
        forwarded = self.get_mock_auth_stub().last_create_dashboard_panel_request
        assert not forwarded.HasField("include_client_errors")

    async def test_update_forwards_the_client_error_choice(self):
        response = await self._put_panel("panel-1", type="error_list", include_client_errors=True)

        assert response.status_code == 200
        assert response.json()["include_client_errors"] is True
        forwarded = self.get_mock_auth_stub().last_update_dashboard_panel_request
        assert forwarded.include_client_errors is True
