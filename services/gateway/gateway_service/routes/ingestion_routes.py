import json
import logging

import fastapi
import gateway_service.proto.ingestion_pb2 as ingestion_pb2
import gateway_service.schemas as schemas
import grpc

router = fastapi.APIRouter(tags=["Ingestion"])
logger = logging.getLogger(__name__)


@router.post(
    "/ingest/single",
    status_code=202,
    summary="Ingest single log",
    description="Ingest a single log entry into the project. Requires API key authentication via Authorization header.",
    response_description="Ingestion acknowledgment",
    response_model=schemas.IngestResponse,
    responses={
        400: {
            "description": "Invalid log format or validation error",
            "content": {
                "application/json": {"example": {"detail": "Invalid timestamp format"}}
            },
        },
        503: {
            "description": "Service unavailable - queue full",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Service temporarily unavailable - queue full"
                    }
                }
            },
            "headers": {
                "Retry-After": {
                    "description": "Seconds to wait before retrying",
                    "schema": {"type": "integer"},
                }
            },
        },
    },
)
async def ingest_single_log(
    log_entry: schemas.LogEntry,
    request: fastapi.Request,
) -> schemas.IngestResponse:
    """
    Ingest a single log entry.

    Accepts a log entry with temporal data, classification, content, and metadata fields.
    The log is validated and queued for asynchronous processing in Redis.

    ## Request Body

    All fields are defined in the `LogEntry` schema with full validation.

    ## Special Requirements

    - **For exception logs** (`log_type: "exception"`): `error_type` and `error_message` are required
    - **For endpoint monitoring** (`log_type: "endpoint"`): `attributes.endpoint` must include method, path, status_code, duration_ms

    ## Response

    Returns ingestion status with accepted/rejected counts.

    Requires API key authentication via `Authorization: Bearer <api-key>` header.
    """
    grpc_pool = request.app.state.grpc_pool
    project_id = request.state.project_id

    try:
        proto_log = _pydantic_to_proto_log(log_entry)

        async with grpc_pool.get_ingestion_stub() as stub:
            response = await stub.IngestLog(
                ingestion_pb2.IngestLogRequest(project_id=project_id, log=proto_log),
                timeout=5.0,
            )

        return schemas.IngestResponse(
            accepted=1,
            rejected=0,
            message=response.message,
        )

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
            raise fastapi.HTTPException(
                status_code=503,
                detail="Service temporarily unavailable - queue full",
                headers={"Retry-After": "60"},
            )
        elif e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=400,
                detail=e.details(),
            )
        else:
            logger.error(f"gRPC error during log ingestion: {e.code()} - {e.details()}")
            raise fastapi.HTTPException(
                status_code=500,
                detail="Failed to ingest log",
            )

    except Exception as e:
        logger.error(f"Failed to ingest log: {e}", exc_info=True)
        raise fastapi.HTTPException(
            status_code=500,
            detail="Failed to ingest log",
        )


@router.post(
    "/ingest/batch",
    status_code=202,
    summary="Ingest batch of logs",
    description="Ingest multiple log entries in a single request for improved throughput (max 1000 logs per batch).",
    response_description="Batch ingestion summary",
    response_model=schemas.IngestResponse,
    responses={
        400: {
            "description": "Invalid batch format or empty batch",
            "content": {
                "application/json": {
                    "example": {"detail": "Batch must contain at least one log entry"}
                }
            },
        },
        503: {
            "description": "Service unavailable - queue full",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Service temporarily unavailable - queue full"
                    }
                }
            },
            "headers": {
                "Retry-After": {
                    "description": "Seconds to wait before retrying",
                    "schema": {"type": "integer"},
                }
            },
        },
    },
)
async def ingest_batch_logs(
    batch_request: schemas.BatchLogRequest,
    request: fastapi.Request,
) -> schemas.IngestResponse:
    """
    Ingest multiple log entries in a single batch request.

    Batch ingestion provides significantly higher throughput and lower overhead
    compared to individual log ingestion requests. Recommended for processing
    large volumes of logs efficiently.

    ## Request Body

    The request must contain a `logs` array with 1-1000 log entries.
    Each log entry follows the same validation rules as single ingestion.

    ## Performance Benefits

    - **5-10x higher throughput** vs individual requests
    - **Lower latency** due to reduced network overhead
    - **Atomic validation** - all logs validated before queueing

    ## Response

    Returns detailed ingestion summary:
    - `accepted` - Number of logs successfully queued for processing
    - `rejected` - Number of logs that failed validation
    - `errors` - Array of specific error messages for debugging

    ## Error Handling

    If some logs fail validation, the response will indicate how many were
    accepted vs rejected, along with specific error messages for each failure.

    Requires API key authentication via `Authorization: Bearer <api-key>` header.
    """
    grpc_pool = request.app.state.grpc_pool
    project_id = request.state.project_id

    try:
        proto_logs = [_pydantic_to_proto_log(log) for log in batch_request.logs]

        async with grpc_pool.get_ingestion_stub() as stub:
            response = await stub.IngestLogBatch(
                ingestion_pb2.IngestLogBatchRequest(
                    project_id=project_id, logs=proto_logs
                ),
                timeout=10.0,
            )

        return schemas.IngestResponse(
            accepted=response.queued,
            rejected=response.failed,
            errors=response.error.split("; ") if response.error else None,
        )

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
            raise fastapi.HTTPException(
                status_code=503,
                detail="Service temporarily unavailable - queue full",
                headers={"Retry-After": "60"},
            )
        elif e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=400,
                detail=e.details(),
            )
        else:
            logger.error(
                f"gRPC error during batch ingestion: {e.code()} - {e.details()}"
            )
            raise fastapi.HTTPException(
                status_code=500,
                detail="Failed to ingest batch",
            )

    except Exception as e:
        logger.error(f"Failed to ingest batch: {e}", exc_info=True)
        raise fastapi.HTTPException(
            status_code=500,
            detail="Failed to ingest batch",
        )


@router.get(
    "/queue/depth",
    summary="Get queue depth",
    description="Check the current number of logs waiting to be processed in the ingestion queue for this project.",
    response_description="Queue depth information",
    response_model=schemas.QueueDepthResponse,
    responses={
        500: {
            "description": "Failed to retrieve queue depth",
            "content": {
                "application/json": {"example": {"detail": "Failed to get queue depth"}}
            },
        },
    },
)
async def get_queue_depth_endpoint(request: fastapi.Request) -> schemas.QueueDepthResponse:
    """
    Get the current ingestion queue depth for this project.

    Returns the number of log entries currently waiting in the Redis queue
    to be processed by the storage workers.

    ## Use Cases

    - **Monitoring**: Track ingestion throughput and identify bottlenecks
    - **Alerting**: Set up alerts when queue depth exceeds thresholds
    - **Capacity planning**: Understand system load and scaling needs

    ## Queue Depth Indicators

    - **0-1000**: Normal operation
    - **1000-10000**: Moderate backlog, monitor closely
    - **>10000**: High backlog, may indicate processing issues

    High queue depth may be caused by:
    - High ingestion rate exceeding processing capacity
    - Slow database write operations
    - Storage worker issues or insufficient workers

    Requires API key authentication via `Authorization: Bearer <api-key>` header.
    """
    grpc_pool = request.app.state.grpc_pool
    project_id = request.state.project_id

    try:
        async with grpc_pool.get_ingestion_stub() as stub:
            response = await stub.GetQueueDepth(
                ingestion_pb2.QueueDepthRequest(project_id=project_id),
                timeout=5.0,
            )

        return schemas.QueueDepthResponse(
            project_id=project_id,
            queue_depth=response.depth,
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error getting queue depth: {e.code()} - {e.details()}")
        raise fastapi.HTTPException(
            status_code=500,
            detail="Failed to get queue depth",
        )

    except Exception as e:
        logger.error(f"Failed to get queue depth: {e}", exc_info=True)
        raise fastapi.HTTPException(
            status_code=500,
            detail="Failed to get queue depth",
        )


def _pydantic_to_proto_log(log_entry: schemas.LogEntry) -> ingestion_pb2.LogEntry:
    """
    Convert Pydantic LogEntry model to protobuf LogEntry.

    Handles serialization of datetime and dict fields to protobuf format.
    """
    proto_log = ingestion_pb2.LogEntry(
        timestamp=log_entry.timestamp.isoformat(),
        level=log_entry.level,
        log_type=log_entry.log_type,
        importance=log_entry.importance,
    )

    if log_entry.message is not None:
        proto_log.message = log_entry.message

    if log_entry.error_type is not None:
        proto_log.error_type = log_entry.error_type

    if log_entry.error_message is not None:
        proto_log.error_message = log_entry.error_message

    if log_entry.stack_trace is not None:
        proto_log.stack_trace = log_entry.stack_trace

    if log_entry.environment is not None:
        proto_log.environment = log_entry.environment

    if log_entry.release is not None:
        proto_log.release = log_entry.release

    if log_entry.sdk_version is not None:
        proto_log.sdk_version = log_entry.sdk_version

    if log_entry.platform is not None:
        proto_log.platform = log_entry.platform

    if log_entry.platform_version is not None:
        proto_log.platform_version = log_entry.platform_version

    if log_entry.attributes is not None:
        proto_log.attributes = json.dumps(log_entry.attributes)

    return proto_log
