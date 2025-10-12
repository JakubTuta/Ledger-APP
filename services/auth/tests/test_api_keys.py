import pytest
from auth_service.proto import auth_pb2

from .test_base import BaseGrpcTest


@pytest.mark.asyncio
class TestApiKeyEndpoints(BaseGrpcTest):
    """Test API key operations."""

    async def test_create_api_key(self):
        """Test creating an API key."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="apikey@example.com", password="password123", plan="free"
            )
        )

        project = await self.stub.CreateProject(
            auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name="Test Project",
                slug="test-project",
                environment="production",
            )
        )

        request = auth_pb2.CreateApiKeyRequest(
            project_id=project.project_id, name="Production Key"
        )
        response = await self.stub.CreateApiKey(request)

        assert response.key_id > 0
        assert response.full_key.startswith("ak_live_")
        assert len(response.full_key) > 40
        assert response.key_prefix == response.full_key[:20]

        print(f"✅ Created API key: {response.full_key[:30]}...")

    async def test_validate_api_key_success(self):
        """Test validating a valid API key."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="validate@example.com", password="password123", plan="pro"
            )
        )

        project = await self.stub.CreateProject(
            auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name="Validation Test",
                slug="validation-test",
                environment="production",
            )
        )

        api_key = await self.stub.CreateApiKey(
            auth_pb2.CreateApiKeyRequest(project_id=project.project_id, name="Test Key")
        )

        request = auth_pb2.ValidateApiKeyRequest(api_key=api_key.full_key)
        response = await self.stub.ValidateApiKey(request)

        assert response.valid is True
        assert response.project_id == project.project_id
        assert response.daily_quota > 0
        assert response.retention_days > 0

        print(f"✅ API key validated for project: {response.project_id}")

    async def test_validate_invalid_api_key(self):
        """Test validating an invalid API key."""
        request = auth_pb2.ValidateApiKeyRequest(
            api_key="ak_live_invalid_key_does_not_exist"
        )
        response = await self.stub.ValidateApiKey(request)

        assert response.valid is False
        assert "invalid" in response.error_message.lower()

        print(f"✅ Correctly rejected invalid API key")

    async def test_revoke_api_key(self):
        """Test revoking an API key."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="revoke@example.com", password="password123", plan="free"
            )
        )

        project = await self.stub.CreateProject(
            auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name="Revoke Test",
                slug="revoke-test",
                environment="production",
            )
        )

        api_key = await self.stub.CreateApiKey(
            auth_pb2.CreateApiKeyRequest(
                project_id=project.project_id, name="To Be Revoked"
            )
        )

        validate_response = await self.stub.ValidateApiKey(
            auth_pb2.ValidateApiKeyRequest(api_key=api_key.full_key)
        )
        assert validate_response.valid is True

        revoke_request = auth_pb2.RevokeApiKeyRequest(key_id=api_key.key_id)
        revoke_response = await self.stub.RevokeApiKey(revoke_request)

        assert revoke_response.success is True

        validate_response = await self.stub.ValidateApiKey(
            auth_pb2.ValidateApiKeyRequest(api_key=api_key.full_key)
        )
        assert validate_response.valid is False

        print(f"✅ API key successfully revoked")
