import asyncio
import datetime

import pytest

import gateway_service.services.redis_client as redis_client_module


def _usage_key(project_id: int) -> str:
    today = datetime.date.today().strftime("%Y%m%d")
    return f"usage:{project_id}:{today}"


@pytest.mark.asyncio
class TestTryConsumeQuotaAtomicity:
    async def _make_client(self) -> redis_client_module.RedisClient:
        client = redis_client_module.RedisClient("redis://localhost:6379/0", decode_responses=False)
        await client.connect()
        return client

    async def test_concurrent_consumers_never_exceed_daily_quota(self):
        client = await self._make_client()
        project_id = 990001
        daily_quota = 100
        amount = 7

        try:
            results = await asyncio.gather(
                *[client.try_consume_quota(project_id, amount, daily_quota) for _ in range(50)]
            )

            allowed_count = sum(1 for allowed, _ in results if allowed)
            denied_count = sum(1 for allowed, _ in results if not allowed)
            final_usage = await client.get_daily_usage(project_id)

            assert allowed_count + denied_count == 50
            assert final_usage == allowed_count * amount
            assert final_usage <= daily_quota
            # 100 // 7 == 14 requests should fit before the 15th overflows.
            assert allowed_count == 14
        finally:
            await client.delete(_usage_key(project_id))
            await client.close()

    async def test_denied_request_does_not_increment_usage(self):
        client = await self._make_client()
        project_id = 990002
        daily_quota = 10

        try:
            allowed_1, usage_1 = await client.try_consume_quota(project_id, 8, daily_quota)
            allowed_2, usage_2 = await client.try_consume_quota(project_id, 5, daily_quota)
            usage_after = await client.get_daily_usage(project_id)

            assert allowed_1 is True
            assert usage_1 == 8
            assert allowed_2 is False
            assert usage_after == 8
        finally:
            await client.delete(_usage_key(project_id))
            await client.close()

    async def test_exact_quota_boundary_is_allowed(self):
        client = await self._make_client()
        project_id = 990003
        daily_quota = 20

        try:
            allowed, usage = await client.try_consume_quota(project_id, 20, daily_quota)

            assert allowed is True
            assert usage == 20
        finally:
            await client.delete(_usage_key(project_id))
            await client.close()
