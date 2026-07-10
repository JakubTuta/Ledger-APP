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

        request = auth_pb2.CreateApiKeyRequest(project_id=project.project_id, name="Production Key")
        response = await self.stub.CreateApiKey(request)

        assert response.key_id > 0
        assert response.full_key.startswith("ledger_")
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
        assert response.logs_daily_quota > 0
        assert response.spans_daily_quota > 0
        assert response.metrics_daily_quota > 0
        assert response.retention_days > 0

        print(f"✅ API key validated for project: {response.project_id}")

    async def test_validate_invalid_api_key(self):
        """Test validating an invalid API key."""
        request = auth_pb2.ValidateApiKeyRequest(api_key="ledger_invalid_key_does_not_exist")
        response = await self.stub.ValidateApiKey(request)

        assert response.valid is False
        assert "invalid" in response.error_message.lower()

        print("✅ Correctly rejected invalid API key")

    async def test_validate_api_key_stale_cache_hash_falls_through_to_db(self):
        """A Redis HASH written by a pre-quota-split deploy won't have
        spans_daily_quota/metrics_daily_quota fields. That must be treated as a
        cache miss (not a source of truth), falling through to the DB and
        rewriting the cache with the full field set."""
        import hashlib

        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="stalehash@example.com", password="password123", plan="pro"
            )
        )
        project = await self.stub.CreateProject(
            auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name="Stale Hash Test",
                slug="stale-hash-test",
                environment="production",
            )
        )
        api_key = await self.stub.CreateApiKey(
            auth_pb2.CreateApiKeyRequest(project_id=project.project_id, name="Test Key")
        )

        key_hash = hashlib.sha256(api_key.full_key.encode()).hexdigest()
        cache_key = f"api_key:{key_hash}"

        await self.redis.hset(
            cache_key,
            mapping={
                "project_id": project.project_id,
                "account_id": account.account_id,
                "logs_daily_quota": 100000,
                "retention_days": 30,
                "rate_limit_per_minute": 1000,
                "rate_limit_per_hour": 50000,
            },
        )

        request = auth_pb2.ValidateApiKeyRequest(api_key=api_key.full_key)
        response = await self.stub.ValidateApiKey(request)

        assert response.valid is True
        assert response.spans_daily_quota > 0
        assert response.metrics_daily_quota > 0

        refreshed = await self.redis.hgetall(cache_key)
        assert b"spans_daily_quota" in refreshed
        assert b"metrics_daily_quota" in refreshed

        print("✅ Stale cache hash treated as miss and refreshed from DB")

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
            auth_pb2.CreateApiKeyRequest(project_id=project.project_id, name="To Be Revoked")
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

        print("✅ API key successfully revoked")
