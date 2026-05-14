import logging

import fastapi
import gateway_service.proto.ingestion_pb2 as ingestion_pb2
import grpc
from pydantic import BaseModel, Field

router = fastapi.APIRouter(tags=["Ingestion"])
logger = logging.getLogger(__name__)

_MAX_SPANS = 1000


class SpanEventRequest(BaseModel):
    name: str
    ts_unix_nano: int
    attrs: dict[str, str] = Field(default_factory=dict)


class SpanRequest(BaseModel):
    trace_id: str = Field(..., min_length=32, max_length=32)
    span_id: str = Field(..., min_length=16, max_length=16)
    parent_span_id: str = Field(default="")
    name: str
    kind: int = Field(default=0)
    start_unix_nano: int
    end_unix_nano: int
    status: int = Field(default=0)
    status_message: str = Field(default="")
    attributes: dict[str, str] = Field(default_factory=dict)
    events: list[SpanEventRequest] = Field(default_factory=list)
    service_name: str


class IngestSpansBatchRequest(BaseModel):
    spans: list[SpanRequest] = Field(..., min_length=1)


class IngestSpansBatchResponse(BaseModel):
    accepted: int
    rejected: int


@router.post(
    "/ingest/spans/batch",
    status_code=202,
    response_model=IngestSpansBatchResponse,
    summary="Ingest distributed trace spans",
)
async def ingest_spans_batch(
    payload: IngestSpansBatchRequest,
    request: fastapi.Request,
) -> IngestSpansBatchResponse:
    if len(payload.spans) > _MAX_SPANS:
        raise fastapi.HTTPException(
            status_code=400,
            detail=f"Batch exceeds maximum of {_MAX_SPANS} spans",
        )

    grpc_pool = request.app.state.grpc_pool
    project_id = request.state.project_id

    proto_spans = []
    for s in payload.spans:
        events = [
            ingestion_pb2.SpanEvent(
                name=e.name,
                ts_unix_nano=e.ts_unix_nano,
                attrs=e.attrs,
            )
            for e in s.events
        ]
        proto_spans.append(
            ingestion_pb2.Span(
                trace_id=s.trace_id.lower(),
                span_id=s.span_id.lower(),
                parent_span_id=s.parent_span_id or "",
                name=s.name,
                kind=s.kind,
                start_unix_nano=s.start_unix_nano,
                end_unix_nano=s.end_unix_nano,
                status=s.status,
                status_message=s.status_message,
                attributes=s.attributes,
                events=events,
                service_name=s.service_name,
            )
        )

    try:
        async with grpc_pool.get_ingestion_stub() as stub:
            response = await stub.IngestSpansBatch(
                ingestion_pb2.IngestSpansBatchRequest(
                    project_id=project_id, spans=proto_spans
                ),
                timeout=10.0,
            )
    except grpc.RpcError as e:
        logger.error(f"gRPC error ingesting spans: {e.code()} - {e.details()}")
        raise fastapi.HTTPException(status_code=502, detail="Failed to ingest spans")

    return IngestSpansBatchResponse(
        accepted=response.accepted, rejected=response.rejected
    )
