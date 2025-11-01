import json
import logging

import fastapi
import grpc

import gateway_service.proto.ingestion_pb2 as ingestion_pb2

router = fastapi.APIRouter(tags=["Ingestion"])
logger = logging.getLogger(__name__)


@router.post(
    "/ingest/single",
    status_code=202,
    summary="Ingest single log",
    description="Ingest a single log entry into the project. Requires API key authentication via X-API-Key header.",
    response_description="Ingestion acknowledgment",
    responses={
        202: {
            "description": "Log accepted for processing",
            "content": {
                "application/json": {
                    "example": {
                        "accepted": 1,
                        "rejected": 0,
                        "message": "Log queued successfully",
                    }
                }
            },
        },
        400: {
            "description": "Invalid log format or validation error",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid timestamp format"}
                }
            },
        },
        503: {
            "description": "Service unavailable - queue full",
            "content": {
                "application/json": {
                    "example": {"detail": "Service temporarily unavailable - queue full"}
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
async def ingest_single_log(log_entry: dict, request: fastapi.Request):
    """
    Ingest a single log entry.

    Accepts a log entry with fields like timestamp, level, message, error details,
    and custom attributes. The log is validated and queued for asynchronous processing.

    **Required fields:**
    - `timestamp` (ISO 8601 format)
    - `level` (debug, info, warning, error, critical)

    **Optional fields:**
    - `message` - Log message (max 10,000 chars)
    - `log_type` - Type of log (console, logger, exception, custom)
    - `error_type` - Error class name
    - `error_message` - Error description
    - `stack_trace` - Full stack trace
    - `attributes` - Custom JSON attributes (max 100KB)
    - `environment`, `release`, `sdk_version`, `platform`

    Requires API key authentication via `X-API-Key` header.
    """
    grpc_pool = request.app.state.grpc_pool
    project_id = request.state.project_id

    try:
        proto_log = _dict_to_proto_log(log_entry)

        async with grpc_pool.get_ingestion_stub() as stub:
            response = await stub.IngestLog(
                ingestion_pb2.IngestLogRequest(project_id=project_id, log=proto_log),
                timeout=5.0,
            )

        return {"accepted": 1, "rejected": 0, "message": response.message}

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
    responses={
        202: {
            "description": "Batch accepted for processing",
            "content": {
                "application/json": {
                    "example": {
                        "accepted": 100,
                        "rejected": 0,
                        "errors": None,
                    }
                }
            },
        },
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
                    "example": {"detail": "Service temporarily unavailable - queue full"}
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
async def ingest_batch_logs(batch_request: dict, request: fastapi.Request):
    """
    Ingest multiple log entries in a single batch request.

    Batch ingestion provides higher throughput and lower overhead compared
    to individual requests. Ideal for processing large volumes of logs.

    **Request format:**
    ```json
    {
      "logs": [
        {
          "timestamp": "2024-01-15T10:30:00Z",
          "level": "error",
          "message": "Application error occurred",
          ...
        },
        ...
      ]
    }
    ```

    **Limits:**
    - Maximum 1000 logs per batch
    - Each log follows the same validation as single ingestion

    **Response:**
    - `accepted` - Number of logs successfully queued
    - `rejected` - Number of logs that failed validation
    - `errors` - Array of error messages for rejected logs

    Requires API key authentication via `X-API-Key` header.
    """
    grpc_pool = request.app.state.grpc_pool
    project_id = request.state.project_id

    logs = batch_request.get("logs", [])
    if not logs:
        raise fastapi.HTTPException(
            status_code=400,
            detail="Batch must contain at least one log entry",
        )

    try:
        proto_logs = [_dict_to_proto_log(log) for log in logs]

        async with grpc_pool.get_ingestion_stub() as stub:
            response = await stub.IngestLogBatch(
                ingestion_pb2.IngestLogBatchRequest(
                    project_id=project_id, logs=proto_logs
                ),
                timeout=10.0,
            )

        return {
            "accepted": response.queued,
            "rejected": response.failed,
            "errors": response.error.split("; ") if response.error else None,
        }

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
            logger.error(f"gRPC error during batch ingestion: {e.code()} - {e.details()}")
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
    responses={
        200: {
            "description": "Queue depth retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "project_id": 456,
                        "queue_depth": 1234,
                    }
                }
            },
        },
        500: {
            "description": "Failed to retrieve queue depth",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to get queue depth"}
                }
            },
        },
    },
)
async def get_queue_depth_endpoint(request: fastapi.Request):
    """
    Get the current ingestion queue depth for this project.

    Returns the number of log entries currently waiting in the Redis queue
    to be processed by the storage workers. High queue depth may indicate:
    - High ingestion rate
    - Slow storage processing
    - Potential backlog issues

    Useful for monitoring and alerting on ingestion performance.

    Requires API key authentication via `X-API-Key` header.
    """
    grpc_pool = request.app.state.grpc_pool
    project_id = request.state.project_id

    try:
        async with grpc_pool.get_ingestion_stub() as stub:
            response = await stub.GetQueueDepth(
                ingestion_pb2.QueueDepthRequest(project_id=project_id),
                timeout=5.0,
            )

        return {"project_id": project_id, "queue_depth": response.depth}

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


def _dict_to_proto_log(log_dict: dict) -> ingestion_pb2.LogEntry:
    proto_log = ingestion_pb2.LogEntry(
        timestamp=log_dict.get("timestamp", ""),
        level=log_dict.get("level", "info"),
        log_type=log_dict.get("log_type", "logger"),
        importance=log_dict.get("importance", "standard"),
    )

    if "message" in log_dict and log_dict["message"] is not None:
        proto_log.message = log_dict["message"]

    if "error_type" in log_dict and log_dict["error_type"] is not None:
        proto_log.error_type = log_dict["error_type"]

    if "error_message" in log_dict and log_dict["error_message"] is not None:
        proto_log.error_message = log_dict["error_message"]

    if "stack_trace" in log_dict and log_dict["stack_trace"] is not None:
        proto_log.stack_trace = log_dict["stack_trace"]

    if "environment" in log_dict and log_dict["environment"] is not None:
        proto_log.environment = log_dict["environment"]

    if "release" in log_dict and log_dict["release"] is not None:
        proto_log.release = log_dict["release"]

    if "sdk_version" in log_dict and log_dict["sdk_version"] is not None:
        proto_log.sdk_version = log_dict["sdk_version"]

    if "platform" in log_dict and log_dict["platform"] is not None:
        proto_log.platform = log_dict["platform"]

    if "platform_version" in log_dict and log_dict["platform_version"] is not None:
        proto_log.platform_version = log_dict["platform_version"]

    if "attributes" in log_dict and log_dict["attributes"] is not None:
        proto_log.attributes = json.dumps(log_dict["attributes"])

    return proto_log
