import logging

import fastapi
import gateway_service.proto.query_pb2 as query_pb2
import gateway_service.services.feature_flags as feature_flags
import grpc
from pydantic import BaseModel

router = fastapi.APIRouter(tags=["Tracing"])
logger = logging.getLogger(__name__)


class TraceSummaryResponse(BaseModel):
    trace_id: str
    root_span_id: str
    root_name: str
    service_name: str
    start_time: str
    duration_ms: int
    span_count: int
    has_error: bool


class SpanResponse(BaseModel):
    span_id: str
    trace_id: str
    parent_span_id: str
    project_id: int
    service_name: str
    name: str
    kind: int
    start_time: str
    duration_ns: int
    status_code: int
    status_message: str
    attributes: str
    events: str
    error_fingerprint: str


class TraceResponse(BaseModel):
    trace_id: str
    spans: list[SpanResponse]
    duration_ms: int
    services: list[str]
    root_span_id: str


class ListTracesResponse(BaseModel):
    traces: list[TraceSummaryResponse]
    total: int
    has_more: bool


class SpanLatencyBucketResponse(BaseModel):
    service_name: str
    name: str
    bucket: str
    calls: int
    p50_ns: int
    p95_ns: int
    p99_ns: int
    errors: int


class SpanLatencyResponse(BaseModel):
    project_id: int
    data: list[SpanLatencyBucketResponse]


@router.get(
    "/metrics/span-latency",
    response_model=SpanLatencyResponse,
    summary="Get span latency percentiles",
    description="Query hourly span latency rollup (p50/p95/p99) from span_latency_1h table.",
)
async def get_span_latency(
    request: fastapi.Request,
    project_id: int = fastapi.Query(...),
    service: str | None = fastapi.Query(None),
    name: str | None = fastapi.Query(None),
    from_time: str | None = fastapi.Query(None),
    to_time: str | None = fastapi.Query(None),
) -> SpanLatencyResponse:
    await feature_flags.require_feature_enabled(request, project_id, "tracing")
    grpc_pool = request.app.state.grpc_pool

    proto_req = query_pb2.GetSpanLatencyRequest(project_id=project_id)
    if service is not None:
        proto_req.service = service
    if name is not None:
        proto_req.name = name
    if from_time is not None:
        proto_req.from_time = from_time
    if to_time is not None:
        proto_req.to_time = to_time

    try:
        async with grpc_pool.get_query_stub() as stub:
            response = await stub.GetSpanLatency(proto_req, timeout=10.0)
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    data = [
        SpanLatencyBucketResponse(
            service_name=b.service_name,
            name=b.name,
            bucket=b.bucket,
            calls=b.calls,
            p50_ns=b.p50_ns,
            p95_ns=b.p95_ns,
            p99_ns=b.p99_ns,
            errors=b.errors,
        )
        for b in response.data
    ]
    return SpanLatencyResponse(project_id=response.project_id, data=data)


@router.get(
    "/traces",
    response_model=ListTracesResponse,
    summary="List traces",
)
async def list_traces(
    request: fastapi.Request,
    project_id: int = fastapi.Query(...),
    service: str | None = fastapi.Query(None),
    name: str | None = fastapi.Query(None),
    min_duration_ms: int | None = fastapi.Query(None),
    has_error: bool | None = fastapi.Query(None),
    from_time: str | None = fastapi.Query(None),
    to_time: str | None = fastapi.Query(None),
    limit: int = fastapi.Query(50, ge=1, le=500),
    offset: int = fastapi.Query(0, ge=0),
) -> ListTracesResponse:
    await feature_flags.require_feature_enabled(request, project_id, "tracing")
    grpc_pool = request.app.state.grpc_pool

    proto_req = query_pb2.ListTracesRequest(
        project_id=project_id,
        limit=limit,
        offset=offset,
    )
    if service is not None:
        proto_req.service = service
    if name is not None:
        proto_req.name = name
    if min_duration_ms is not None:
        proto_req.min_duration_ms = min_duration_ms
    if has_error is not None:
        proto_req.has_error = has_error
    if from_time is not None:
        proto_req.from_time = from_time
    if to_time is not None:
        proto_req.to_time = to_time

    try:
        async with grpc_pool.get_query_stub() as stub:
            response = await stub.ListTraces(proto_req, timeout=10.0)
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    traces = [
        TraceSummaryResponse(
            trace_id=t.trace_id,
            root_span_id=t.root_span_id,
            root_name=t.root_name,
            service_name=t.service_name,
            start_time=t.start_time,
            duration_ms=t.duration_ms,
            span_count=t.span_count,
            has_error=t.has_error,
        )
        for t in response.traces
    ]
    return ListTracesResponse(
        traces=traces, total=response.total, has_more=response.has_more
    )


@router.get(
    "/traces/{trace_id}",
    response_model=TraceResponse,
    summary="Get full trace",
)
async def get_trace(
    request: fastapi.Request,
    trace_id: str,
    project_id: int = fastapi.Query(...),
) -> TraceResponse:
    await feature_flags.require_feature_enabled(request, project_id, "tracing")
    grpc_pool = request.app.state.grpc_pool

    try:
        async with grpc_pool.get_query_stub() as stub:
            response = await stub.GetTrace(
                query_pb2.GetTraceRequest(
                    trace_id=trace_id, project_id=project_id
                ),
                timeout=10.0,
            )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    if not response.found:
        raise fastapi.HTTPException(status_code=404, detail="Trace not found")

    spans = [
        SpanResponse(
            span_id=s.span_id,
            trace_id=s.trace_id,
            parent_span_id=s.parent_span_id,
            project_id=s.project_id,
            service_name=s.service_name,
            name=s.name,
            kind=s.kind,
            start_time=s.start_time,
            duration_ns=s.duration_ns,
            status_code=s.status_code,
            status_message=s.status_message,
            attributes=s.attributes,
            events=s.events,
            error_fingerprint=s.error_fingerprint,
        )
        for s in response.spans
    ]
    return TraceResponse(
        trace_id=response.trace_id,
        spans=spans,
        duration_ms=response.duration_ms,
        services=list(response.services),
        root_span_id=response.root_span_id,
    )
