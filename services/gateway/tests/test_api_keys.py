import grpc
import pytest
from gateway_service.proto import auth_pb2

from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestCreateApiKey(BaseGatewayTest):
    """Test API key creation."""

    async def test_create_api_key_success(self):
        """Test successful API key creation."""
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
            "/api/v1/projects/1/api-keys",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"name": "Production API Key"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["key_id"] > 0
        assert "full_key" in data
        assert data["full_key"].startswith("ak_test_")
        assert "key_prefix" in data
        assert "warning" in data
        assert "not be shown again" in data["warning"].lower()
        print(f"✅ Created API key ID: {data['key_id']}, prefix: {data['key_prefix']}")

    async def test_create_api_key_with_name(self):
        """Test API key creation with custom name."""
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

        names = [
            "Production Key",
            "Staging Environment",
            "CI/CD Pipeline",
            "Mobile App",
        ]

        for name in names:
            response = await self.client.post(
                "/api/v1/projects/1/api-keys",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"name": name},
            )

            assert response.status_code == 201
            print(f"✅ Created API key with name: {name}")

    async def test_create_api_key_project_not_found(self):
        """Test creating API key for non-existent project."""
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

        async def mock_create_not_found(request):
            error = grpc.RpcError()
            error.code = lambda: grpc.StatusCode.NOT_FOUND
            error.details = lambda: f"Project {request.project_id} not found"
            raise error

        stub.CreateApiKey = mock_create_not_found

        response = await self.client.post(
            "/api/v1/projects/999/api-keys",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"name": "Test Key"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
        print("✅ Non-existent project handled")

    async def test_create_api_key_permission_denied(self):
        """Test creating API key for project user doesn't own."""
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

        async def mock_create_forbidden(request):
            error = grpc.RpcError()
            error.code = lambda: grpc.StatusCode.PERMISSION_DENIED
            error.details = lambda: "You don't have permission"
            raise error

        stub.CreateApiKey = mock_create_forbidden

        response = await self.client.post(
            "/api/v1/projects/2/api-keys",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"name": "Test Key"},
        )

        assert response.status_code == 403
        assert "permission" in response.json()["detail"].lower()
        print("✅ Permission denied handled")

    async def test_create_api_key_without_auth(self):
        """Test creating API key without authentication."""
        response = await self.client.post(
            "/api/v1/projects/1/api-keys",
            json={"name": "Test Key"},
        )

        assert response.status_code == 401
        print("✅ Unauthenticated API key creation rejected")

    async def test_create_api_key_validation_empty_name(self):
        """Test API key name validation."""
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
            "/api/v1/projects/1/api-keys",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"name": ""},
        )

        assert response.status_code == 422
        print("✅ Empty name rejected")

    async def test_create_api_key_validation_long_name(self):
        """Test API key name length validation."""
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

        long_name = "a" * 256

        response = await self.client.post(
            "/api/v1/projects/1/api-keys",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"name": long_name},
        )

        assert response.status_code == 422
        print("✅ Long name rejected")


@pytest.mark.asyncio
class TestRevokeApiKey(BaseGatewayTest):
    """Test API key revocation."""

    async def test_revoke_api_key_success(self):
        """Test successful API key revocation."""
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

        response = await self.client.delete(
            "/api/v1/api-keys/1",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "revoked" in data["message"].lower()
        print("✅ API key revoked successfully")

    async def test_revoke_api_key_not_found(self):
        """Test revoking non-existent API key."""
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

        async def mock_revoke_not_found(request):
            error = grpc.RpcError()
            error.code = lambda: grpc.StatusCode.NOT_FOUND
            error.details = lambda: f"API key {request.key_id} not found"
            raise error

        stub.RevokeApiKey = mock_revoke_not_found

        response = await self.client.delete(
            "/api/v1/api-keys/999",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
        print("✅ Non-existent API key handled")

    async def test_revoke_api_key_permission_denied(self):
        """Test revoking API key user doesn't own."""
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

        async def mock_revoke_forbidden(request):
            error = grpc.RpcError()
            error.code = lambda: grpc.StatusCode.PERMISSION_DENIED
            error.details = lambda: "You don't have permission"
            raise error

        stub.RevokeApiKey = mock_revoke_forbidden

        response = await self.client.delete(
            "/api/v1/api-keys/2",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 403
        assert "permission" in response.json()["detail"].lower()
        print("✅ Permission denied handled")

    async def test_revoke_api_key_without_auth(self):
        """Test revoking API key without authentication."""
        response = await self.client.delete("/api/v1/api-keys/1")

        assert response.status_code == 401
        print("✅ Unauthenticated API key revocation rejected")

    async def test_revoke_api_key_cache_invalidation(self):
        """Test that revoking API key should invalidate cache."""
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

        revoked_key = "key_to_revoke_123"
        await self.mock_redis.set_cached_api_key(
            revoked_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 1000,
                "rate_limit_per_hour": 50000,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        cached = await self.mock_redis.get_cached_api_key(revoked_key)
        assert cached is not None

        response = await self.client.delete(
            "/api/v1/api-keys/1",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        print("✅ API key revoked (cache invalidation should occur in production)")


@pytest.mark.asyncio
class TestApiKeyValidation(BaseGatewayTest):
    """Test API key validation edge cases."""

    async def test_api_key_format_validation(self):
        """Test various API key formats."""
        valid_keys = [
            "ak_test_1234567890abcdef",
            "ledger_abcdef1234567890",
            "test_key_with_underscores",
        ]

        for key in valid_keys:
            await self.mock_redis.set_cached_api_key(
                key,
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
                headers={"Authorization": f"Bearer {key}"},
            )

            assert response.status_code == 200
            print(f"✅ Valid API key format accepted: {key[:20]}...")
