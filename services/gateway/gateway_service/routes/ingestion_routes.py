import json
import logging

import fastapi
import grpc

import gateway_service.proto.ingestion_pb2 as ingestion_pb2

router = fastapi.APIRouter(tags=["ingestion"])
logger = logging.getLogger(__name__)


@router.post("/ingest/single", status_code=202)
async def ingest_single_log(log_entry: dict, request: fastapi.Request):
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


@router.post("/ingest/batch", status_code=202)
async def ingest_batch_logs(batch_request: dict, request: fastapi.Request):
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


@router.get("/queue/depth")
async def get_queue_depth_endpoint(request: fastapi.Request):
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
