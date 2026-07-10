import pytest
from gateway_service.proto import auth_pb2, query_pb2

from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestGetProjectUsageStats(BaseGatewayTest):
    async def test_usage_stats_success(self):
        session_token = self.make_session_token(account_id=1)

        auth_stub = self.get_mock_auth_stub()
        auth_stub.get_projects_response = auth_pb2.GetProjectsResponse(
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

        query_stub = self.get_mock_query_stub()
        query_stub.get_usage_stats_response = query_pb2.GetUsageStatsResponse(
            project_id=1,
            usage=[
                query_pb2.UsageStatsData(
                    date="2026-07-10",
                    log_count=1234,
                    span_count=4567,
                    metric_point_count=89,
                    logs_daily_quota=100000,
                    spans_daily_quota=300000,
                    metrics_daily_quota=100000,
                    logs_quota_used_percent=1.23,
                    spans_quota_used_percent=1.52,
                    metrics_quota_used_percent=0.09,
                )
            ],
        )

        response = await self.client.get(
            "/api/v1/projects/1/usage-stats",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == 1
        assert len(data["usage"]) == 1
        entry = data["usage"][0]
        assert entry["date"] == "2026-07-10"
        assert entry["log_count"] == 1234
        assert entry["span_count"] == 4567
        assert entry["metric_point_count"] == 89
        assert entry["logs_daily_quota"] == 100000
        assert entry["spans_daily_quota"] == 300000
        assert entry["metrics_daily_quota"] == 100000

    async def test_usage_stats_rejects_non_member(self):
        session_token = self.make_session_token(account_id=1)

        auth_stub = self.get_mock_auth_stub()
        auth_stub.get_projects_response = auth_pb2.GetProjectsResponse(projects=[])

        response = await self.client.get(
            "/api/v1/projects/1/usage-stats",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 403

    async def test_usage_stats_rejects_invalid_date(self):
        session_token = self.make_session_token(account_id=1)

        auth_stub = self.get_mock_auth_stub()
        auth_stub.get_projects_response = auth_pb2.GetProjectsResponse(
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

        response = await self.client.get(
            "/api/v1/projects/1/usage-stats?start_date=not-a-date",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 400

    async def test_usage_stats_without_auth(self):
        response = await self.client.get("/api/v1/projects/1/usage-stats")

        assert response.status_code == 401
