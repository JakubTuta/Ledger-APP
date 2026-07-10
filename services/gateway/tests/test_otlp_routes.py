import gzip
import json

import grpc
import pytest
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from opentelemetry.proto.common.v1 import common_pb2

import gateway_service.proto.ingestion_pb2 as ingestion_pb2
import tests.test_base as test_base

TRACE_ID = bytes.fromhex("a" * 32)
SPAN_ID = bytes.fromhex("b" * 16)


def _protobuf_trace_body() -> bytes:
    request = trace_service_pb2.ExportTraceServiceRequest()
    rs = request.resource_spans.add()
    rs.resource.attributes.append(
        common_pb2.KeyValue(key="service.name", value=common_pb2.AnyValue(string_value="checkout"))
    )
    ss = rs.scope_spans.add()
    span = ss.spans.add()
    span.trace_id = TRACE_ID
    span.span_id = SPAN_ID
    span.name = "GET /users"
    span.start_time_unix_nano = 1_000_000_000
    span.end_time_unix_nano = 1_000_500_000
    return request.SerializeToString()


def _json_trace_body() -> bytes:
    data = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "checkout"}}]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "a" * 32,
                                "spanId": "b" * 16,
                                "name": "GET /users",
                                "startTimeUnixNano": "1000000000",
                                "endTimeUnixNano": "1000500000",
                            }
                        ]
                    }
                ],
            }
        ]
    }
    return json.dumps(data).encode()


def _json_log_body() -> bytes:
    data = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "checkout"}}]
                },
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "severityNumber": 9,
                                "body": {"stringValue": "hello"},
                            }
                        ]
                    }
                ],
            }
        ]
    }
    return json.dumps(data).encode()


def _json_metric_body() -> bytes:
    data = {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "checkout"}}]
                },
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "queue.depth",
                                "gauge": {
                                    "dataPoints": [
                                        {
                                            "timeUnixNano": "1000000000",
                                            "asDouble": 42.0,
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                ],
            }
        ]
    }
    return json.dumps(data).encode()


@pytest.mark.asyncio
class TestOtlpTraceRoute(test_base.BaseGatewayTest):
    async def test_protobuf_round_trip(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        response = await self.client.post(
            "/v1/traces",
            content=_protobuf_trace_body(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/x-protobuf",
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-protobuf"

        parsed = trace_service_pb2.ExportTraceServiceResponse()
        parsed.ParseFromString(response.content)
        assert parsed.partial_success.rejected_spans == 0

    async def test_json_round_trip(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        response = await self.client.post(
            "/v1/traces",
            content=_json_trace_body(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    async def test_gzip_json_body(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        response = await self.client.post(
            "/v1/traces",
            content=gzip.compress(_json_trace_body()),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
            },
        )

        assert response.status_code == 200

    async def test_without_api_key(self, setup_method):
        response = await self.client.post(
            "/v1/traces",
            content=_json_trace_body(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 401

    async def test_unsupported_content_type(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        response = await self.client.post(
            "/v1/traces",
            content=b"<xml/>",
            headers={"X-API-Key": "test_api_key_123", "Content-Type": "text/xml"},
        )
        assert response.status_code == 415

    async def test_malformed_json_body(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        response = await self.client.post(
            "/v1/traces",
            content=b"{not json",
            headers={"X-API-Key": "test_api_key_123", "Content-Type": "application/json"},
        )
        assert response.status_code == 400

    async def test_partial_success_reported(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        mock_stub = self.mock_grpc_pool.get_stub("ingestion", None)
        mock_stub.ingest_spans_batch_response = ingestion_pb2.IngestSpansBatchResponse(
            success=True, accepted=0, rejected=1
        )

        response = await self.client.post(
            "/v1/traces",
            content=_json_trace_body(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["partialSuccess"]["rejectedSpans"] == "1"

    async def test_queue_full_returns_503(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        mock_stub = self.mock_grpc_pool.get_stub("ingestion", None)

        class MockError(grpc.RpcError):
            def code(self):
                return grpc.StatusCode.RESOURCE_EXHAUSTED

            def details(self):
                return "Queue full"

        async def raise_error(*args, **kwargs):
            raise MockError()

        mock_stub.IngestSpansBatch = raise_error

        response = await self.client.post(
            "/v1/traces",
            content=_json_trace_body(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 503
        assert response.headers["retry-after"] == "60"

    async def test_batch_too_large_rejected(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        data = {
            "resourceSpans": [
                {
                    "scopeSpans": [
                        {
                            "spans": [
                                {"traceId": "a" * 32, "spanId": "b" * 16, "name": f"op{i}"}
                                for i in range(1001)
                            ]
                        }
                    ]
                }
            ]
        }

        response = await self.client.post(
            "/v1/traces",
            content=json.dumps(data).encode(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 400

    async def test_spans_quota_exceeded_rejects_without_forwarding(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1, spans_daily_quota=1)
        self.mock_redis.data["daily_usage:1:spans"] = 1

        mock_stub = self.mock_grpc_pool.get_stub("ingestion", None)

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("IngestSpansBatch should not be called once quota is exhausted")

        mock_stub.IngestSpansBatch = fail_if_called

        response = await self.client.post(
            "/v1/traces",
            content=_json_trace_body(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["partialSuccess"]["rejectedSpans"] == "1"

    async def test_spans_quota_exhaustion_does_not_block_logs_or_metrics(self, setup_method):
        """Regression test for the shared-quota incident: exhausting the spans
        quota must not affect logs or metrics ingestion for the same project."""
        await self.set_api_key_cache(
            "test_api_key_123",
            project_id=1,
            spans_daily_quota=1,
            logs_daily_quota=1000000,
            metrics_daily_quota=1000000,
        )
        self.mock_redis.data["daily_usage:1:spans"] = 1

        spans_response = await self.client.post(
            "/v1/traces",
            content=_json_trace_body(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
            },
        )
        spans_data = json.loads(spans_response.content)
        assert spans_data["partialSuccess"]["rejectedSpans"] == "1"

        logs_response = await self.client.post(
            "/v1/logs",
            content=_json_log_body(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
            },
        )
        assert logs_response.status_code == 200
        logs_data = json.loads(logs_response.content)
        assert "partialSuccess" not in logs_data or not logs_data.get("partialSuccess")

        metrics_response = await self.client.post(
            "/v1/metrics",
            content=_json_metric_body(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
            },
        )
        assert metrics_response.status_code == 200
        metrics_data = json.loads(metrics_response.content)
        assert "partialSuccess" not in metrics_data or not metrics_data.get("partialSuccess")


@pytest.mark.asyncio
class TestOtlpLogsRoute(test_base.BaseGatewayTest):
    async def test_json_round_trip(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        response = await self.client.post(
            "/v1/logs",
            content=_json_log_body(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200

    async def test_without_api_key(self, setup_method):
        response = await self.client.post(
            "/v1/logs",
            content=_json_log_body(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 401

    async def test_increments_daily_usage(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        await self.client.post(
            "/v1/logs",
            content=_json_log_body(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
            },
        )

        usage = await self.mock_redis.get_daily_usage(1)
        assert usage == 1

    async def test_quota_exceeded_rejects_without_forwarding(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1, logs_daily_quota=1)
        self.mock_redis.data["daily_usage:1:logs"] = 1

        mock_stub = self.mock_grpc_pool.get_stub("ingestion", None)

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("IngestLogBatch should not be called once quota is exhausted")

        mock_stub.IngestLogBatch = fail_if_called

        response = await self.client.post(
            "/v1/logs",
            content=_json_log_body(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["partialSuccess"]["rejectedLogRecords"] == "1"

        usage = await self.mock_redis.get_daily_usage(1)
        assert usage == 1

    async def test_quota_consumed_exactly_by_batch_size(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1, logs_daily_quota=100)

        data = {
            "resourceLogs": [
                {
                    "scopeLogs": [
                        {
                            "logRecords": [
                                {"severityNumber": 9, "body": {"stringValue": f"log {i}"}}
                                for i in range(5)
                            ]
                        }
                    ]
                }
            ]
        }

        await self.client.post(
            "/v1/logs",
            content=json.dumps(data).encode(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
            },
        )

        usage = await self.mock_redis.get_daily_usage(1)
        assert usage == 5


@pytest.mark.asyncio
class TestOtlpMetricsRoute(test_base.BaseGatewayTest):
    async def test_json_round_trip(self, setup_method):
        await self.set_api_key_cache("test_api_key_123", project_id=1)

        response = await self.client.post(
            "/v1/metrics",
            content=_json_metric_body(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200

    async def test_not_blocked_by_daily_quota_exhaustion(self, setup_method):
        """Regression test for the /v1/metrics 402 bug: the rate-limit middleware's
        read-only daily-quota check must exempt /v1/metrics like /v1/logs and
        /v1/traces, since the route reserves quota atomically itself and reports
        denials as a 200 partial-success (never a hard error an OTel exporter would
        retry-storm on)."""
        await self.set_api_key_cache("test_api_key_123", project_id=1, metrics_daily_quota=1)
        self.mock_redis.data["daily_usage:1:metrics"] = 1

        response = await self.client.post(
            "/v1/metrics",
            content=_json_metric_body(),
            headers={
                "X-API-Key": "test_api_key_123",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["partialSuccess"]["rejectedDataPoints"] == "1"
