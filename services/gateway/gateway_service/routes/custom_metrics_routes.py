import logging

import fastapi
import gateway_service.proto.query_pb2 as query_pb2
import grpc
from pydantic import BaseModel

router = fastapi.APIRouter(tags=["Custom Metrics"])
logger = logging.getLogger(__name__)


class MetricDataPointResponse(BaseModel):
    bucket: str
    value: float


class QueryCustomMetricsResponse(BaseModel):
    project_id: int
    name: str
    agg: str
    data: list[MetricDataPointResponse]


class MetricTagEntryResponse(BaseModel):
    key: str
    values: list[str]


@router.get(
    "/metrics/custom",
    response_model=QueryCustomMetricsResponse,
    summary="Query custom metric time series",
)
async def query_custom_metrics(
    request: fastapi.Request,
    project_id: int = fastapi.Query(...),
    name: str = fastapi.Query(...),
    tags: str = fastapi.Query("{}"),
    from_time: str | None = fastapi.Query(None),
    to_time: str | None = fastapi.Query(None),
    agg: str = fastapi.Query("sum"),
    step_seconds: int = fastapi.Query(300, ge=60),
) -> QueryCustomMetricsResponse:
    grpc_pool = request.app.state.grpc_pool

    proto_req = query_pb2.QueryCustomMetricsRequest(
        project_id=project_id,
        name=name,
        tags=tags,
        agg=agg,
        step_seconds=step_seconds,
    )
    if from_time:
        proto_req.from_time = from_time
    if to_time:
        proto_req.to_time = to_time

    try:
        async with grpc_pool.get_query_stub() as stub:
            response = await stub.QueryCustomMetrics(proto_req, timeout=10.0)
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    return QueryCustomMetricsResponse(
        project_id=response.project_id,
        name=response.name,
        agg=response.agg,
        data=[
            MetricDataPointResponse(bucket=p.bucket, value=p.value)
            for p in response.data
        ],
    )


@router.get(
    "/metrics/custom/names",
    response_model=list[str],
    summary="List custom metric names for a project",
)
async def list_metric_names(
    request: fastapi.Request,
    project_id: int = fastapi.Query(...),
    prefix: str | None = fastapi.Query(None),
) -> list[str]:
    grpc_pool = request.app.state.grpc_pool

    proto_req = query_pb2.ListCustomMetricNamesRequest(project_id=project_id)
    if prefix:
        proto_req.prefix = prefix

    try:
        async with grpc_pool.get_query_stub() as stub:
            response = await stub.ListCustomMetricNames(proto_req, timeout=5.0)
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    return list(response.names)


@router.get(
    "/metrics/custom/tags",
    response_model=list[MetricTagEntryResponse],
    summary="List tag keys/values for a custom metric",
)
async def list_metric_tags(
    request: fastapi.Request,
    project_id: int = fastapi.Query(...),
    name: str = fastapi.Query(...),
) -> list[MetricTagEntryResponse]:
    grpc_pool = request.app.state.grpc_pool

    try:
        async with grpc_pool.get_query_stub() as stub:
            response = await stub.ListCustomMetricTags(
                query_pb2.ListCustomMetricTagsRequest(
                    project_id=project_id, name=name
                ),
                timeout=5.0,
            )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    return [
        MetricTagEntryResponse(key=t.key, values=list(t.values))
        for t in response.tags
    ]
