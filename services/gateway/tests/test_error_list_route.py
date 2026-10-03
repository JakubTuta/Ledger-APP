import pytest
from gateway_service.proto import auth_pb2

from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestErrorListRoute(BaseGatewayTest):
    async def _get(self, query: str):
        token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_projects_response = auth_pb2.GetProjectsResponse(
            projects=[
                auth_pb2.ProjectInfo(
                    project_id=1,
                    name="My Project",
                    slug="my-project",
                    environment="production",
                    retention_days=30,
                    logs_daily_quota=100000,
                    spans_daily_quota=300000,
                    metrics_daily_quota=100000,
                ),
            ]
        )
        return await self.client.get(
            f"/api/v1/errors/list?project_id=1&period=today{query}",
            headers={"Authorization": f"Bearer {token}"},
        )

    async def test_client_errors_are_included_by_default(self):
        response = await self._get("")

        assert response.status_code == 200
        forwarded = self.get_mock_query_stub().last_get_error_list_request
        assert forwarded.include_client_errors is True

    async def test_client_errors_can_be_excluded(self):
        response = await self._get("&include_client_errors=false")

        assert response.status_code == 200
        forwarded = self.get_mock_query_stub().last_get_error_list_request
        assert forwarded.HasField("include_client_errors")
        assert forwarded.include_client_errors is False
