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


def _otlp_delta_counter_body(name: str, value: int, service_name: str) -> dict:
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
                                "sum": {
                                    "dataPoints": [
                                        {
                                            "timeUnixNano": str(now_ns),
                                            "asInt": str(value),
                                        }
                                    ],
                                    "aggregationTemporality": "AGGREGATION_TEMPORALITY_DELTA",
                                    "isMonotonic": True,
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
        self,
        client: httpx.AsyncClient,
        auth_headers: dict,
        project: dict,
        api_key_headers: dict,
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

        async def _metric_is_listed() -> bool:
            response = await client.get(
                "/api/v1/metrics/names",
                headers=auth_headers,
                params={"project_id": project["project_id"]},
            )
            if response.status_code != 200:
                return False
            return any(
                metric["name"] == metric_name for metric in response.json()["metrics"]
            )

        await poll_until(
            _metric_is_listed,
            timeout=30.0,
            interval=1.0,
            description="metric name to become discoverable",
        )

        tags_response = await client.get(
            f"/api/v1/metrics/{metric_name}/tags",
            headers=auth_headers,
            params={"project_id": project["project_id"]},
        )
        assert tags_response.status_code == 200, tags_response.text
        tag_keys = {entry["key"]: entry["values"] for entry in tags_response.json()["keys"]}
        assert "e2e" in tag_keys["region"]

        series_response = await client.get(
            f"/api/v1/metrics/{metric_name}/series",
            headers=auth_headers,
            params={
                "project_id": project["project_id"],
                "aggregation": "avg",
                "group_by": ["region"],
                "interval": "5m",
            },
        )
        assert series_response.status_code == 200, series_response.text
        body = series_response.json()

        assert body["type"] == "gauge"
        assert len(body["series"]) == 1
        assert body["series"][0]["tags"]["region"] == "e2e"
        assert body["series"][0]["points"][-1]["value"] == pytest.approx(42.5)

    async def test_delta_counter_sums_per_bucket(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict,
        project: dict,
        api_key_headers: dict,
    ):
        """Three delta increments of 2 read back as 6, not as three separate points."""
        metric_name = f"e2e.counter.{_hex(8)}"

        for _ in range(3):
            response = await client.post(
                "/v1/metrics",
                content=json.dumps(
                    _otlp_delta_counter_body(metric_name, 2, "e2e-metrics-service")
                ).encode(),
                headers={**api_key_headers, "Content-Type": "application/json"},
            )
            assert response.status_code == 200, response.text

        async def _counter_totals_six() -> bool:
            response = await client.get(
                f"/api/v1/metrics/{metric_name}/series",
                headers=auth_headers,
                params={
                    "project_id": project["project_id"],
                    "aggregation": "sum",
                    "interval": "1h",
                },
            )
            if response.status_code != 200:
                return False
            series = response.json()["series"]
            if not series:
                return False
            return sum(point["value"] for point in series[0]["points"]) == 6.0

        await poll_until(
            _counter_totals_six,
            timeout=30.0,
            interval=1.0,
            description="delta counter to total 6 across the bucket",
        )
