import pytest
from auth_service.proto import auth_pb2

from .test_base import BaseGrpcTest


@pytest.mark.asyncio
class TestCompleteUserJourney(BaseGrpcTest):
    """Test complete user journey from registration to API key usage."""

    async def test_complete_onboarding_flow(self):
        """
        Complete flow:
        1. Register account
        2. Login
        3. Get account info
        4. Create project
        5. Create API key
        6. Validate API key
        """
        register_response = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="journey@example.com", password="SecurePassword123!", plan="pro"
            )
        )
        assert register_response.account_id > 0
        account_id = register_response.account_id
        print(f"✅ Step 1: Registered account {account_id}")

        login_response = await self.stub.Login(
            auth_pb2.LoginRequest(
                email="journey@example.com", password="SecurePassword123!"
            )
        )
        assert login_response.account_id == account_id
        print(f"✅ Step 2: Logged in successfully")

        get_account_response = await self.stub.GetAccount(
            auth_pb2.GetAccountRequest(account_id=account_id)
        )
        assert get_account_response.account_id == account_id
        assert get_account_response.email == "journey@example.com"
        print(f"✅ Step 3: Retrieved account info")

        project_response = await self.stub.CreateProject(
            auth_pb2.CreateProjectRequest(
                account_id=account_id,
                name="Production App",
                slug="production-app",
                environment="production",
            )
        )
        assert project_response.project_id > 0
        project_id = project_response.project_id
        print(f"✅ Step 4: Created project {project_id}")

        api_key_response = await self.stub.CreateApiKey(
            auth_pb2.CreateApiKeyRequest(project_id=project_id, name="Production Key")
        )
        assert api_key_response.key_id > 0
        full_key = api_key_response.full_key
        print(f"✅ Step 5: Created API key {full_key[:30]}...")

        validate_response = await self.stub.ValidateApiKey(
            auth_pb2.ValidateApiKeyRequest(api_key=full_key)
        )
        assert validate_response.valid is True
        assert validate_response.project_id == project_id
        print(f"✅ Step 6: API key validated")

        print(f"\n🎉 Complete onboarding flow succeeded!")

    async def test_multi_environment_setup(self):
        """
        Test setting up multiple environments:
        - Production, Staging, Development projects
        - API keys for each environment
        """
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="multienv@example.com", password="password123", plan="enterprise"
            )
        )

        environments = ["production", "staging", "dev"]
        env_data = {}

        for env in environments:
            project = await self.stub.CreateProject(
                auth_pb2.CreateProjectRequest(
                    account_id=account.account_id,
                    name=f"My App {env.title()}",
                    slug=f"my-app-{env}",
                    environment=env,
                )
            )

            api_key = await self.stub.CreateApiKey(
                auth_pb2.CreateApiKeyRequest(
                    project_id=project.project_id, name=f"{env.title()} Key"
                )
            )

            env_data[env] = {
                "project_id": project.project_id,
                "api_key": api_key.full_key,
            }

            print(f"✅ Setup {env} environment: project={project.project_id}")

        projects = await self.stub.GetProjects(
            auth_pb2.GetProjectsRequest(account_id=account.account_id)
        )
        assert len(projects.projects) == 3

        for env, data in env_data.items():
            response = await self.stub.ValidateApiKey(
                auth_pb2.ValidateApiKeyRequest(api_key=data["api_key"])
            )
            assert response.valid is True
            assert response.project_id == data["project_id"]

        print(f"✅ All {len(environments)} environments configured correctly")


@pytest.mark.asyncio
class TestTeamCollaboration(BaseGrpcTest):
    """Test scenarios involving multiple team members."""

    async def test_multiple_users_separate_projects(self):
        """Test multiple users with their own isolated projects."""
        users = []

        for i in range(3):
            account = await self.stub.Register(
                auth_pb2.RegisterRequest(
                    email=f"team{i}@example.com", password="password123", plan="pro"
                )
            )

            project = await self.stub.CreateProject(
                auth_pb2.CreateProjectRequest(
                    account_id=account.account_id,
                    name=f"User {i} Project",
                    slug=f"user{i}-project",
                    environment="production",
                )
            )

            users.append(
                {"account_id": account.account_id, "project_id": project.project_id}
            )

        for i, user in enumerate(users):
            projects = await self.stub.GetProjects(
                auth_pb2.GetProjectsRequest(account_id=user["account_id"])
            )

            assert len(projects.projects) == 1
            assert projects.projects[0].project_id == user["project_id"]

        print(f"✅ {len(users)} users have isolated projects")

    async def test_single_user_multiple_teams(self):
        """Test single user managing multiple team projects."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="manager@example.com", password="password123", plan="enterprise"
            )
        )

        teams = ["frontend", "backend", "mobile", "analytics"]
        team_projects = []

        for team in teams:
            project = await self.stub.CreateProject(
                auth_pb2.CreateProjectRequest(
                    account_id=account.account_id,
                    name=f"{team.title()} Team",
                    slug=f"{team}-team",
                    environment="production",
                )
            )
            team_projects.append(project)
            print(f"✅ Created project for {team} team: {project.project_id}")

        projects = await self.stub.GetProjects(
            auth_pb2.GetProjectsRequest(account_id=account.account_id)
        )

        assert len(projects.projects) == len(teams)
        print(f"✅ Manager can access all {len(teams)} team projects")


@pytest.mark.asyncio
class TestApiKeyLifecycle(BaseGrpcTest):
    """Test complete lifecycle of API keys."""

    async def test_api_key_rotation(self):
        """Test rotating API keys (create new, revoke old)."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="rotation@example.com", password="password123", plan="free"
            )
        )

        project = await self.stub.CreateProject(
            auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name="Rotation Test",
                slug="rotation-test",
                environment="production",
            )
        )

        key1 = await self.stub.CreateApiKey(
            auth_pb2.CreateApiKeyRequest(project_id=project.project_id, name="Key v1")
        )
        print(f"✅ Created key v1: {key1.full_key[:30]}...")

        response = await self.stub.ValidateApiKey(
            auth_pb2.ValidateApiKeyRequest(api_key=key1.full_key)
        )
        assert response.valid is True

        key2 = await self.stub.CreateApiKey(
            auth_pb2.CreateApiKeyRequest(project_id=project.project_id, name="Key v2")
        )
        print(f"✅ Created key v2: {key2.full_key[:30]}...")

        response1 = await self.stub.ValidateApiKey(
            auth_pb2.ValidateApiKeyRequest(api_key=key1.full_key)
        )
        response2 = await self.stub.ValidateApiKey(
            auth_pb2.ValidateApiKeyRequest(api_key=key2.full_key)
        )
        assert response1.valid is True
        assert response2.valid is True

        await self.stub.RevokeApiKey(auth_pb2.RevokeApiKeyRequest(key_id=key1.key_id))
        print(f"✅ Revoked key v1")

        response1 = await self.stub.ValidateApiKey(
            auth_pb2.ValidateApiKeyRequest(api_key=key1.full_key)
        )
        response2 = await self.stub.ValidateApiKey(
            auth_pb2.ValidateApiKeyRequest(api_key=key2.full_key)
        )
        assert response1.valid is False
        assert response2.valid is True

        print(f"✅ Key rotation completed successfully")

    async def test_emergency_key_revocation(self):
        """Test revoking all keys in emergency scenario."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="emergency@example.com", password="password123", plan="pro"
            )
        )

        project = await self.stub.CreateProject(
            auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name="Emergency Test",
                slug="emergency-test",
                environment="production",
            )
        )

        keys = []
        for i in range(3):
            key = await self.stub.CreateApiKey(
                auth_pb2.CreateApiKeyRequest(
                    project_id=project.project_id, name=f"Key {i}"
                )
            )
            keys.append(key)

        for key in keys:
            response = await self.stub.ValidateApiKey(
                auth_pb2.ValidateApiKeyRequest(api_key=key.full_key)
            )
            assert response.valid is True

        print(f"✅ Created {len(keys)} active keys")

        for key in keys:
            await self.stub.RevokeApiKey(
                auth_pb2.RevokeApiKeyRequest(key_id=key.key_id)
            )

        print(f"✅ Revoked all {len(keys)} keys")

        for key in keys:
            response = await self.stub.ValidateApiKey(
                auth_pb2.ValidateApiKeyRequest(api_key=key.full_key)
            )
            assert response.valid is False

        print(f"✅ Emergency revocation completed")


@pytest.mark.asyncio
class TestErrorRecovery(BaseGrpcTest):
    """Test error recovery and resilience."""

    async def test_recover_from_failed_login(self):
        """Test recovering from failed login attempts."""
        await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="recovery@example.com", password="correct_password", plan="free"
            )
        )

        for i in range(3):
            try:
                await self.stub.Login(
                    auth_pb2.LoginRequest(
                        email="recovery@example.com", password=f"wrong{i}"
                    )
                )
            except:
                pass

        response = await self.stub.Login(
            auth_pb2.LoginRequest(
                email="recovery@example.com", password="correct_password"
            )
        )

        assert response.account_id > 0
        print("✅ Successfully logged in after failed attempts")

    async def test_continue_after_invalid_operations(self):
        """Test that invalid operations don't break subsequent valid ones."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="continue@example.com", password="password123", plan="free"
            )
        )

        try:
            await self.stub.CreateProject(
                auth_pb2.CreateProjectRequest(
                    account_id=99999,
                    name="Invalid",
                    slug="invalid",
                    environment="production",
                )
            )
        except:
            pass

        try:
            await self.stub.CreateApiKey(
                auth_pb2.CreateApiKeyRequest(project_id=99999, name="Invalid")
            )
        except:
            pass

        project = await self.stub.CreateProject(
            auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name="Valid Project",
                slug="valid-project",
                environment="production",
            )
        )

        assert project.project_id > 0
        print("✅ Valid operations work after invalid attempts")


@pytest.mark.asyncio
class TestDataConsistency(BaseGrpcTest):
    """Test data consistency across operations."""

    async def test_account_data_consistency(self):
        """Test that account data remains consistent across operations."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="consistent@example.com", password="password123", plan="pro"
            )
        )

        for i in range(5):
            response = await self.stub.GetAccount(
                auth_pb2.GetAccountRequest(account_id=account.account_id)
            )

            assert response.account_id == account.account_id
            assert response.email == account.email
            assert response.plan == account.plan

        print("✅ Account data consistent across 5 retrievals")

    async def test_project_count_consistency(self):
        """Test that project count is consistent."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="projcount@example.com", password="password123", plan="enterprise"
            )
        )

        for i in range(5):
            await self.stub.CreateProject(
                auth_pb2.CreateProjectRequest(
                    account_id=account.account_id,
                    name=f"Project {i}",
                    slug=f"project-{i}",
                    environment="production",
                )
            )

        for i in range(3):
            response = await self.stub.GetProjects(
                auth_pb2.GetProjectsRequest(account_id=account.account_id)
            )

            assert len(response.projects) == 5

        print("✅ Project count consistent: always 5")

    async def test_api_key_validation_consistency(self):
        """Test that API key validation is consistent."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="keyvalconsist@example.com", password="password123", plan="free"
            )
        )

        project = await self.stub.CreateProject(
            auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name="Consistency Test",
                slug="consistency-test",
                environment="production",
            )
        )

        api_key = await self.stub.CreateApiKey(
            auth_pb2.CreateApiKeyRequest(project_id=project.project_id, name="Test Key")
        )

        for i in range(10):
            response = await self.stub.ValidateApiKey(
                auth_pb2.ValidateApiKeyRequest(api_key=api_key.full_key)
            )

            assert response.valid is True
            assert response.project_id == project.project_id

        print("✅ API key validation consistent across 10 attempts")
