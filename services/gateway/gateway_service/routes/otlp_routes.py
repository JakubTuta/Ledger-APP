import logging

import fastapi
import grpc
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

import gateway_service.config as config
import gateway_service.proto.ingestion_pb2 as ingestion_pb2
import gateway_service.services.otlp_translator as otlp_translator

router = fastapi.APIRouter(tags=["OTLP"])
logger = logging.getLogger(__name__)

_MAX_ITEMS = 1000
_SUPPORTED_CONTENT_TYPES = ("application/x-protobuf", "application/json")


async def _reserve_ingest_capacity(
    request: fastapi.Request, project_id: int, item_count: int
) -> str | None:
    """Atomically reserve quota/rate capacity for `item_count` items before forwarding to gRPC.

    Returns an error message if the batch should be rejected, or None if accepted.
    Reserving before the gRPC call (rather than incrementing after accept) closes the
    race where concurrent bursts could overshoot the daily quota by a full request.
    """
    redis = request.app.state.redis_client
    rate_limits = request.state.rate_limits

    rate_allowed, rate_meta = await redis.check_rate_limit(
        project_id,
        rate_limits["per_minute"],
        rate_limits["per_hour"],
        key_prefix="ingest",
        amount=item_count,
    )
    if not rate_allowed:
        raise fastapi.HTTPException(
            status_code=429,
            detail="Ingestion rate limit exceeded",
            headers={"Retry-After": "60"},
        )

    quota_allowed, usage = await redis.try_consume_quota(
        project_id, item_count, request.state.daily_quota
    )
    if not quota_allowed:
        return f"Daily quota exceeded ({usage}/{request.state.daily_quota})"

    return None


@router.post(
    "/v1/traces",
    summary="OTLP trace ingestion",
    description="Receives OTLP/HTTP trace export requests (protobuf or JSON), "
    "translated internally and stored as spans.",
)
async def export_traces(request: fastapi.Request) -> fastapi.Response:
    content_type = otlp_translator.normalize_content_type(request.headers.get("content-type"))
    if content_type not in _SUPPORTED_CONTENT_TYPES:
        raise fastapi.HTTPException(
            status_code=415,
            detail="Unsupported content type, use application/x-protobuf or application/json",
        )

    body = await request.body()

    try:
        otlp_request = otlp_translator.decode_trace_request(body, content_type)
    except otlp_translator.TranslationError as e:
        raise fastapi.HTTPException(status_code=400, detail=str(e))

    spans = otlp_translator.otlp_spans_to_proto(otlp_request)

    if len(spans) > _MAX_ITEMS:
        raise fastapi.HTTPException(
            status_code=400,
            detail=f"Batch exceeds maximum of {_MAX_ITEMS} spans",
        )

    rejected = 0
    error_message = ""

    if spans:
        grpc_pool = request.app.state.grpc_pool
        project_id = request.state.project_id

        quota_error = await _reserve_ingest_capacity(request, project_id, len(spans))
        if quota_error is not None:
            rejected = len(spans)
            error_message = quota_error
            spans = []

    if spans:
        try:
            async with grpc_pool.get_ingestion_stub() as stub:
                response = await stub.IngestSpansBatch(
                    ingestion_pb2.IngestSpansBatchRequest(project_id=project_id, spans=spans),
                    timeout=config.settings.GRPC_TIMEOUT,
                )
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
                raise fastapi.HTTPException(
                    status_code=503,
                    detail="Service temporarily unavailable - queue full",
                    headers={"Retry-After": "60"},
                )
            if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
                raise fastapi.HTTPException(status_code=400, detail=e.details())

            logger.error(f"gRPC error during span ingestion: {e.code()} - {e.details()}")
            raise fastapi.HTTPException(status_code=500, detail="Failed to ingest spans")

        rejected = response.rejected
        if rejected:
            error_message = f"{rejected} of {len(spans)} spans rejected"

    response_proto = trace_service_pb2.ExportTraceServiceResponse()
    if rejected:
        response_proto.partial_success.rejected_spans = rejected
        response_proto.partial_success.error_message = error_message

    return fastapi.Response(
        content=otlp_translator.encode_export_response(response_proto, content_type),
        media_type=content_type,
        status_code=200,
    )


@router.post(
    "/v1/logs",
    summary="OTLP log ingestion",
    description="Receives OTLP/HTTP log export requests (protobuf or JSON), "
    "translated internally and stored as logs.",
)
async def export_logs(request: fastapi.Request) -> fastapi.Response:
    content_type = otlp_translator.normalize_content_type(request.headers.get("content-type"))
    if content_type not in _SUPPORTED_CONTENT_TYPES:
        raise fastapi.HTTPException(
            status_code=415,
            detail="Unsupported content type, use application/x-protobuf or application/json",
        )

    body = await request.body()

    try:
        otlp_request = otlp_translator.decode_logs_request(body, content_type)
    except otlp_translator.TranslationError as e:
        raise fastapi.HTTPException(status_code=400, detail=str(e))

    logs = otlp_translator.otlp_logs_to_proto(otlp_request)

    if len(logs) > _MAX_ITEMS:
        raise fastapi.HTTPException(
            status_code=400,
            detail=f"Batch exceeds maximum of {_MAX_ITEMS} log records",
        )

    rejected = 0
    error_message = ""

    if logs:
        grpc_pool = request.app.state.grpc_pool
        project_id = request.state.project_id

        quota_error = await _reserve_ingest_capacity(request, project_id, len(logs))
        if quota_error is not None:
            rejected = len(logs)
            error_message = quota_error
            logs = []

    if logs:
        try:
            async with grpc_pool.get_ingestion_stub() as stub:
                response = await stub.IngestLogBatch(
                    ingestion_pb2.IngestLogBatchRequest(project_id=project_id, logs=logs),
                    timeout=config.settings.GRPC_TIMEOUT,
                )
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
                raise fastapi.HTTPException(
                    status_code=503,
                    detail="Service temporarily unavailable - queue full",
                    headers={"Retry-After": "60"},
                )
            if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
                raise fastapi.HTTPException(status_code=400, detail=e.details())

            logger.error(f"gRPC error during log ingestion: {e.code()} - {e.details()}")
            raise fastapi.HTTPException(status_code=500, detail="Failed to ingest logs")

        rejected = response.failed
        if rejected:
            error_message = response.error or f"{rejected} of {len(logs)} logs rejected"

    response_proto = logs_service_pb2.ExportLogsServiceResponse()
    if rejected:
        response_proto.partial_success.rejected_log_records = rejected
        response_proto.partial_success.error_message = error_message

    return fastapi.Response(
        content=otlp_translator.encode_export_response(response_proto, content_type),
        media_type=content_type,
        status_code=200,
    )


@router.post(
    "/v1/metrics",
    summary="OTLP metric ingestion",
    description="Receives OTLP/HTTP metric export requests (protobuf or JSON), "
    "translated internally and stored as metric points.",
)
async def export_metrics(request: fastapi.Request) -> fastapi.Response:
    content_type = otlp_translator.normalize_content_type(request.headers.get("content-type"))
    if content_type not in _SUPPORTED_CONTENT_TYPES:
        raise fastapi.HTTPException(
            status_code=415,
            detail="Unsupported content type, use application/x-protobuf or application/json",
        )

    body = await request.body()

    try:
        otlp_request = otlp_translator.decode_metrics_request(body, content_type)
    except otlp_translator.TranslationError as e:
        raise fastapi.HTTPException(status_code=400, detail=str(e))

    points = otlp_translator.otlp_metrics_to_proto(otlp_request)

    if len(points) > _MAX_ITEMS:
        raise fastapi.HTTPException(
            status_code=400,
            detail=f"Batch exceeds maximum of {_MAX_ITEMS} metric points",
        )

    rejected = 0
    error_message = ""

    if points:
        grpc_pool = request.app.state.grpc_pool
        project_id = request.state.project_id

        quota_error = await _reserve_ingest_capacity(request, project_id, len(points))
        if quota_error is not None:
            rejected = len(points)
            error_message = quota_error
            points = []

    if points:
        try:
            async with grpc_pool.get_ingestion_stub() as stub:
                response = await stub.IngestMetricPointsBatch(
                    ingestion_pb2.IngestMetricPointsBatchRequest(
                        project_id=project_id, points=points
                    ),
                    timeout=config.settings.GRPC_TIMEOUT,
                )
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
                raise fastapi.HTTPException(
                    status_code=503,
                    detail="Service temporarily unavailable - queue full",
                    headers={"Retry-After": "60"},
                )
            if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
                raise fastapi.HTTPException(status_code=400, detail=e.details())

            logger.error(f"gRPC error during metric ingestion: {e.code()} - {e.details()}")
            raise fastapi.HTTPException(status_code=500, detail="Failed to ingest metrics")

        rejected = response.rejected
        if rejected:
            error_message = f"{rejected} of {len(points)} metric points rejected"

    response_proto = metrics_service_pb2.ExportMetricsServiceResponse()
    if rejected:
        response_proto.partial_success.rejected_data_points = rejected
        response_proto.partial_success.error_message = error_message

    return fastapi.Response(
        content=otlp_translator.encode_export_response(response_proto, content_type),
        media_type=content_type,
        status_code=200,
    )
