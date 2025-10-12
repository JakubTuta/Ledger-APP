import pytest
from auth_service.proto import auth_pb2

from .test_base import BaseGrpcTest


@pytest.mark.asyncio
class TestProjectEndpoints(BaseGrpcTest):
    """Test project operations."""

    async def test_create_project_success(self):
        """Test creating a project."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="project@example.com", password="password123", plan="pro"
            )
        )

        request = auth_pb2.CreateProjectRequest(
            account_id=account.account_id,
            name="My Project",
            slug="my-project",
            environment="production",
        )
        response = await self.stub.CreateProject(request)

        assert response.project_id > 0
        assert response.name == "My Project"
        assert response.slug == "my-project"
        assert response.environment == "production"
        assert response.retention_days == 30
        assert response.daily_quota == 1_000_000
        print(f"✅ Created project ID: {response.project_id}")

    async def test_create_project_duplicate_slug(self):
        """Test creating project with duplicate slug fails."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="user@example.com", password="password123", plan="free"
            )
        )

        await self.stub.CreateProject(
            auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name="Project 1",
                slug="duplicate-slug",
                environment="production",
            )
        )

        request = auth_pb2.CreateProjectRequest(
            account_id=account.account_id,
            name="Project 2",
            slug="duplicate-slug",
            environment="staging",
        )

        try:
            await self.stub.CreateProject(request)
            assert False, "Should have raised error"
        except Exception as e:
            assert "already exists" in str(e).lower()
            print(f"✅ Correctly rejected duplicate slug")

    async def test_get_projects(self):
        """Test retrieving projects for an account."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="multi@example.com", password="password123", plan="enterprise"
            )
        )

        for i in range(3):
            await self.stub.CreateProject(
                auth_pb2.CreateProjectRequest(
                    account_id=account.account_id,
                    name=f"Project {i}",
                    slug=f"project-{i}",
                    environment="production",
                )
            )

        request = auth_pb2.GetProjectsRequest(account_id=account.account_id)
        response = await self.stub.GetProjects(request)

        assert len(response.projects) == 3
        for project in response.projects:
            print(f"✅ Found project: {project.name}")


@pytest.mark.asyncio
class TestProjectValidation(BaseGrpcTest):
    """Test project input validation."""

    async def test_create_project_empty_name(self):
        """Test creating project with empty name."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="empty@example.com", password="password123", plan="free"
            )
        )

        request = auth_pb2.CreateProjectRequest(
            account_id=account.account_id,
            name="",
            slug="empty-name",
            environment="production",
        )

        try:
            await self.stub.CreateProject(request)
            print("⚠️  Empty name accepted - consider adding validation")
        except Exception as e:
            print(f"✅ Empty name rejected: {e}")

    async def test_create_project_special_characters_in_slug(self):
        """Test slug validation with special characters."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="slug@example.com", password="password123", plan="free"
            )
        )

        invalid_slugs = [
            "my project",
            "my_project!",
            "MY-PROJECT",
            "project@123",
            "project#tag",
        ]

        for slug in invalid_slugs:
            request = auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name="Test Project",
                slug=slug,
                environment="production",
            )

            try:
                await self.stub.CreateProject(request)
                print(f"⚠️  Invalid slug accepted: {slug}")
            except Exception:
                print(f"✅ Invalid slug rejected: {slug}")

    async def test_create_project_very_long_name(self):
        """Test project with very long name."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="longname@example.com", password="password123", plan="free"
            )
        )

        long_name = "A" * 300
        request = auth_pb2.CreateProjectRequest(
            account_id=account.account_id,
            name=long_name,
            slug="long-name-project",
            environment="production",
        )

        try:
            response = await self.stub.CreateProject(request)
            print(f"✅ Long name accepted ({len(long_name)} chars)")
        except Exception as e:
            print(f"⚠️  Long name rejected: {e}")

    async def test_create_project_invalid_environment(self):
        """Test creating project with invalid environment."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="env@example.com", password="password123", plan="free"
            )
        )

        invalid_environments = ["testing", "local", "invalid", "PRODUCTION"]

        for env in invalid_environments:
            request = auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name=f"Env Test {env}",
                slug=f"env-{env.lower()}",
                environment=env,
            )

            try:
                response = await self.stub.CreateProject(request)
                print(f"⚠️  Invalid environment accepted: {env}")
            except Exception:
                print(f"✅ Invalid environment rejected: {env}")

    async def test_create_project_different_environments(self):
        """Test creating projects with different valid environments."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="validenv@example.com", password="password123", plan="enterprise"
            )
        )

        valid_environments = ["production", "staging", "dev"]

        for env in valid_environments:
            request = auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name=f"Project {env.title()}",
                slug=f"project-{env}",
                environment=env,
            )

            response = await self.stub.CreateProject(request)
            assert response.environment == env
            print(f"✅ Created project with environment: {env}")


@pytest.mark.asyncio
class TestProjectBusinessLogic(BaseGrpcTest):
    """Test project business logic."""

    async def test_create_multiple_projects_same_account(self):
        """Test creating multiple projects for same account."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="multiple@example.com", password="password123", plan="enterprise"
            )
        )

        environments = ["production", "staging", "dev"]
        project_ids = []

        for env in environments:
            response = await self.stub.CreateProject(
                auth_pb2.CreateProjectRequest(
                    account_id=account.account_id,
                    name=f"App {env.title()}",
                    slug=f"app-{env}",
                    environment=env,
                )
            )
            project_ids.append(response.project_id)

        assert len(project_ids) == len(set(project_ids))
        print(f"✅ Created {len(project_ids)} projects with unique IDs")

    async def test_get_projects_empty(self):
        """Test getting projects for account with no projects."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="noprojects@example.com", password="password123", plan="free"
            )
        )

        request = auth_pb2.GetProjectsRequest(account_id=account.account_id)
        response = await self.stub.GetProjects(request)

        assert len(response.projects) == 0
        print("✅ Empty project list returned correctly")

    async def test_get_projects_nonexistent_account(self):
        """Test getting projects for non-existent account."""
        request = auth_pb2.GetProjectsRequest(account_id=99999)
        response = await self.stub.GetProjects(request)

        assert len(response.projects) == 0
        print("✅ Non-existent account returns empty list")

    async def test_create_project_nonexistent_account(self):
        """Test creating project for non-existent account."""
        request = auth_pb2.CreateProjectRequest(
            account_id=99999,
            name="Orphan Project",
            slug="orphan-project",
            environment="production",
        )

        try:
            response = await self.stub.CreateProject(request)
            print(
                "⚠️  Project created for non-existent account - consider adding FK validation"
            )
        except Exception as e:
            print(f"✅ Project creation for non-existent account rejected: {e}")

    async def test_projects_isolated_between_accounts(self):
        """Test that projects are isolated between accounts."""
        account1 = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="user1@example.com", password="password123", plan="free"
            )
        )

        account2 = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="user2@example.com", password="password123", plan="free"
            )
        )

        await self.stub.CreateProject(
            auth_pb2.CreateProjectRequest(
                account_id=account1.account_id,
                name="Account 1 Project",
                slug="account1-project",
                environment="production",
            )
        )

        await self.stub.CreateProject(
            auth_pb2.CreateProjectRequest(
                account_id=account2.account_id,
                name="Account 2 Project",
                slug="account2-project",
                environment="production",
            )
        )

        response1 = await self.stub.GetProjects(
            auth_pb2.GetProjectsRequest(account_id=account1.account_id)
        )

        response2 = await self.stub.GetProjects(
            auth_pb2.GetProjectsRequest(account_id=account2.account_id)
        )

        assert len(response1.projects) == 1
        assert len(response2.projects) == 1
        assert response1.projects[0].slug == "account1-project"
        assert response2.projects[0].slug == "account2-project"
        print("✅ Projects correctly isolated between accounts")


@pytest.mark.asyncio
class TestProjectSlugValidation(BaseGrpcTest):
    """Test slug validation rules."""

    async def test_slug_lowercase_only(self):
        """Test that slugs should be lowercase."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="slug@example.com", password="password123", plan="free"
            )
        )

        request = auth_pb2.CreateProjectRequest(
            account_id=account.account_id,
            name="Test Project",
            slug="UPPERCASE-SLUG",
            environment="production",
        )

        try:
            response = await self.stub.CreateProject(request)
            print("⚠️  Uppercase slug accepted - consider enforcing lowercase")
        except Exception:
            print("✅ Uppercase slug rejected")

    async def test_slug_with_numbers(self):
        """Test slugs with numbers."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="numbers@example.com", password="password123", plan="free"
            )
        )

        request = auth_pb2.CreateProjectRequest(
            account_id=account.account_id,
            name="Project 123",
            slug="project-123",
            environment="production",
        )

        response = await self.stub.CreateProject(request)
        assert response.project_id > 0
        print("✅ Slug with numbers accepted")

    async def test_slug_only_hyphens(self):
        """Test slug with only valid characters."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="hyphens@example.com", password="password123", plan="free"
            )
        )

        valid_slugs = [
            "my-project",
            "my-super-long-project-name",
            "project123",
            "123project",
        ]

        for i, slug in enumerate(valid_slugs):
            request = auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name=f"Project {i}",
                slug=slug,
                environment="production",
            )

            response = await self.stub.CreateProject(request)
            assert response.project_id > 0
            print(f"✅ Valid slug accepted: {slug}")


@pytest.mark.asyncio
class TestProjectConcurrency(BaseGrpcTest):
    """Test concurrent project operations."""

    async def test_concurrent_project_creation_different_slugs(self):
        """Test creating multiple projects concurrently with different slugs."""
        import asyncio

        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="concurrent@example.com",
                password="password123",
                plan="enterprise",
            )
        )

        async def create_project(index):
            request = auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name=f"Project {index}",
                slug=f"project-{index}",
                environment="production",
            )
            return await self.stub.CreateProject(request)

        tasks = [create_project(i) for i in range(5)]
        responses = await asyncio.gather(*tasks)

        project_ids = [r.project_id for r in responses]
        assert len(project_ids) == len(set(project_ids))
        print(f"✅ Created {len(responses)} concurrent projects")

    async def test_concurrent_project_creation_same_slug(self):
        """Test race condition with same slug."""
        import asyncio

        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="race@example.com", password="password123", plan="free"
            )
        )

        async def create_project():
            request = auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name="Race Project",
                slug="race-project",
                environment="production",
            )
            return await self.stub.CreateProject(request)

        tasks = [create_project() for _ in range(3)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, Exception)]

        assert len(successes) == 1, "Only one should succeed"
        assert len(failures) == 2, "Two should fail"
        print(f"✅ Slug race condition handled: 1 success, 2 failures")

    async def test_concurrent_get_projects(self):
        """Test getting projects concurrently."""
        import asyncio

        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="concurrentget@example.com", password="password123", plan="pro"
            )
        )

        for i in range(3):
            await self.stub.CreateProject(
                auth_pb2.CreateProjectRequest(
                    account_id=account.account_id,
                    name=f"Project {i}",
                    slug=f"concurrentget-{i}",
                    environment="production",
                )
            )

        async def get_projects():
            request = auth_pb2.GetProjectsRequest(account_id=account.account_id)
            return await self.stub.GetProjects(request)

        tasks = [get_projects() for _ in range(5)]
        responses = await asyncio.gather(*tasks)

        for response in responses:
            assert len(response.projects) == 3

        print(f"✅ {len(responses)} concurrent GetProjects calls succeeded")


@pytest.mark.asyncio
class TestProjectEdgeCases(BaseGrpcTest):
    """Test additional edge cases."""

    async def test_create_project_empty_slug(self):
        """Test creating project with empty slug."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="emptyslug@example.com", password="password123", plan="free"
            )
        )

        request = auth_pb2.CreateProjectRequest(
            account_id=account.account_id,
            name="Empty Slug Project",
            slug="",
            environment="production",
        )

        try:
            await self.stub.CreateProject(request)
            print("⚠️  Empty slug accepted - consider adding validation")
        except Exception as e:
            print(f"✅ Empty slug rejected: {e}")

    async def test_create_project_very_long_slug(self):
        """Test creating project with very long slug."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="longslug@example.com", password="password123", plan="free"
            )
        )

        long_slug = "a" * 300
        request = auth_pb2.CreateProjectRequest(
            account_id=account.account_id,
            name="Long Slug Project",
            slug=long_slug,
            environment="production",
        )

        try:
            response = await self.stub.CreateProject(request)
            print(f"✅ Long slug accepted ({len(long_slug)} chars)")
        except Exception as e:
            print(f"⚠️  Long slug rejected: {e}")

    async def test_create_project_slug_with_unicode(self):
        """Test creating project with unicode characters in slug."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="unicode@example.com", password="password123", plan="free"
            )
        )

        unicode_slugs = [
            "project-ñ",
            "project-中文",
            "project-emoji-🚀",
        ]

        for slug in unicode_slugs:
            request = auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name="Unicode Project",
                slug=slug,
                environment="production",
            )

            try:
                await self.stub.CreateProject(request)
                print(f"⚠️  Unicode slug accepted: {slug}")
            except Exception:
                print(f"✅ Unicode slug rejected: {slug}")
