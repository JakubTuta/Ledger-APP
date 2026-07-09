import json
import time
import uuid

import httpx
import pytest

from .helpers import poll_until

pytestmark = pytest.mark.e2e


def _hex(n: int) -> str:
    return uuid.uuid4().hex[:n]


def _otlp_trace_body(trace_id: str, span_id: str, service_name: str, operation: str) -> dict:
    start_ns = int(time.time() * 1e9)
    end_ns = start_ns + 50_000_000  # 50ms span
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service_name}},
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": span_id,
                                "name": operation,
                                "kind": "SPAN_KIND_SERVER",
                                "startTimeUnixNano": str(start_ns),
                                "endTimeUnixNano": str(end_ns),
                                "status": {"code": "STATUS_CODE_OK"},
                            }
                        ]
                    }
                ],
            }
        ]
    }


def _otlp_metric_body(name: str, value: float, service_name: str) -> dict:
    now_ns = int(time.time() * 1e9)
    return {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service_name}},
                    ]
                },
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": name,
                                "gauge": {
                                    "dataPoints": [
                                        {
                                            "timeUnixNano": str(now_ns),
                                            "asDouble": value,
                                            "attributes": [
                                                {
                                                    "key": "region",
                                                    "value": {"stringValue": "e2e"},
                                                }
                                            ],
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


class TestOtlpTracesFlow:
    async def test_ingest_trace_then_query_back(
        self, client: httpx.AsyncClient, auth_headers: dict, project: dict, api_key_headers: dict
    ):
        trace_id = _hex(32)
        span_id = _hex(16)
        operation = f"e2e-op-{_hex(8)}"

        ingest_response = await client.post(
            "/v1/traces",
            content=json.dumps(
                _otlp_trace_body(trace_id, span_id, "e2e-trace-service", operation)
            ).encode(),
            headers={**api_key_headers, "Content-Type": "application/json"},
        )
        assert ingest_response.status_code == 200, ingest_response.text

        async def _trace_is_queryable() -> bool:
            response = await client.get(
                "/api/v1/traces",
                headers=auth_headers,
                params={"project_id": project["project_id"], "operation": operation},
            )
            if response.status_code != 200:
                return False
            return len(response.json()["traces"]) > 0

        await poll_until(
            _trace_is_queryable, timeout=30.0, interval=1.0, description="trace to become queryable"
        )


class TestOtlpMetricsFlow:
    async def test_ingest_metric_then_query_back(
        self, client: httpx.AsyncClient, auth_headers: dict, project: dict, api_key_headers: dict
    ):
        metric_name = f"e2e.gauge.{_hex(8)}"

        ingest_response = await client.post(
            "/v1/metrics",
            content=json.dumps(
                _otlp_metric_body(metric_name, 42.5, "e2e-metrics-service")
            ).encode(),
            headers={**api_key_headers, "Content-Type": "application/json"},
        )
        assert ingest_response.status_code == 200, ingest_response.text

        async def _metric_is_queryable() -> bool:
            # No fromTime/toTime -> reads raw metric_points directly rather
            # than metric_points_1h, so this doesn't need to wait on the
            # rollup cron (ANALYTICS_METRIC_POINTS_1H_ROLLUP_CRON, every
            # 10 minutes) to catch up.
            response = await client.get(
                "/api/v1/metrics/query",
                headers=auth_headers,
                params={
                    "project_id": project["project_id"],
                    "name": metric_name,
                    "aggregation": "avg",
                },
            )
            if response.status_code != 200:
                return False
            data_points = response.json().get("data", [])
            return len(data_points) > 0

        await poll_until(
            _metric_is_queryable,
            timeout=30.0,
            interval=1.0,
            description="metric point to become queryable",
        )
