import json
import logging
from datetime import datetime, timedelta

import fastapi
import gateway_service.proto.query_pb2 as query_pb2
import gateway_service.routes.query_routes as query_routes
import gateway_service.schemas as schemas
import grpc
from gateway_service import dependencies
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


@router.get(
    "/traces",
    response_model=ListTracesResponse,
    summary="List traces",
)
async def list_traces(
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
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
    return ListTracesResponse(traces=traces, total=response.total, has_more=response.has_more)


@router.get(
    "/traces/{trace_id}",
    response_model=TraceResponse,
    summary="Get full trace",
)
async def get_trace(
    request: fastapi.Request,
    trace_id: str,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> TraceResponse:
    grpc_pool = request.app.state.grpc_pool

    try:
        async with grpc_pool.get_query_stub() as stub:
            response = await stub.GetTrace(
                query_pb2.GetTraceRequest(trace_id=trace_id, project_id=project_id),
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


class TraceLogsResponse(BaseModel):
    logs: list[schemas.LogEntryResponse]
    truncated: bool


class ServiceNodeResponse(BaseModel):
    service: str
    calls: int
    errors: int
    p95_ms: float


class ServiceEdgeResponse(BaseModel):
    caller: str
    callee: str
    calls: int
    errors: int
    p95_ms: float


class ServiceMapResponse(BaseModel):
    nodes: list[ServiceNodeResponse]
    edges: list[ServiceEdgeResponse]
    from_time: str
    to_time: str
    # Hourly rollup: p95 is the highest hourly p95 rather than the window's.
    downsampled: bool


class RedPointResponse(BaseModel):
    bucket: str
    calls: int
    errors: int
    p50_ms: float
    p95_ms: float
    p99_ms: float


class RedSeriesResponse(BaseModel):
    service: str
    operation: str | None
    calls: int
    errors: int
    p95_ms: float
    points: list[RedPointResponse]


class ServiceRedResponse(BaseModel):
    interval: str
    series: list[RedSeriesResponse]
    from_time: str
    to_time: str


_INTERVALS = ("1m", "5m", "1h", "1d")


async def _call_query(request: fastapi.Request, method: str, proto_req, timeout: float = 15.0):
    try:
        async with request.app.state.grpc_pool.get_query_stub() as stub:
            return await getattr(stub, method)(proto_req, timeout=timeout)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(status_code=400, detail=str(e.details()))
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))


@router.get(
    "/traces/{trace_id}/logs",
    response_model=TraceLogsResponse,
    summary="Logs emitted inside a trace",
    description="Logs carrying this trace id, oldest first - optionally only those "
    "emitted inside one span. Searched within the trace's own time window.",
)
async def get_trace_logs(
    request: fastapi.Request,
    trace_id: str,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
    span_id: str | None = fastapi.Query(None),
    limit: int = fastapi.Query(500, ge=1, le=2000),
) -> TraceLogsResponse:
    proto_req = query_pb2.GetTraceLogsRequest(project_id=project_id, trace_id=trace_id, limit=limit)
    if span_id is not None:
        proto_req.span_id = span_id
    response = await _call_query(request, "GetTraceLogs", proto_req)
    return TraceLogsResponse(
        logs=[query_routes.proto_to_log_response(log) for log in response.logs],
        truncated=response.truncated,
    )


@router.get(
    "/services/map",
    response_model=ServiceMapResponse,
    summary="Service dependency map",
    description="Services seen in a window (entry-span calls, errors, p95) and the "
    "calls between them, including calls into uninstrumented dependencies named "
    "by client spans (databases, third-party APIs). Window: at most 7 days, "
    "default the last hour.",
)
async def get_service_map(
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
    from_time: str | None = fastapi.Query(None, alias="from"),
    to_time: str | None = fastapi.Query(None, alias="to"),
) -> ServiceMapResponse:
    proto_req = query_pb2.GetServiceMapRequest(project_id=project_id)
    if from_time is not None:
        proto_req.from_time = from_time
    if to_time is not None:
        proto_req.to_time = to_time
    response = await _call_query(request, "GetServiceMap", proto_req)
    return ServiceMapResponse(
        nodes=[
            ServiceNodeResponse(service=n.service, calls=n.calls, errors=n.errors, p95_ms=n.p95_ms)
            for n in response.nodes
        ],
        edges=[
            ServiceEdgeResponse(
                caller=e.caller, callee=e.callee, calls=e.calls, errors=e.errors, p95_ms=e.p95_ms
            )
            for e in response.edges
        ],
        from_time=response.from_time,
        to_time=response.to_time,
        downsampled=response.downsampled,
    )


@router.get(
    "/services/red",
    response_model=ServiceRedResponse,
    summary="Rate, errors and duration per service",
    description="RED metrics from entry spans (server/consumer spans and trace "
    "roots): one series per service, or per operation when `service` is set. "
    "Window: at most 7 days, default the last hour.",
)
async def get_service_red(
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
    service: str | None = fastapi.Query(None),
    interval: str | None = fastapi.Query(None),
    from_time: str | None = fastapi.Query(None, alias="from"),
    to_time: str | None = fastapi.Query(None, alias="to"),
) -> ServiceRedResponse:
    if interval is not None and interval not in _INTERVALS:
        raise fastapi.HTTPException(
            status_code=400,
            detail=f"Invalid interval {interval!r}. Expected one of: {', '.join(_INTERVALS)}",
        )
    proto_req = query_pb2.GetServiceRedRequest(project_id=project_id)
    for field, value in (
        ("service", service),
        ("interval", interval),
        ("from_time", from_time),
        ("to_time", to_time),
    ):
        if value is not None:
            setattr(proto_req, field, value)
    response = await _call_query(request, "GetServiceRed", proto_req)
    return ServiceRedResponse(
        interval=response.interval,
        from_time=response.from_time,
        to_time=response.to_time,
        series=[
            RedSeriesResponse(
                service=s.service,
                operation=s.operation or None,
                calls=s.calls,
                errors=s.errors,
                p95_ms=s.p95_ms,
                points=[
                    RedPointResponse(
                        bucket=p.bucket,
                        calls=p.calls,
                        errors=p.errors,
                        p50_ms=p.p50_ms,
                        p95_ms=p.p95_ms,
                        p99_ms=p.p99_ms,
                    )
                    for p in s.points
                ],
            )
            for s in response.series
        ],
    )
