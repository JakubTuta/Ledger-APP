import logging

import fastapi
import gateway_service.proto.ingestion_pb2 as ingestion_pb2
import gateway_service.schemas as schemas
import grpc

router = fastapi.APIRouter(tags=["Ingestion"])
logger = logging.getLogger(__name__)


@router.get(
    "/queue/depth",
    summary="Get queue depth",
    description="Check the current number of logs waiting to be processed in the ingestion queue for this project.",
    response_description="Queue depth information",
    response_model=schemas.QueueDepthResponse,
    responses={
        500: {
            "description": "Failed to retrieve queue depth",
            "content": {"application/json": {"example": {"detail": "Failed to get queue depth"}}},
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
