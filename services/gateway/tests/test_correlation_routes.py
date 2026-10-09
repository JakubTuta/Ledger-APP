import json

import pytest
from gateway_service.proto import query_pb2

from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestTraceLogs(BaseGatewayTest):
    async def test_returns_logs_and_forwards_the_span_filter(self):
        token = self.make_session_token(account_id=1)
        stub = self.get_mock_query_stub()
        stub.get_trace_logs_response = query_pb2.GetTraceLogsResponse(
            logs=[
                query_pb2.LogEntry(
                    id=7,
                    project_id=1,
                    timestamp="2026-10-09T10:00:00+00:00",
                    ingested_at="2026-10-09T10:00:01+00:00",
                    level="info",
                    log_type="logger",
                    importance="standard",
                    message="charged card",
                    attributes=json.dumps({"trace_id": "a" * 32}),
                )
            ],
            truncated=True,
        )

        response = await self.client.get(
            f"/api/v1/traces/{'a' * 32}/logs?project_id=1&span_id={'b' * 16}&limit=10",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["truncated"] is True
        assert body["logs"][0]["message"] == "charged card"
        assert body["logs"][0]["attributes"] == {"trace_id": "a" * 32}
        request = stub.last_get_trace_logs_request
        assert (request.span_id, request.limit) == ("b" * 16, 10)


@pytest.mark.asyncio
class TestServiceMap(BaseGatewayTest):
    async def test_returns_nodes_and_edges(self):
        token = self.make_session_token(account_id=1)
        self.get_mock_query_stub().get_service_map_response = query_pb2.GetServiceMapResponse(
            nodes=[query_pb2.ServiceNode(service="api", calls=10, errors=1, p95_ms=12.5)],
            edges=[query_pb2.ServiceEdge(caller="api", callee="postgresql", calls=30, p95_ms=2.0)],
            from_time="2026-10-09T09:00:00+00:00",
            to_time="2026-10-09T10:00:00+00:00",
        )

        response = await self.client.get(
            "/api/v1/services/map?project_id=1", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["nodes"] == [{"service": "api", "calls": 10, "errors": 1, "p95_ms": 12.5}]
        assert body["edges"][0]["callee"] == "postgresql"


@pytest.mark.asyncio
class TestServiceRed(BaseGatewayTest):
    async def test_service_level_series_have_no_operation(self):
        token = self.make_session_token(account_id=1)
        stub = self.get_mock_query_stub()
        stub.get_service_red_response = query_pb2.GetServiceRedResponse(
            interval="1m",
            series=[
                query_pb2.RedSeries(
                    service="api",
                    calls=3,
                    points=[query_pb2.RedPoint(bucket="2026-10-09T10:00:00+00:00", calls=3)],
                )
            ],
        )

        response = await self.client.get(
            "/api/v1/services/red?project_id=1&interval=1m",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        series = response.json()["series"][0]
        assert series["operation"] is None
        assert series["points"][0]["calls"] == 3
        assert stub.last_get_service_red_request.interval == "1m"

    async def test_rejects_an_unknown_interval(self):
        token = self.make_session_token(account_id=1)

        response = await self.client.get(
            "/api/v1/services/red?project_id=1&interval=7m",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400


@pytest.mark.asyncio
class TestMetricSeriesDistributions(BaseGatewayTest):
    async def test_open_bucket_edges_become_null_and_exemplars_pass_through(self):
        token = self.make_session_token(account_id=1)
        self.get_mock_query_stub().query_metric_series_response = (
            query_pb2.QueryMetricSeriesResponse(
                project_id=1,
                name="latency",
                type=3,
                aggregation="p90",
                interval="1m",
                histograms=[
                    query_pb2.MetricHistogram(
                        buckets=[
                            query_pb2.HistogramBucket(
                                lower_bound=float("-inf"), upper_bound=10.0, count=1
                            ),
                            query_pb2.HistogramBucket(
                                lower_bound=10.0, upper_bound=float("inf"), count=2
                            ),
                        ]
                    )
                ],
                exemplars=[
                    query_pb2.MetricExemplar(
                        value=812.0, timestamp="2026-10-09T10:00:00+00:00", trace_id="a" * 32
                    )
                ],
            )
        )

        response = await self.client.get(
            "/api/v1/metrics/latency/series?project_id=1&aggregation=p90",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["type"] == "exponential_histogram"
        buckets = body["histograms"][0]["buckets"]
        assert (buckets[0]["lower_bound"], buckets[-1]["upper_bound"]) == (None, None)
        assert body["exemplars"] == [
            {
                "tags": {},
                "value": 812.0,
                "timestamp": "2026-10-09T10:00:00+00:00",
                "trace_id": "a" * 32,
                "span_id": None,
            }
        ]
