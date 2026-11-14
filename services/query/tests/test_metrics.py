import datetime
import json

import pytest

import query_service.proto.query_pb2 as query_pb2
import tests.test_base as test_base


class TestMetrics(test_base.BaseQueryTest):
    @pytest.mark.asyncio
    async def test_get_usage_stats_old_cache_shape_defaults_new_fields(self):
        """Cache items written before the logs/spans/metrics quota split only
        have the bare daily_quota/quota_used_percent keys. These must still
        map onto the logs_* proto fields, with the genuinely-new spans/metrics
        fields defaulting to 0 rather than erroring."""
        now = datetime.datetime.now(datetime.timezone.utc)
        today = now.date()
        cache_key = "metrics:usage_stats:1"

        test_data = {
            "project_id": 1,
            "daily_quota": 1000000,
            "usage": [
                {
                    "date": today.isoformat(),
                    "log_count": 456789,
                    "quota_used_percent": 45.6,
                },
                {
                    "date": (today - datetime.timedelta(days=1)).isoformat(),
                    "log_count": 523456,
                    "quota_used_percent": 52.3,
                },
            ],
        }

        await self.redis.set(cache_key, json.dumps(test_data))

        request = query_pb2.GetUsageStatsRequest(
            project_id=1,
        )

        response = await self.stub.GetUsageStats(request)

        assert response.project_id == 1
        assert len(response.usage) == 2
        assert response.usage[0].date == today.isoformat()
        assert response.usage[0].log_count == 456789
        assert response.usage[0].logs_daily_quota == 1000000
        assert abs(response.usage[0].logs_quota_used_percent - 45.6) < 0.01
        assert response.usage[0].span_count == 0
        assert response.usage[0].metric_point_count == 0
        assert response.usage[0].spans_daily_quota == 0
        assert response.usage[0].metrics_daily_quota == 0

    @pytest.mark.asyncio
    async def test_get_usage_stats_new_cache_shape(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        today = now.date()
        cache_key = "metrics:usage_stats:1"

        test_data = {
            "project_id": 1,
            "usage": [
                {
                    "date": today.isoformat(),
                    "log_count": 456789,
                    "span_count": 12345,
                    "metric_point_count": 678,
                    "logs_daily_quota": 1000000,
                    "spans_daily_quota": 3000000,
                    "metrics_daily_quota": 1000000,
                    "logs_quota_used_percent": 45.6,
                    "spans_quota_used_percent": 0.41,
                    "metrics_quota_used_percent": 0.07,
                },
            ],
        }

        await self.redis.set(cache_key, json.dumps(test_data))

        request = query_pb2.GetUsageStatsRequest(
            project_id=1,
        )

        response = await self.stub.GetUsageStats(request)

        assert response.project_id == 1
        assert len(response.usage) == 1
        entry = response.usage[0]
        assert entry.log_count == 456789
        assert entry.span_count == 12345
        assert entry.metric_point_count == 678
        assert entry.logs_daily_quota == 1000000
        assert entry.spans_daily_quota == 3000000
        assert entry.metrics_daily_quota == 1000000
        assert abs(entry.logs_quota_used_percent - 45.6) < 0.01
        assert abs(entry.spans_quota_used_percent - 0.41) < 0.01
        assert abs(entry.metrics_quota_used_percent - 0.07) < 0.01

    @pytest.mark.asyncio
    async def test_get_usage_stats_not_found(self):
        request = query_pb2.GetUsageStatsRequest(
            project_id=999,
        )

        response = await self.stub.GetUsageStats(request)

        assert response.project_id == 999
        assert len(response.usage) == 0
