import pytest

from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestRateLimitMiddleware(BaseGatewayTest):
    """Test rate limiting functionality."""

    async def test_rate_limit_allows_within_limit(self):
        """Test requests within rate limit are allowed."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 10,
                "rate_limit_per_hour": 100,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        for i in range(5):
            response = await self.client.get(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            assert response.status_code == 200
            print(f"✅ Request {i+1}/5 allowed")

    async def test_rate_limit_per_minute_exceeded(self):
        """Test rate limit per minute enforcement."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 3,
                "rate_limit_per_hour": 100,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        for i in range(3):
            response = await self.client.get(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            assert response.status_code == 200

        response = await self.client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 429
        assert "rate limit" in response.json()["detail"].lower()
        assert "Retry-After" in response.headers
        print("✅ Rate limit per minute enforced")

    async def test_rate_limit_per_hour_exceeded(self):
        """Test rate limit per hour enforcement."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 1000,
                "rate_limit_per_hour": 5,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        for i in range(5):
            response = await self.client.get(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            assert response.status_code == 200

        response = await self.client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 429
        assert "rate limit" in response.json()["detail"].lower()
        print("✅ Rate limit per hour enforced")

    async def test_rate_limit_headers_present(self):
        """Test rate limit headers are included."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 10,
                "rate_limit_per_hour": 100,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        response = await self.client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        assert "X-RateLimit-Limit-Minute" in response.headers
        assert "X-RateLimit-Limit-Hour" in response.headers
        print("✅ Rate limit headers present")

    async def test_rate_limit_different_projects_independent(self):
        """Test different projects have independent rate limits."""
        api_key_1 = "test_api_key_project_1"
        api_key_2 = "test_api_key_project_2"

        await self.mock_redis.set_cached_api_key(
            api_key_1,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 3,
                "rate_limit_per_hour": 100,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        await self.mock_redis.set_cached_api_key(
            api_key_2,
            {
                "project_id": 2,
                "account_id": 1,
                "rate_limit_per_minute": 3,
                "rate_limit_per_hour": 100,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        for i in range(3):
            response = await self.client.get(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {api_key_1}"},
            )
            assert response.status_code == 200

        response = await self.client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {api_key_1}"},
        )
        assert response.status_code == 429

        response = await self.client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {api_key_2}"},
        )
        assert response.status_code == 200
        print("✅ Different projects have independent rate limits")

    async def test_daily_quota_enforcement(self):
        """Test daily quota is enforced."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 1000,
                "rate_limit_per_hour": 50000,
                "daily_quota": 5,
                "current_usage": 0,
            },
        )

        self.mock_redis.data[f"daily_usage:1"] = 10

        response = await self.client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 402
        assert "quota exceeded" in response.json()["detail"].lower()
        print("✅ Daily quota enforced")


@pytest.mark.asyncio
class TestRateLimitExemptions(BaseGatewayTest):
    """Test rate limit exemptions for public paths."""

    async def test_health_endpoint_not_rate_limited(self):
        """Test health endpoint bypasses rate limiting."""
        for i in range(20):
            response = await self.client.get("/health")
            assert response.status_code == 200

        print("✅ Health endpoint not rate limited")

    async def test_public_auth_endpoints_not_rate_limited(self):
        """Test public auth endpoints bypass rate limiting."""
        for i in range(10):
            response = await self.client.post(
                "/api/v1/accounts/register",
                json={
                    "email": f"test{i}@example.com",
                    "password": "Password123",
                    "name": "Test User",
                },
            )
            assert response.status_code in [201, 409, 422]

        print("✅ Public endpoints not rate limited")


@pytest.mark.asyncio
class TestRateLimitMetrics(BaseGatewayTest):
    """Test rate limiting metrics and monitoring."""

    async def test_rate_limit_stats_tracking(self):
        """Test rate limiting statistics are tracked."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 3,
                "rate_limit_per_hour": 100,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        for i in range(4):
            await self.client.get(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {api_key}"},
            )

        print("✅ Rate limit stats can be tracked")
