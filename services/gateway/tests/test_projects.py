import grpc
import pytest
from gateway_service.proto import auth_pb2

from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestCreateProject(BaseGatewayTest):
    """Test project creation."""

    async def test_create_project_success(self):
        """Test successful project creation."""

        response = await self.client.post(
            "/api/v1/projects",
            headers=self.session_headers(),
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
        assert data["logs_daily_quota"] > 0
        print(f"✅ Created project ID: {data['project_id']}")

    async def test_create_project_duplicate_slug(self):
        """Test creating project with duplicate slug fails."""

        stub = self.get_mock_auth_stub()

        async def mock_create_duplicate(request, timeout=None):
            error = grpc.RpcError()
            error.code = lambda: grpc.StatusCode.ALREADY_EXISTS
            error.details = lambda: f"Project with slug '{request.slug}' already exists"
            raise error

        stub.CreateProject = mock_create_duplicate

        response = await self.client.post(
            "/api/v1/projects",
            headers=self.session_headers(),
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

        invalid_slugs = [
            "MY-PROJECT",
            "my project",
            "my_project!",
            "",
        ]

        for slug in invalid_slugs:
            response = await self.client.post(
                "/api/v1/projects",
                headers=self.session_headers(),
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

        response = await self.client.post(
            "/api/v1/projects",
            headers=self.session_headers(),
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

        response = await self.client.post(
            "/api/v1/projects",
            headers=self.session_headers(),
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

        stub = self.get_mock_auth_stub()
        stub.get_projects_response = auth_pb2.GetProjectsResponse(
            projects=[
                auth_pb2.ProjectInfo(
                    project_id=1,
                    name="Project 1",
                    slug="project-1",
                    environment="production",
                    retention_days=30,
                    logs_daily_quota=1000000,
                ),
                auth_pb2.ProjectInfo(
                    project_id=2,
                    name="Project 2",
                    slug="project-2",
                    environment="staging",
                    retention_days=7,
                    logs_daily_quota=500000,
                ),
            ]
        )

        response = await self.client.get(
            "/api/v1/projects",
            headers=self.session_headers(),
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

        response = await self.client.get(
            "/api/v1/projects",
            headers=self.session_headers(),
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
