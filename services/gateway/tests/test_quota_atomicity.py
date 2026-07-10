import asyncio
import datetime

import pytest

import gateway_service.services.redis_client as redis_client_module


def _usage_key(project_id: int, signal: str = "logs") -> str:
    today = datetime.date.today().strftime("%Y%m%d")
    return f"usage:{project_id}:{signal}:{today}"


@pytest.mark.asyncio
class TestTryConsumeQuotaAtomicity:
    async def _make_client(self) -> redis_client_module.RedisClient:
        client = redis_client_module.RedisClient("redis://localhost:6379/0", decode_responses=False)
        await client.connect()
        return client

    @pytest.mark.parametrize("signal", ["logs", "spans", "metrics"])
    async def test_concurrent_consumers_never_exceed_daily_quota(self, signal):
        client = await self._make_client()
        project_id = 990001
        daily_quota = 100
        amount = 7

        try:
            results = await asyncio.gather(
                *[
                    client.try_consume_quota(project_id, signal, amount, daily_quota)
                    for _ in range(50)
                ]
            )

            allowed_count = sum(1 for allowed, _ in results if allowed)
            denied_count = sum(1 for allowed, _ in results if not allowed)
            final_usage = await client.get_daily_usage(project_id, signal=signal)

            assert allowed_count + denied_count == 50
            assert final_usage == allowed_count * amount
            assert final_usage <= daily_quota
            # 100 // 7 == 14 requests should fit before the 15th overflows.
            assert allowed_count == 14
        finally:
            await client.delete(_usage_key(project_id, signal))
            await client.close()

    @pytest.mark.parametrize("signal", ["logs", "spans", "metrics"])
    async def test_denied_request_does_not_increment_usage(self, signal):
        client = await self._make_client()
        project_id = 990002
        daily_quota = 10

        try:
            allowed_1, usage_1 = await client.try_consume_quota(project_id, signal, 8, daily_quota)
            allowed_2, usage_2 = await client.try_consume_quota(project_id, signal, 5, daily_quota)
            usage_after = await client.get_daily_usage(project_id, signal=signal)

            assert allowed_1 is True
            assert usage_1 == 8
            assert allowed_2 is False
            assert usage_after == 8
        finally:
            await client.delete(_usage_key(project_id, signal))
            await client.close()

    @pytest.mark.parametrize("signal", ["logs", "spans", "metrics"])
    async def test_exact_quota_boundary_is_allowed(self, signal):
        client = await self._make_client()
        project_id = 990003
        daily_quota = 20

        try:
            allowed, usage = await client.try_consume_quota(project_id, signal, 20, daily_quota)

            assert allowed is True
            assert usage == 20
        finally:
            await client.delete(_usage_key(project_id, signal))
            await client.close()

    async def test_signals_are_isolated_per_project(self):
        """Exhausting one signal's quota must not affect the others - this is
        the structural fix for the prod incident where logs/spans/metrics
        shared a single counter."""
        client = await self._make_client()
        project_id = 990004
        quota = 5

        try:
            logs_allowed, _ = await client.try_consume_quota(project_id, "logs", 5, quota)
            spans_allowed, spans_usage = await client.try_consume_quota(
                project_id, "spans", 3, quota
            )
            metrics_allowed, metrics_usage = await client.try_consume_quota(
                project_id, "metrics", 1, quota
            )

            assert logs_allowed is True
            assert spans_allowed is True
            assert spans_usage == 3
            assert metrics_allowed is True
            assert metrics_usage == 1

            usage_by_signal = await client.get_daily_usage_by_signal(project_id)
            assert usage_by_signal == {"logs": 5, "spans": 3, "metrics": 1}
        finally:
            await client.delete(_usage_key(project_id, "logs"))
            await client.delete(_usage_key(project_id, "spans"))
            await client.delete(_usage_key(project_id, "metrics"))
            await client.close()
