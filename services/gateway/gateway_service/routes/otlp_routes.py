import logging
import typing

import fastapi
import grpc
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

import gateway_service.config as config
import gateway_service.proto.ingestion_pb2 as ingestion_pb2
import gateway_service.services.otlp_translator as otlp_translator
import gateway_service.services.self_monitoring as self_monitoring

router = fastapi.APIRouter(tags=["OTLP"])
logger = logging.getLogger(__name__)

# Mirrors ingestion_service.config.MAX_BATCH_LOGS: the ingestion service refuses
# a single gRPC batch larger than this, so oversized exports are split here
# rather than rejected. OTel exporters treat a 4xx as non-retryable and drop the
# payload, so returning an error for a large-but-valid batch is silent data loss.
_MAX_ITEMS_PER_GRPC_BATCH = 1000

# Absurdity guard only - a single export this large is a malformed or hostile
# payload, not a tuned exporter. The body is already fully decompressed in
# memory by the time we get here.
_MAX_ITEMS_PER_REQUEST = 100_000

_SUPPORTED_CONTENT_TYPES = ("application/x-protobuf", "application/json")


class _Signal(typing.NamedTuple):
    """Everything that differs between the three OTLP signal endpoints."""

    name: str
    decode: typing.Callable
    translate: typing.Callable
    quota_state_attr: str
    build_grpc_request: typing.Callable
    grpc_method_name: str
    rejected_of: typing.Callable
    new_response: typing.Callable
    set_partial_success: typing.Callable


async def _consume_daily_quota(
    request: fastapi.Request, project_id: int, item_count: int, signal: str, quota: int
) -> str | None:
    """Atomically reserve `item_count` against the project's daily quota for `signal`.

    Returns an error message if the batch should be rejected, or None if accepted.
    Reserving before the gRPC call (rather than incrementing after accept) closes
    the race where concurrent bursts could overshoot the daily quota by a full
    request. Each signal draws on its own counter, so a burst on one can't starve
    the others.

    Request-rate limiting is deliberately not done here: RateLimitMiddleware
    already applies the project's per-minute/per-hour request budget to these
    paths. Doing a second, item-weighted check against the same configured
    numbers would spend a requests-per-minute allowance in units of log records.
    Item volume is governed by this daily quota.
    """
    redis = request.app.state.redis_client

    quota_allowed, usage = await redis.try_consume_quota(project_id, signal, item_count, quota)
    if not quota_allowed:
        logger.warning(
            f"Project {project_id} daily {signal} quota exceeded, rejecting {item_count} items "
            f"({usage}/{quota})"
        )
        return f"Daily {signal} quota exceeded ({usage}/{quota})"

    return None


def _http_error_for(rpc_error: grpc.RpcError, signal: str) -> fastapi.HTTPException:
    if rpc_error.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
        return fastapi.HTTPException(
            status_code=503,
            detail="Service temporarily unavailable - queue full",
            headers={"Retry-After": "60"},
        )
    if rpc_error.code() == grpc.StatusCode.INVALID_ARGUMENT:
        return fastapi.HTTPException(status_code=400, detail=rpc_error.details())

    logger.error(
        f"gRPC error during {signal} ingestion: {rpc_error.code()} - {rpc_error.details()}"
    )
    return fastapi.HTTPException(status_code=500, detail=f"Failed to ingest {signal}")


async def _forward_in_chunks(
    request: fastapi.Request,
    project_id: int,
    translated: otlp_translator.Translated,
    signal: _Signal,
) -> tuple[int, int, list[str]]:
    """Send `items` to the ingestion service in batches it will accept.

    Returns (rejected count, unsent count, per-chunk detail messages). A chunk
    that fails outright raises, unless earlier chunks already landed -
    re-raising then would make the exporter resend data that is already
    stored, so the remainder is reported as rejected via OTLP partial_success
    instead. `unsent` is the part of that remainder that never reached the
    ingestion service.
    """
    grpc_pool = request.app.state.grpc_pool
    items = translated.items
    rejected = 0
    sent = 0
    details: list[str] = []

    for start in range(0, len(items), _MAX_ITEMS_PER_GRPC_BATCH):
        chunk = items[start : start + _MAX_ITEMS_PER_GRPC_BATCH]

        try:
            async with grpc_pool.get_ingestion_stub() as stub:
                method = getattr(stub, signal.grpc_method_name)
                response = await method(
                    signal.build_grpc_request(project_id, chunk, translated.resources),
                    timeout=config.settings.GRPC_TIMEOUT,
                )
        except grpc.RpcError as e:
            if sent == 0:
                raise _http_error_for(e, signal.name)

            logger.error(
                f"gRPC error after {sent} {signal.name} already accepted for project "
                f"{project_id}; reporting the remaining {len(items) - sent} as rejected: "
                f"{e.code()} - {e.details()}"
            )
            details.append(f"ingestion unavailable after {sent} accepted")
            unsent = len(items) - sent
            return rejected + unsent, unsent, details

        rejected += signal.rejected_of(response)
        if response.HasField("error") and response.error:
            details.append(response.error)
        sent += len(chunk)

    return rejected, 0, details


async def _export(request: fastapi.Request, signal: _Signal) -> fastapi.Response:
    content_type = otlp_translator.normalize_content_type(request.headers.get("content-type"))
    if content_type not in _SUPPORTED_CONTENT_TYPES:
        raise fastapi.HTTPException(
            status_code=415,
            detail="Unsupported content type, use application/x-protobuf or application/json",
        )

    body = await request.body()

    try:
        otlp_request = signal.decode(body, content_type)
    except otlp_translator.TranslationError as e:
        raise fastapi.HTTPException(status_code=400, detail=str(e))

    translated = signal.translate(otlp_request)
    items = translated.items

    if len(items) > _MAX_ITEMS_PER_REQUEST:
        raise fastapi.HTTPException(
            status_code=413,
            detail=f"Export exceeds the maximum of {_MAX_ITEMS_PER_REQUEST} items per request",
        )

    rejected = 0
    error_message = ""

    if items:
        project_id = request.state.project_id
        quota_error = await _consume_daily_quota(
            request,
            project_id,
            len(items),
            signal.name,
            getattr(request.state, signal.quota_state_attr),
        )

        if quota_error is not None:
            rejected = len(items)
            error_message = quota_error
            _count_items(signal, "quota", rejected)
        else:
            redis = request.app.state.redis_client
            # Items that never reached ingestion give their reservation back:
            # the exporter retries a 503, and an outage would otherwise burn the
            # day's quota on data that was never stored.
            try:
                rejected, unsent, details = await _forward_in_chunks(
                    request, project_id, translated, signal
                )
            except fastapi.HTTPException:
                await redis.refund_quota(project_id, signal.name, len(items))
                _count_items(signal, "unavailable", len(items))
                raise
            if unsent:
                await redis.refund_quota(project_id, signal.name, unsent)
            if rejected:
                error_message = "; ".join(details) or (
                    f"{rejected} of {len(items)} {signal.name} rejected"
                )
            _count_items(signal, "accepted", len(items) - rejected)
            _count_items(signal, "rejected", rejected)

    response_proto = signal.new_response()
    if rejected:
        signal.set_partial_success(response_proto, rejected, error_message)

    return fastapi.Response(
        content=otlp_translator.encode_export_response(response_proto, content_type),
        media_type=content_type,
        status_code=200,
    )


def _count_items(signal: _Signal, outcome: str, count: int) -> None:
    if count:
        self_monitoring.increment(
            "ledger.otlp.items", count, {"signal": signal.name, "outcome": outcome}
        )


def _set_partial_success(field_name: str) -> typing.Callable:
    def setter(response_proto, rejected: int, error_message: str) -> None:
        setattr(response_proto.partial_success, field_name, rejected)
        response_proto.partial_success.error_message = error_message

    return setter


_TRACES = _Signal(
    name="spans",
    decode=otlp_translator.decode_trace_request,
    translate=otlp_translator.otlp_spans_to_proto,
    quota_state_attr="spans_daily_quota",
    build_grpc_request=lambda project_id, chunk, resources: ingestion_pb2.IngestSpansBatchRequest(
        project_id=project_id, spans=chunk, resources=resources
    ),
    grpc_method_name="IngestSpansBatch",
    rejected_of=lambda response: response.rejected,
    new_response=trace_service_pb2.ExportTraceServiceResponse,
    set_partial_success=_set_partial_success("rejected_spans"),
)

_LOGS = _Signal(
    name="logs",
    decode=otlp_translator.decode_logs_request,
    translate=otlp_translator.otlp_logs_to_proto,
    quota_state_attr="logs_daily_quota",
    build_grpc_request=lambda project_id, chunk, resources: ingestion_pb2.IngestLogBatchRequest(
        project_id=project_id, logs=chunk, resources=resources
    ),
    grpc_method_name="IngestLogBatch",
    rejected_of=lambda response: response.failed,
    new_response=logs_service_pb2.ExportLogsServiceResponse,
    set_partial_success=_set_partial_success("rejected_log_records"),
)

_METRICS = _Signal(
    name="metrics",
    decode=otlp_translator.decode_metrics_request,
    translate=otlp_translator.otlp_metrics_to_proto,
    quota_state_attr="metrics_daily_quota",
    build_grpc_request=lambda project_id, chunk, resources: (
        ingestion_pb2.IngestMetricPointsBatchRequest(
            project_id=project_id, points=chunk, resources=resources
        )
    ),
    grpc_method_name="IngestMetricPointsBatch",
    rejected_of=lambda response: response.rejected,
    new_response=metrics_service_pb2.ExportMetricsServiceResponse,
    set_partial_success=_set_partial_success("rejected_data_points"),
)


@router.post(
    "/v1/traces",
    summary="OTLP trace ingestion",
    description="Receives OTLP/HTTP trace export requests (protobuf or JSON), "
    "translated internally and stored as spans. Exports larger than the internal "
    "batch size are split automatically rather than rejected.",
)
async def export_traces(request: fastapi.Request) -> fastapi.Response:
    return await _export(request, _TRACES)


@router.post(
    "/v1/logs",
    summary="OTLP log ingestion",
    description="Receives OTLP/HTTP log export requests (protobuf or JSON), "
    "translated internally and stored as logs. Exports larger than the internal "
    "batch size are split automatically rather than rejected.",
)
async def export_logs(request: fastapi.Request) -> fastapi.Response:
    return await _export(request, _LOGS)


@router.post(
    "/v1/metrics",
    summary="OTLP metric ingestion",
    description="Receives OTLP/HTTP metric export requests (protobuf or JSON), "
    "translated internally and stored as metric points. Exports larger than the "
    "internal batch size are split automatically rather than rejected.",
)
async def export_metrics(request: fastapi.Request) -> fastapi.Response:
    return await _export(request, _METRICS)
