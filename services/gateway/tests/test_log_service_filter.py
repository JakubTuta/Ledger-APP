import pytest
from gateway_service.proto import auth_pb2, query_pb2

from .test_base import BaseGatewayTest


def _member_project() -> auth_pb2.GetProjectsResponse:
    return auth_pb2.GetProjectsResponse(
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


@pytest.mark.asyncio
class TestServiceFilterParam(BaseGatewayTest):
    async def _get(self, path: str):
        session_token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_projects_response = _member_project()
        return await self.client.get(path, headers={"Authorization": f"Bearer {session_token}"})

    async def test_logs_forwards_the_service_filter(self):
        response = await self._get("/api/v1/logs?project_id=1&period=today&service=api")

        assert response.status_code == 200
        assert self.get_mock_query_stub().last_query_logs_request.service == "api"

    async def test_logs_leaves_the_service_filter_unset_by_default(self):
        response = await self._get("/api/v1/logs?project_id=1&period=today")

        assert response.status_code == 200
        assert not self.get_mock_query_stub().last_query_logs_request.HasField("service")

    async def test_facets_forwards_the_service_filter(self):
        response = await self._get("/api/v1/logs/facets?project_id=1&period=today&service=api")

        assert response.status_code == 200
        assert self.get_mock_query_stub().last_get_log_facets_request.service == "api"

    async def test_facets_leaves_the_service_filter_unset_by_default(self):
        response = await self._get("/api/v1/logs/facets?project_id=1&period=today")

        assert response.status_code == 200
        assert not self.get_mock_query_stub().last_get_log_facets_request.HasField("service")


@pytest.mark.asyncio
class TestListLogServices(BaseGatewayTest):
    async def _get(self, path: str):
        session_token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_projects_response = _member_project()
        return await self.client.get(path, headers={"Authorization": f"Bearer {session_token}"})

    async def test_returns_service_names(self):
        self.get_mock_query_stub().list_log_services_response = query_pb2.ListLogServicesResponse(
            project_id=1, services=["api", "worker"]
        )

        response = await self._get("/api/v1/logs/services?project_id=1&period=last7days")

        assert response.status_code == 200
        assert response.json() == {"project_id": 1, "services": ["api", "worker"]}

    async def test_forwards_window_and_limit(self):
        response = await self._get("/api/v1/logs/services?project_id=1&period=today&limit=7")

        assert response.status_code == 200
        request = self.get_mock_query_stub().last_list_log_services_request
        assert request.project_id == 1
        assert request.limit == 7
        assert request.start_time and request.end_time

    async def test_requires_a_time_window(self):
        response = await self._get("/api/v1/logs/services?project_id=1")

        assert response.status_code == 400

    async def test_rejects_an_oversized_limit(self):
        response = await self._get("/api/v1/logs/services?project_id=1&period=today&limit=101")

        assert response.status_code == 422

    async def test_rejects_non_member(self):
        session_token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_project_role_response = auth_pb2.GetProjectRoleResponse(
            is_member=False, role=""
        )

        response = await self.client.get(
            "/api/v1/logs/services?project_id=1&period=today",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 403
