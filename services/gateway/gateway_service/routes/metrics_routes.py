import logging

import fastapi
import gateway_service.proto.query_pb2 as query_pb2
import grpc
from gateway_service import dependencies
from pydantic import BaseModel

router = fastapi.APIRouter(tags=["Metrics"])
logger = logging.getLogger(__name__)

_METRIC_TYPES = {0: "sum", 1: "gauge", 2: "histogram"}
_TEMPORALITIES = {0: "unspecified", 1: "delta", 2: "cumulative"}

_AGGREGATIONS = ("avg", "sum", "min", "max", "count", "p50", "p95", "p99")
_INTERVALS = ("1m", "5m", "1h", "1d")


class MetricNameResponse(BaseModel):
    name: str
    type: str
    temporality: str
    tag_keys: list[str]
    last_seen: str | None
    series_count: int


class ListMetricNamesResponse(BaseModel):
    project_id: int
    metrics: list[MetricNameResponse]


class MetricTagKeyResponse(BaseModel):
    key: str
    values: list[str]
    truncated: bool


class MetricTagsResponse(BaseModel):
    project_id: int
    name: str
    keys: list[MetricTagKeyResponse]


class MetricSeriesPointResponse(BaseModel):
    bucket: str
    value: float


class MetricSeriesResponse(BaseModel):
    tags: dict[str, str]
    points: list[MetricSeriesPointResponse]


class HistogramBucketResponse(BaseModel):
    upper_bound: float | None
    count: float


class MetricHistogramResponse(BaseModel):
    tags: dict[str, str]
    buckets: list[HistogramBucketResponse]
    count: int
    sum: float


class MetricSeriesQueryResponse(BaseModel):
    project_id: int
    name: str
    type: str
    temporality: str
    aggregation: str
    interval: str
    series: list[MetricSeriesResponse]
    histograms: list[MetricHistogramResponse]
    downsampled: bool
    truncated: bool


def _parse_tag_filters(raw: list[str]) -> dict[str, str]:
    """Parse repeated `tag=value` query parameters.

    A tag value may itself contain '=', so only the first one separates.
    """
    filters: dict[str, str] = {}
    for entry in raw:
        key, separator, value = entry.partition("=")
        if not separator or not key:
            raise fastapi.HTTPException(
                status_code=400,
                detail=f"Invalid tag filter {entry!r}. Expected 'key=value'.",
            )
        filters[key] = value
    return filters


@router.get(
    "/metrics/names",
    response_model=ListMetricNamesResponse,
    summary="List metric names",
    description="Metric names this project has sent, with type, temporality, "
    "tag keys and when each was last seen.",
)
async def list_metric_names(
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
    from_time: str | None = fastapi.Query(None, alias="from"),
    to_time: str | None = fastapi.Query(None, alias="to"),
) -> ListMetricNamesResponse:
    grpc_pool = request.app.state.grpc_pool

    proto_req = query_pb2.ListMetricNamesRequest(project_id=project_id)
    if from_time is not None:
        proto_req.from_time = from_time
    if to_time is not None:
        proto_req.to_time = to_time

    try:
        async with grpc_pool.get_query_stub() as stub:
            response = await stub.ListMetricNames(proto_req, timeout=10.0)
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    return ListMetricNamesResponse(
        project_id=response.project_id,
        metrics=[
            MetricNameResponse(
                name=metric.name,
                type=_METRIC_TYPES.get(metric.type, "gauge"),
                temporality=_TEMPORALITIES.get(metric.temporality, "unspecified"),
                tag_keys=list(metric.tag_keys),
                last_seen=metric.last_seen or None,
                series_count=metric.series_count,
            )
            for metric in response.metrics
        ],
    )


@router.get(
    "/metrics/{name}/tags",
    response_model=MetricTagsResponse,
    summary="List a metric's tag keys and values",
    description="Tag keys present on a metric, each with a sample of its values "
    "for the group-by and filter pickers. Values are capped per key; `truncated` "
    "marks a key whose values were cut off.",
)
async def get_metric_tags(
    request: fastapi.Request,
    name: str,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
    from_time: str | None = fastapi.Query(None, alias="from"),
    to_time: str | None = fastapi.Query(None, alias="to"),
    max_values_per_key: int = fastapi.Query(50, ge=1, le=50),
) -> MetricTagsResponse:
    grpc_pool = request.app.state.grpc_pool

    proto_req = query_pb2.GetMetricTagsRequest(
        project_id=project_id, name=name, max_values_per_key=max_values_per_key
    )
    if from_time is not None:
        proto_req.from_time = from_time
    if to_time is not None:
        proto_req.to_time = to_time

    try:
        async with grpc_pool.get_query_stub() as stub:
            response = await stub.GetMetricTags(proto_req, timeout=10.0)
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    return MetricTagsResponse(
        project_id=response.project_id,
        name=response.name,
        keys=[
            MetricTagKeyResponse(
                key=entry.key, values=list(entry.values), truncated=entry.truncated
            )
            for entry in response.keys
        ],
    )


@router.get(
    "/metrics/{name}/series",
    response_model=MetricSeriesQueryResponse,
    summary="Query a metric as a time series",
    description="Bucketed time series for one metric, optionally split by tag "
    "keys via `group_by` and narrowed by repeated `tag=key=value` filters. "
    "Cumulative counters are differenced reset-aware before aggregation, so a "
    "counter reads as activity per bucket rather than a running total. Histogram "
    "metrics also return a whole-window distribution in `histograms`.",
)
async def query_metric_series(
    request: fastapi.Request,
    name: str,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
    aggregation: str = fastapi.Query("avg"),
    group_by: list[str] = fastapi.Query([]),
    tag: list[str] = fastapi.Query([]),
    interval: str | None = fastapi.Query(None),
    from_time: str | None = fastapi.Query(None, alias="from"),
    to_time: str | None = fastapi.Query(None, alias="to"),
) -> MetricSeriesQueryResponse:
    if aggregation not in _AGGREGATIONS:
        raise fastapi.HTTPException(
            status_code=400,
            detail=f"Invalid aggregation {aggregation!r}. Expected one of: "
            f"{', '.join(_AGGREGATIONS)}",
        )
    if interval is not None and interval not in _INTERVALS:
        raise fastapi.HTTPException(
            status_code=400,
            detail=f"Invalid interval {interval!r}. Expected one of: {', '.join(_INTERVALS)}",
        )

    grpc_pool = request.app.state.grpc_pool

    proto_req = query_pb2.QueryMetricSeriesRequest(
        project_id=project_id,
        name=name,
        group_by=group_by,
        aggregation=aggregation,
    )
    for key, value in _parse_tag_filters(tag).items():
        proto_req.tag_filters[key] = value
    if interval is not None:
        proto_req.interval = interval
    if from_time is not None:
        proto_req.from_time = from_time
    if to_time is not None:
        proto_req.to_time = to_time

    try:
        async with grpc_pool.get_query_stub() as stub:
            response = await stub.QueryMetricSeries(proto_req, timeout=15.0)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(status_code=400, detail=str(e.details()))
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    return MetricSeriesQueryResponse(
        project_id=response.project_id,
        name=response.name,
        type=_METRIC_TYPES.get(response.type, "gauge"),
        temporality=_TEMPORALITIES.get(response.temporality, "unspecified"),
        aggregation=response.aggregation,
        interval=response.interval,
        series=[
            MetricSeriesResponse(
                tags=dict(series.tags),
                points=[
                    MetricSeriesPointResponse(bucket=point.bucket, value=point.value)
                    for point in series.points
                ],
            )
            for series in response.series
        ],
        histograms=[
            MetricHistogramResponse(
                tags=dict(histogram.tags),
                buckets=[
                    HistogramBucketResponse(
                        # JSON has no infinity; the OTLP overflow bucket's open
                        # upper edge becomes null rather than an invalid literal.
                        upper_bound=None if bucket.upper_bound == float("inf") else bucket.upper_bound,
                        count=bucket.count,
                    )
                    for bucket in histogram.buckets
                ],
                count=histogram.count,
                sum=histogram.sum,
            )
            for histogram in response.histograms
        ],
        downsampled=response.downsampled,
        truncated=response.truncated,
    )
