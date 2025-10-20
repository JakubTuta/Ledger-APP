import datetime
import json

import pytest

import query_service.proto.query_pb2 as query_pb2
import tests.test_base as test_base


class TestMetrics(test_base.BaseQueryTest):
    @pytest.mark.asyncio
    async def test_get_error_rate(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        cache_key = "metrics:error_rate:1:5min"

        test_data = {
            "project_id": 1,
            "interval": "5min",
            "data": [
                {
                    "timestamp": now.isoformat(),
                    "error_count": 42,
                    "critical_count": 3,
                },
                {
                    "timestamp": (now - datetime.timedelta(minutes=5)).isoformat(),
                    "error_count": 38,
                    "critical_count": 1,
                },
            ],
        }

        await self.redis.set(cache_key, json.dumps(test_data))

        request = query_pb2.GetErrorRateRequest(
            project_id=1,
            interval="5min",
        )

        response = await self.stub.GetErrorRate(request)

        assert response.project_id == 1
        assert response.interval == "5min"
        assert len(response.data) == 2
        assert response.data[0].error_count == 42
        assert response.data[0].critical_count == 3

    @pytest.mark.asyncio
    async def test_get_error_rate_not_found(self):
        request = query_pb2.GetErrorRateRequest(
            project_id=999,
            interval="5min",
        )

        response = await self.stub.GetErrorRate(request)

        assert response.project_id == 999
        assert len(response.data) == 0

    @pytest.mark.asyncio
    async def test_get_error_rate_different_intervals(self):
        for interval in ["5min", "15min", "1hour", "1day"]:
            cache_key = f"metrics:error_rate:1:{interval}"
            test_data = {
                "project_id": 1,
                "interval": interval,
                "data": [
                    {
                        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "error_count": 10,
                        "critical_count": 1,
                    }
                ],
            }
            await self.redis.set(cache_key, json.dumps(test_data))

            request = query_pb2.GetErrorRateRequest(
                project_id=1,
                interval=interval,
            )

            response = await self.stub.GetErrorRate(request)

            assert response.interval == interval
            assert len(response.data) == 1

    @pytest.mark.asyncio
    async def test_get_log_volume(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        cache_key = "metrics:log_volume:1:1hour"

        test_data = {
            "project_id": 1,
            "interval": "1hour",
            "data": [
                {
                    "timestamp": now.isoformat(),
                    "debug": 1523,
                    "info": 8934,
                    "warning": 234,
                    "error": 42,
                    "critical": 3,
                },
                {
                    "timestamp": (now - datetime.timedelta(hours=1)).isoformat(),
                    "debug": 1234,
                    "info": 7890,
                    "warning": 123,
                    "error": 23,
                    "critical": 1,
                },
            ],
        }

        await self.redis.set(cache_key, json.dumps(test_data))

        request = query_pb2.GetLogVolumeRequest(
            project_id=1,
            interval="1hour",
        )

        response = await self.stub.GetLogVolume(request)

        assert response.project_id == 1
        assert response.interval == "1hour"
        assert len(response.data) == 2
        assert response.data[0].debug == 1523
        assert response.data[0].info == 8934
        assert response.data[0].warning == 234
        assert response.data[0].error == 42
        assert response.data[0].critical == 3

    @pytest.mark.asyncio
    async def test_get_log_volume_not_found(self):
        request = query_pb2.GetLogVolumeRequest(
            project_id=999,
            interval="1hour",
        )

        response = await self.stub.GetLogVolume(request)

        assert response.project_id == 999
        assert len(response.data) == 0

    @pytest.mark.asyncio
    async def test_get_top_errors(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        cache_key = "metrics:top_errors:1"

        test_data = {
            "project_id": 1,
            "errors": [
                {
                    "fingerprint": "abc123def456",
                    "error_type": "TimeoutError",
                    "error_message": "Database connection timeout",
                    "occurrence_count": 234,
                    "first_seen": (now - datetime.timedelta(hours=24)).isoformat(),
                    "last_seen": now.isoformat(),
                    "status": "unresolved",
                    "sample_log_id": 12345,
                },
                {
                    "fingerprint": "xyz789uvw012",
                    "error_type": "ValueError",
                    "error_message": "Invalid user input",
                    "occurrence_count": 156,
                    "first_seen": (now - datetime.timedelta(hours=12)).isoformat(),
                    "last_seen": now.isoformat(),
                    "status": "unresolved",
                    "sample_log_id": 12346,
                },
            ],
        }

        await self.redis.set(cache_key, json.dumps(test_data))

        request = query_pb2.GetTopErrorsRequest(
            project_id=1,
            limit=10,
        )

        response = await self.stub.GetTopErrors(request)

        assert response.project_id == 1
        assert len(response.errors) == 2
        assert response.errors[0].fingerprint == "abc123def456"
        assert response.errors[0].error_type == "TimeoutError"
        assert response.errors[0].occurrence_count == 234
        assert response.errors[0].status == "unresolved"
        assert response.errors[0].sample_log_id == 12345

    @pytest.mark.asyncio
    async def test_get_top_errors_not_found(self):
        request = query_pb2.GetTopErrorsRequest(
            project_id=999,
            limit=10,
        )

        response = await self.stub.GetTopErrors(request)

        assert response.project_id == 999
        assert len(response.errors) == 0

    @pytest.mark.asyncio
    async def test_get_top_errors_with_limit(self):
        cache_key = "metrics:top_errors:1"

        test_data = {
            "project_id": 1,
            "errors": [
                {
                    "fingerprint": f"fp{i}",
                    "error_type": f"Error{i}",
                    "occurrence_count": 100 - i,
                    "first_seen": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "last_seen": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "status": "unresolved",
                }
                for i in range(20)
            ],
        }

        await self.redis.set(cache_key, json.dumps(test_data))

        request = query_pb2.GetTopErrorsRequest(
            project_id=1,
            limit=5,
        )

        response = await self.stub.GetTopErrors(request)

        assert len(response.errors) == 5

    @pytest.mark.asyncio
    async def test_get_usage_stats(self):
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
        assert response.usage[0].daily_quota == 1000000
        assert abs(response.usage[0].quota_used_percent - 45.6) < 0.01

    @pytest.mark.asyncio
    async def test_get_usage_stats_not_found(self):
        request = query_pb2.GetUsageStatsRequest(
            project_id=999,
        )

        response = await self.stub.GetUsageStats(request)

        assert response.project_id == 999
        assert len(response.usage) == 0

    @pytest.mark.asyncio
    async def test_metrics_cache_ttl(self):
        cache_key = "metrics:error_rate:1:5min"

        test_data = {
            "project_id": 1,
            "interval": "5min",
            "data": [],
        }

        await self.redis.set(cache_key, json.dumps(test_data), ex=600)

        ttl = await self.redis.ttl(cache_key)
        assert ttl > 0
        assert ttl <= 600

    @pytest.mark.asyncio
    async def test_metrics_multiple_projects(self):
        now = datetime.datetime.now(datetime.timezone.utc)

        for project_id in [1, 2, 3]:
            cache_key = f"metrics:error_rate:{project_id}:5min"
            test_data = {
                "project_id": project_id,
                "interval": "5min",
                "data": [
                    {
                        "timestamp": now.isoformat(),
                        "error_count": project_id * 10,
                        "critical_count": project_id,
                    }
                ],
            }
            await self.redis.set(cache_key, json.dumps(test_data))

        for project_id in [1, 2, 3]:
            request = query_pb2.GetErrorRateRequest(
                project_id=project_id,
                interval="5min",
            )

            response = await self.stub.GetErrorRate(request)

            assert response.project_id == project_id
            assert len(response.data) == 1
            assert response.data[0].error_count == project_id * 10
            assert response.data[0].critical_count == project_id
