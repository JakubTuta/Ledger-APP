import json
import logging
from datetime import datetime, timedelta

import fastapi
import gateway_service.proto.query_pb2 as query_pb2
import grpc
from pydantic import BaseModel

router = fastapi.APIRouter(tags=["Tracing"])
logger = logging.getLogger(__name__)

_STATUS_MAP = {0: "UNSET", 1: "OK", 2: "ERROR"}


def _ns_to_ms(ns: int) -> float:
    return round(ns / 1_000_000, 3)


def _add_ns_to_iso(iso_str: str, duration_ns: int) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        dt_end = dt + timedelta(microseconds=duration_ns / 1000)
        return dt_end.isoformat()
    except Exception:
        return iso_str


def _parse_json_field(raw: str) -> dict | list | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


class TraceSummaryResponse(BaseModel):
    trace_id: str
    root_service: str
    root_operation: str
    start_time: str
    duration_ms: int
    span_count: int
    has_error: bool


class SpanResponse(BaseModel):
    span_id: str
    trace_id: str
    parent_span_id: str | None
    service_name: str
    name: str
    kind: int
    start_time: str
    end_time: str
    duration_ms: float
    status: str
    status_message: str
    attributes: dict | None
    events: list | None
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
    operation: str | None = fastapi.Query(None),
    min_duration_ms: int | None = fastapi.Query(None),
    has_error: bool | None = fastapi.Query(None),
    from_time: str | None = fastapi.Query(None, alias="from"),
    to_time: str | None = fastapi.Query(None, alias="to"),
    limit: int = fastapi.Query(50, ge=1, le=500),
    offset: int = fastapi.Query(0, ge=0),
) -> ListTracesResponse:
    grpc_pool = request.app.state.grpc_pool

    proto_req = query_pb2.ListTracesRequest(
        project_id=project_id,
        limit=limit,
        offset=offset,
    )
    if service is not None:
        proto_req.service = service
    if operation is not None:
        proto_req.name = operation
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
            root_service=t.service_name,
            root_operation=t.root_name,
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
            parent_span_id=s.parent_span_id or None,
            service_name=s.service_name,
            name=s.name,
            kind=s.kind,
            start_time=s.start_time,
            end_time=_add_ns_to_iso(s.start_time, s.duration_ns),
            duration_ms=_ns_to_ms(s.duration_ns),
            status=_STATUS_MAP.get(s.status_code, "UNSET"),
            status_message=s.status_message,
            attributes=_parse_json_field(s.attributes),
            events=_parse_json_field(s.events),
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
