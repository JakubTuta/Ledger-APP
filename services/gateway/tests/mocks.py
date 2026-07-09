import typing

import gateway_service.proto.auth_pb2 as auth_pb2
import gateway_service.proto.ingestion_pb2 as ingestion_pb2


class MockRedisClient:
    def __init__(self):
        self.data = {}
        self.client = self

    async def get(self, key: str) -> typing.Optional[str]:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: typing.Optional[int] = None) -> None:
        self.data[key] = value

    async def setex(self, key: str, seconds: int, value: str) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> None:
        if key in self.data:
            del self.data[key]

    async def incr(self, key: str) -> int:
        if key not in self.data:
            self.data[key] = 0
        self.data[key] += 1
        return self.data[key]

    async def expire(self, key: str, seconds: int) -> None:
        pass

    async def ttl(self, key: str) -> int:
        return 300 if key in self.data else -2

    def pipeline(self):
        return MockRedisPipeline(self)

    async def ping(self) -> bool:
        return True

    async def get_cached_api_key(self, api_key: str) -> typing.Optional[dict]:
        key = f"api_key:cache:{api_key}"
        return self.data.get(key)

    async def set_cached_api_key(
        self, api_key: str, data: dict, ttl: typing.Optional[int] = None
    ) -> None:
        key = f"api_key:cache:{api_key}"
        self.data[key] = data

    async def get_stale_cache(self, api_key: str) -> typing.Optional[dict]:
        key = f"api_key:stale:{api_key}"
        return self.data.get(key)

    async def get_cached_project_access(
        self, account_id: int, project_id: int
    ) -> typing.Optional[bool]:
        key = f"project_access:{account_id}:{project_id}"
        return self.data.get(key)

    async def set_cached_project_access(
        self, account_id: int, project_id: int, is_member: bool, ttl: int = 60
    ) -> None:
        key = f"project_access:{account_id}:{project_id}"
        self.data[key] = is_member

    async def delete_cached_project_access(self, account_id: int, project_id: int) -> None:
        key = f"project_access:{account_id}:{project_id}"
        self.data.pop(key, None)

    async def get_daily_usage(self, project_id: int) -> int:
        key = f"daily_usage:{project_id}"
        return self.data.get(key, 0)

    async def check_rate_limit(
        self,
        project_id: int,
        limit_per_minute: int,
        limit_per_hour: int,
        key_prefix: str = "project",
        amount: int = 1,
    ) -> tuple[bool, dict]:
        minute_key = f"ratelimit:{key_prefix}:{project_id}:minute"
        hour_key = f"ratelimit:{key_prefix}:{project_id}:hour"

        minute_count = self.data.get(minute_key, 0)
        hour_count = self.data.get(hour_key, 0)

        minute_count += amount
        hour_count += amount

        self.data[minute_key] = minute_count
        self.data[hour_key] = hour_count

        allowed = minute_count <= limit_per_minute and hour_count <= limit_per_hour

        return allowed, {
            "minute_count": minute_count,
            "minute_limit": limit_per_minute,
            "hour_count": hour_count,
            "hour_limit": limit_per_hour,
        }

    async def try_consume_quota(
        self, project_id: int, amount: int, daily_quota: int
    ) -> tuple[bool, int]:
        key = f"daily_usage:{project_id}"
        current = self.data.get(key, 0)
        new_usage = current + amount

        if new_usage > daily_quota:
            return False, current

        self.data[key] = new_usage
        return True, new_usage

    def pubsub(self):
        return MockRedisPubSub()

    async def publish(self, channel: str, message: str) -> int:
        return 0

    async def close(self) -> None:
        pass


class MockRedisPubSub:
    def __init__(self):
        self.channels = []
        self.messages = []

    async def subscribe(self, *channels):
        self.channels.extend(channels)

    async def unsubscribe(self, *channels):
        for channel in channels:
            if channel in self.channels:
                self.channels.remove(channel)

    async def listen(self):
        yield {"type": "subscribe", "channel": self.channels[0] if self.channels else None}
        for message in self.messages:
            yield message

    async def close(self):
        pass


class MockRedisPipeline:
    def __init__(self, redis_client: MockRedisClient):
        self.redis_client = redis_client
        self.commands = []

    def incr(self, key: str):
        self.commands.append(("incr", key))
        return self

    def expire(self, key: str, seconds: int):
        self.commands.append(("expire", key, seconds))
        return self

    async def execute(self) -> list:
        results = []
        for command in self.commands:
            if command[0] == "incr":
                result = await self.redis_client.incr(command[1])
                results.append(result)
            elif command[0] == "expire":
                await self.redis_client.expire(command[1], command[2])
                results.append(True)
        return results


class MockAuthChannel:
    """Fake gRPC channel whose unary_unary() dispatches to a MockAuthStub by
    method name, so routes that build their own `AuthServiceStub(channel)`
    (rather than calling grpc_pool.get_stub(...) directly - see
    routes/alert_routes.py::_stub) still hit the same mock in tests."""

    def __init__(self, mock_stub: "MockAuthStub"):
        self._mock_stub = mock_stub

    def unary_unary(self, method_path: str, *args, **kwargs):
        # AuthServiceStub.__init__ eagerly binds every RPC on the service, not
        # just the ones a given route calls, so look up the mock method lazily
        # (inside `call`) rather than at bind time - MockAuthStub only needs to
        # implement the methods actually exercised by a given test.
        method_name = method_path.rsplit("/", 1)[-1]

        async def call(request, timeout=None, **kwargs):
            mock_method = getattr(self._mock_stub, method_name)
            return await mock_method(request, timeout=timeout)

        return call


class MockGRPCPool:
    def __init__(self):
        self.stubs = {}
        self.call_count = 0

    def get_channel(self, service_name: str):
        if service_name == "auth":
            return MockAuthChannel(self.get_stub("auth", None))
        return None

    def get_stub(self, service_name: str, stub_class):
        if service_name not in self.stubs:
            if service_name == "auth":
                self.stubs[service_name] = MockAuthStub()
            elif service_name == "ingestion":
                self.stubs[service_name] = MockIngestionStub()
        return self.stubs[service_name]

    def get_auth_stub(self):
        class ContextManager:
            def __init__(self, stub):
                self.stub = stub

            async def __aenter__(self):
                return self.stub

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        return ContextManager(self.get_stub("auth", None))

    def get_ingestion_stub(self):
        class ContextManager:
            def __init__(self, stub):
                self.stub = stub

            async def __aenter__(self):
                return self.stub

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        return ContextManager(self.get_stub("ingestion", None))

    def get_stats(self) -> dict:
        return {
            "auth": {
                "address": "localhost:50051",
                "pool_size": 10,
                "active_channels": 10,
            },
            "ingestion": {
                "address": "localhost:50052",
                "pool_size": 10,
                "active_channels": 10,
            },
        }

    async def close_all(self) -> None:
        pass


class MockAuthStub:
    def __init__(self):
        self.register_response = None
        self.login_response = None
        self.refresh_token_response = None
        self.validate_api_key_response = None
        self.create_project_response = None
        self.get_projects_response = None
        self.create_api_key_response = None
        self.revoke_api_key_response = None
        self.get_account_response = None

    async def Register(self, request, timeout=None):
        if self.register_response:
            return self.register_response
        return auth_pb2.RegisterResponse(
            account_id=1,
            email=request.email,
            plan="free",
            name="Test User",
        )

    async def Login(self, request, timeout=None):
        if self.login_response:
            return self.login_response
        return auth_pb2.LoginResponse(
            account_id=1,
            email=request.email,
            plan="free",
            access_token="test_token_123",
            refresh_token="test_refresh_token_123",
            expires_in=3600,
        )

    async def RefreshToken(self, request, timeout=None):
        if self.refresh_token_response:
            return self.refresh_token_response
        return auth_pb2.RefreshTokenResponse(
            access_token="new_test_token_456",
            refresh_token="new_test_refresh_token_456",
            expires_in=900,
            account_id=1,
            email="test@example.com",
        )

    async def ValidateApiKey(self, request, timeout=None):
        if self.validate_api_key_response:
            return self.validate_api_key_response
        return auth_pb2.ValidateApiKeyResponse(
            valid=True,
            project_id=1,
            account_id=1,
            daily_quota=1000000,
            retention_days=30,
            rate_limit_per_minute=1000,
            rate_limit_per_hour=50000,
            current_usage=0,
            error_message="",
        )

    async def CreateProject(self, request, timeout=None):
        if self.create_project_response:
            return self.create_project_response
        return auth_pb2.CreateProjectResponse(
            project_id=1,
            name=request.name,
            slug=request.slug,
            environment=request.environment,
            retention_days=30,
            daily_quota=1000000,
        )

    async def GetProjects(self, request, timeout=None):
        if self.get_projects_response:
            return self.get_projects_response
        return auth_pb2.GetProjectsResponse(projects=[])

    async def CreateApiKey(self, request, timeout=None):
        if self.create_api_key_response:
            return self.create_api_key_response
        return auth_pb2.CreateApiKeyResponse(
            key_id=1,
            full_key="ak_test_1234567890abcdef",
            key_prefix="ak_test_",
        )

    async def RevokeApiKey(self, request, timeout=None):
        if self.revoke_api_key_response:
            return self.revoke_api_key_response
        return auth_pb2.RevokeApiKeyResponse(success=True)

    async def GetAccount(self, request, timeout=None):
        if self.get_account_response:
            return self.get_account_response
        return auth_pb2.GetAccountResponse(
            account_id=request.account_id,
            email="test@example.com",
            plan="free",
            status="active",
            name="Test User",
            created_at="2024-01-01T00:00:00Z",
        )

    async def UpdateAccountName(self, request, timeout=None):
        return auth_pb2.UpdateAccountNameResponse(
            success=True,
            name=request.name,
        )

    async def ChangePassword(self, request, timeout=None):
        return auth_pb2.ChangePasswordResponse(
            success=True,
        )

    async def RevokeAllSessions(self, request, timeout=None):
        return auth_pb2.RevokeAllSessionsResponse(revoked_count=1)

    async def GetProjectRole(self, request, timeout=None):
        return auth_pb2.GetProjectRoleResponse(is_member=True, role="owner")

    async def AckAlertEvent(self, request, timeout=None):
        return auth_pb2.AckAlertEventResponse(
            success=True,
            event=auth_pb2.AlertEvent(
                id=request.event_id,
                project_id=request.project_id,
                rule_name="Test Rule",
                metric="error_rate",
                comparator=">",
                threshold=10.0,
                unit="percent",
                value=25.0,
                severity=3,
                connectors_sent="[]",
                fired_at="2026-01-01T00:00:00+00:00",
                acked_by=request.account_id,
                acked_at="2026-01-01T00:05:00+00:00",
            ),
        )

    async def SnoozeAlertEvent(self, request, timeout=None):
        return auth_pb2.SnoozeAlertEventResponse(
            success=True,
            event=auth_pb2.AlertEvent(
                id=request.event_id,
                project_id=request.project_id,
                rule_name="Test Rule",
                metric="error_rate",
                comparator=">",
                threshold=10.0,
                unit="percent",
                value=25.0,
                severity=3,
                connectors_sent="[]",
                fired_at="2026-01-01T00:00:00+00:00",
                snoozed_until="2026-01-01T01:00:00+00:00",
            ),
        )


class MockIngestionStub:
    def __init__(self):
        self.ingest_log_response = None
        self.ingest_log_batch_response = None
        self.get_queue_depth_response = None
        self.ingest_spans_batch_response = None
        self.ingest_metric_points_batch_response = None

    async def IngestLog(self, request, timeout=None):
        if self.ingest_log_response:
            return self.ingest_log_response
        return ingestion_pb2.IngestLogResponse(
            success=True,
            message="Log accepted for processing",
        )

    async def IngestLogBatch(self, request, timeout=None):
        if self.ingest_log_batch_response:
            return self.ingest_log_batch_response
        return ingestion_pb2.IngestLogBatchResponse(
            success=True,
            queued=len(request.logs),
            failed=0,
            error=None,
        )

    async def GetQueueDepth(self, request, timeout=None):
        if self.get_queue_depth_response:
            return self.get_queue_depth_response
        return ingestion_pb2.QueueDepthResponse(
            depth=0,
        )

    async def IngestSpansBatch(self, request, timeout=None):
        if self.ingest_spans_batch_response:
            return self.ingest_spans_batch_response
        return ingestion_pb2.IngestSpansBatchResponse(
            success=True,
            accepted=len(request.spans),
            rejected=0,
        )

    async def IngestMetricPointsBatch(self, request, timeout=None):
        if self.ingest_metric_points_batch_response:
            return self.ingest_metric_points_batch_response
        return ingestion_pb2.IngestMetricPointsBatchResponse(
            success=True,
            accepted=len(request.points),
            rejected=0,
        )
