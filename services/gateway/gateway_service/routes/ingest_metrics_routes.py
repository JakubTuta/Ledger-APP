import logging

import fastapi
import gateway_service.proto.ingestion_pb2 as ingestion_pb2
import gateway_service.services.feature_flags as feature_flags
import grpc
from pydantic import BaseModel, Field

router = fastapi.APIRouter(tags=["Ingestion"])
logger = logging.getLogger(__name__)

_MAX_METRICS = 1000


class MetricDataPointRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    tags: str = Field(default="{}")
    ts_unix_nano: int
    type: int = Field(..., ge=1, le=3)
    count: int = Field(default=1)
    sum: float = Field(default=0.0)
    min_v: float = Field(default=0.0)
    max_v: float = Field(default=0.0)
    buckets: str = Field(default="{}")


class IngestMetricsBatchRequest(BaseModel):
    metrics: list[MetricDataPointRequest] = Field(..., min_length=1)


class IngestMetricsBatchResponse(BaseModel):
    accepted: int
    rejected: int


@router.post(
    "/ingest/metrics/batch",
    status_code=202,
    response_model=IngestMetricsBatchResponse,
    summary="Ingest custom metrics",
)
async def ingest_metrics_batch(
    payload: IngestMetricsBatchRequest,
    request: fastapi.Request,
) -> IngestMetricsBatchResponse:
    if len(payload.metrics) > _MAX_METRICS:
        raise fastapi.HTTPException(
            status_code=400,
            detail=f"Batch exceeds maximum of {_MAX_METRICS} metrics",
        )

    grpc_pool = request.app.state.grpc_pool
    project_id = request.state.project_id

    if not await feature_flags.is_feature_enabled(request, project_id, "custom_metrics"):
        return IngestMetricsBatchResponse(accepted=0, rejected=len(payload.metrics))

    proto_metrics = [
        ingestion_pb2.MetricDataPoint(
            name=m.name,
            tags=m.tags,
            ts_unix_nano=m.ts_unix_nano,
            type=m.type,
            count=m.count,
            sum=m.sum,
            min_v=m.min_v,
            max_v=m.max_v,
            buckets=m.buckets,
        )
        for m in payload.metrics
    ]

    try:
        async with grpc_pool.get_ingestion_stub() as stub:
            response = await stub.IngestMetricsBatch(
                ingestion_pb2.IngestMetricsBatchRequest(
                    project_id=project_id, metrics=proto_metrics
                ),
                timeout=10.0,
            )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
            raise fastapi.HTTPException(
                status_code=429,
                detail="Metric series cardinality limit exceeded",
            )
        logger.error(f"gRPC error ingesting metrics: {e.code()} - {e.details()}")
        raise fastapi.HTTPException(status_code=502, detail="Failed to ingest metrics")

    return IngestMetricsBatchResponse(
        accepted=response.accepted, rejected=response.rejected
    )
