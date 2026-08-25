import grpc
import pytest
from gateway_service.proto import auth_pb2, query_pb2

from .test_base import BaseGatewayTest


def _member_project() -> auth_pb2.GetProjectsResponse:
    return auth_pb2.GetProjectsResponse(
        projects=[
            auth_pb2.ProjectInfo(
                project_id=1,
                name="My Project",
                slug="my-project",
                environment="production",
                retention_days=30,
                logs_daily_quota=100000,
                spans_daily_quota=300000,
                metrics_daily_quota=100000,
            ),
        ]
    )


@pytest.mark.asyncio
class TestListMetricNames(BaseGatewayTest):
    async def test_maps_type_and_temporality_to_names(self):
        session_token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_projects_response = _member_project()

        self.get_mock_query_stub().list_metric_names_response = (
            query_pb2.ListMetricNamesResponse(
                project_id=1,
                metrics=[
                    query_pb2.MetricNameInfo(
                        name="orders_processed",
                        type=0,
                        temporality=1,
                        tag_keys=["region"],
                        last_seen="2026-08-25T12:00:00+00:00",
                        series_count=3,
                    ),
                    query_pb2.MetricNameInfo(
                        name="request_duration_ms", type=2, temporality=2, series_count=1
                    ),
                ],
            )
        )

        response = await self.client.get(
            "/api/v1/metrics/names?project_id=1",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 200
        metrics = response.json()["metrics"]
        assert metrics[0]["type"] == "sum"
        assert metrics[0]["temporality"] == "delta"
        assert metrics[0]["tag_keys"] == ["region"]
        assert metrics[0]["series_count"] == 3
        assert metrics[1]["type"] == "histogram"
        assert metrics[1]["temporality"] == "cumulative"
        assert metrics[1]["last_seen"] is None

    async def test_rejects_non_member(self):
        session_token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_project_role_response = auth_pb2.GetProjectRoleResponse(
            is_member=False, role=""
        )

        response = await self.client.get(
            "/api/v1/metrics/names?project_id=1",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 403


@pytest.mark.asyncio
class TestGetMetricTags(BaseGatewayTest):
    async def test_returns_keys_and_truncation_flag(self):
        session_token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_projects_response = _member_project()

        self.get_mock_query_stub().get_metric_tags_response = query_pb2.GetMetricTagsResponse(
            project_id=1,
            name="latency",
            keys=[
                query_pb2.MetricTagKey(key="region", values=["eu", "us"], truncated=False),
                query_pb2.MetricTagKey(key="user", values=["a"], truncated=True),
            ],
        )

        response = await self.client.get(
            "/api/v1/metrics/latency/tags?project_id=1",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 200
        keys = response.json()["keys"]
        assert keys[0] == {"key": "region", "values": ["eu", "us"], "truncated": False}
        assert keys[1]["truncated"] is True


@pytest.mark.asyncio
class TestQueryMetricSeries(BaseGatewayTest):
    async def test_returns_series_points(self):
        session_token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_projects_response = _member_project()

        series = query_pb2.MetricSeries(
            points=[
                query_pb2.MetricSeriesPoint(bucket="2026-08-25T12:00:00+00:00", value=10.0),
                query_pb2.MetricSeriesPoint(bucket="2026-08-25T12:05:00+00:00", value=20.0),
            ]
        )
        series.tags["region"] = "eu"

        self.get_mock_query_stub().query_metric_series_response = (
            query_pb2.QueryMetricSeriesResponse(
                project_id=1,
                name="orders",
                type=0,
                temporality=1,
                aggregation="sum",
                interval="5m",
                series=[series],
                downsampled=True,
            )
        )

        response = await self.client.get(
            "/api/v1/metrics/orders/series?project_id=1&aggregation=sum&group_by=region",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "sum"
        assert data["temporality"] == "delta"
        assert data["interval"] == "5m"
        assert data["downsampled"] is True
        assert data["series"][0]["tags"] == {"region": "eu"}
        assert [point["value"] for point in data["series"][0]["points"]] == [10.0, 20.0]

    async def test_tag_filters_are_forwarded(self):
        session_token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_projects_response = _member_project()
        query_stub = self.get_mock_query_stub()

        response = await self.client.get(
            "/api/v1/metrics/orders/series?project_id=1&tag=region=eu&tag=route=/api/orders",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 200
        forwarded = dict(query_stub.last_query_metric_series_request.tag_filters)
        assert forwarded == {"region": "eu", "route": "/api/orders"}

    async def test_tag_value_may_contain_equals(self):
        session_token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_projects_response = _member_project()
        query_stub = self.get_mock_query_stub()

        response = await self.client.get(
            "/api/v1/metrics/orders/series?project_id=1&tag=query=a=b",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 200
        forwarded = dict(query_stub.last_query_metric_series_request.tag_filters)
        assert forwarded == {"query": "a=b"}

    async def test_malformed_tag_filter_is_rejected(self):
        session_token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_projects_response = _member_project()

        response = await self.client.get(
            "/api/v1/metrics/orders/series?project_id=1&tag=region",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 400

    async def test_invalid_aggregation_is_rejected_before_grpc(self):
        session_token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_projects_response = _member_project()
        query_stub = self.get_mock_query_stub()

        response = await self.client.get(
            "/api/v1/metrics/orders/series?project_id=1&aggregation=median",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 400
        assert query_stub.last_query_metric_series_request is None

    async def test_invalid_interval_is_rejected(self):
        session_token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_projects_response = _member_project()

        response = await self.client.get(
            "/api/v1/metrics/orders/series?project_id=1&interval=90s",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 400

    async def test_histogram_infinite_bound_serializes_as_null(self):
        session_token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_projects_response = _member_project()

        self.get_mock_query_stub().query_metric_series_response = (
            query_pb2.QueryMetricSeriesResponse(
                project_id=1,
                name="request_duration_ms",
                type=2,
                aggregation="p95",
                interval="5m",
                histograms=[
                    query_pb2.MetricHistogram(
                        buckets=[
                            query_pb2.HistogramBucket(upper_bound=10.0, count=2),
                            query_pb2.HistogramBucket(upper_bound=float("inf"), count=1),
                        ],
                        count=3,
                        sum=45.0,
                    )
                ],
            )
        )

        response = await self.client.get(
            "/api/v1/metrics/request_duration_ms/series?project_id=1&aggregation=p95",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 200
        buckets = response.json()["histograms"][0]["buckets"]
        assert buckets[0]["upper_bound"] == 10.0
        assert buckets[1]["upper_bound"] is None

    async def test_invalid_argument_from_query_service_maps_to_400(self):
        session_token = self.make_session_token(account_id=1)
        self.get_mock_auth_stub().get_projects_response = _member_project()

        error = grpc.RpcError()
        error.code = lambda: grpc.StatusCode.INVALID_ARGUMENT
        error.details = lambda: "Unsupported aggregation 'median'"
        self.get_mock_query_stub().query_metric_series_error = error

        response = await self.client.get(
            "/api/v1/metrics/orders/series?project_id=1&aggregation=avg",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 400
