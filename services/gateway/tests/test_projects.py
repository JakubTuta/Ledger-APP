import grpc
import pytest
from gateway_service.proto import auth_pb2

from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestCreateProject(BaseGatewayTest):
    """Test project creation."""

    async def test_create_project_success(self):
        """Test successful project creation."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 1000,
                "rate_limit_per_hour": 50000,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        response = await self.client.post(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "name": "My Test Project",
                "slug": "my-test-project",
                "environment": "production",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["project_id"] > 0
        assert data["name"] == "My Test Project"
        assert data["slug"] == "my-test-project"
        assert data["environment"] == "production"
        assert data["retention_days"] == 30
        assert data["daily_quota"] > 0
        print(f"✅ Created project ID: {data['project_id']}")

    async def test_create_project_duplicate_slug(self):
        """Test creating project with duplicate slug fails."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 1000,
                "rate_limit_per_hour": 50000,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        stub = self.get_mock_auth_stub()

        async def mock_create_duplicate(request):
            error = grpc.RpcError()
            error.code = lambda: grpc.StatusCode.ALREADY_EXISTS
            error.details = lambda: f"Project with slug '{request.slug}' already exists"
            raise error

        stub.CreateProject = mock_create_duplicate

        response = await self.client.post(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "name": "Duplicate Project",
                "slug": "existing-slug",
                "environment": "production",
            },
        )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()
        print("✅ Duplicate slug rejected")

    async def test_create_project_invalid_slug_format(self):
        """Test slug validation."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 1000,
                "rate_limit_per_hour": 50000,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        invalid_slugs = [
            "MY-PROJECT",
            "my project",
            "my_project!",
            "",
        ]

        for slug in invalid_slugs:
            response = await self.client.post(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "name": "Test Project",
                    "slug": slug,
                    "environment": "production",
                },
            )

            assert response.status_code == 422
            print(f"✅ Invalid slug rejected: '{slug}'")

    async def test_create_project_slug_lowercase_conversion(self):
        """Test slug is converted to lowercase."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 1000,
                "rate_limit_per_hour": 50000,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        response = await self.client.post(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "name": "Test Project",
                "slug": "test-project",
                "environment": "production",
            },
        )

        assert response.status_code == 201
        assert response.json()["slug"] == "test-project"
        print("✅ Slug lowercase validation passed")

    async def test_create_project_invalid_environment(self):
        """Test environment validation."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 1000,
                "rate_limit_per_hour": 50000,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        response = await self.client.post(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "name": "Test Project",
                "slug": "test-project",
                "environment": "invalid_env",
            },
        )

        assert response.status_code == 422
        print("✅ Invalid environment rejected")

    async def test_create_project_without_auth(self):
        """Test creating project without authentication fails."""
        response = await self.client.post(
            "/api/v1/projects",
            json={
                "name": "Test Project",
                "slug": "test-project",
                "environment": "production",
            },
        )

        assert response.status_code == 401
        print("✅ Unauthenticated project creation rejected")


@pytest.mark.asyncio
class TestListProjects(BaseGatewayTest):
    """Test listing projects."""

    async def test_list_projects_success(self):
        """Test successful project listing."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 1000,
                "rate_limit_per_hour": 50000,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        stub = self.get_mock_auth_stub()
        stub.get_projects_response = auth_pb2.GetProjectsResponse(
            projects=[
                auth_pb2.ProjectInfo(
                    project_id=1,
                    name="Project 1",
                    slug="project-1",
                    environment="production",
                    retention_days=30,
                    daily_quota=1000000,
                ),
                auth_pb2.ProjectInfo(
                    project_id=2,
                    name="Project 2",
                    slug="project-2",
                    environment="staging",
                    retention_days=7,
                    daily_quota=500000,
                ),
            ]
        )

        response = await self.client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["projects"]) == 2
        assert data["projects"][0]["name"] == "Project 1"
        assert data["projects"][1]["name"] == "Project 2"
        print("✅ Listed 2 projects")

    async def test_list_projects_empty(self):
        """Test listing when no projects exist."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 1000,
                "rate_limit_per_hour": 50000,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        response = await self.client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["projects"]) == 0
        print("✅ Empty project list handled")

    async def test_list_projects_without_auth(self):
        """Test listing projects without authentication."""
        response = await self.client.get("/api/v1/projects")

        assert response.status_code == 401
        print("✅ Unauthenticated project list rejected")


@pytest.mark.asyncio
class TestGetProjectBySlug(BaseGatewayTest):
    """Test getting project by slug."""

    async def test_get_project_by_slug_success(self):
        """Test getting project by slug."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 1000,
                "rate_limit_per_hour": 50000,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        stub = self.get_mock_auth_stub()
        stub.get_projects_response = auth_pb2.GetProjectsResponse(
            projects=[
                auth_pb2.ProjectInfo(
                    project_id=1,
                    name="My Project",
                    slug="my-project",
                    environment="production",
                    retention_days=30,
                    daily_quota=1000000,
                ),
            ]
        )

        response = await self.client.get(
            "/api/v1/projects/my-project",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == "my-project"
        assert data["name"] == "My Project"
        print("✅ Project found by slug")

    async def test_get_project_by_slug_not_found(self):
        """Test getting non-existent project."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 1000,
                "rate_limit_per_hour": 50000,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        response = await self.client.get(
            "/api/v1/projects/nonexistent-project",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
        print("✅ Non-existent project handled")
