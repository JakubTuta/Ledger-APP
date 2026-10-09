import logging

import fastapi
import gateway_service.proto.auth_pb2 as auth_pb2
import gateway_service.proto.auth_pb2_grpc as auth_pb2_grpc
import gateway_service.proto.query_pb2 as query_pb2
import gateway_service.schemas as schemas
import grpc
from gateway_service import dependencies

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(tags=["Dashboard"])

VALID_PERIODS = {"today", "last7days", "last30days", "currentWeek", "currentMonth", "currentYear"}

# One summary request fans out to grouped queries over every listed project.
_MAX_PROJECTS_PER_REQUEST = 100


async def _accessible_project_ids(request: fastapi.Request, account_id: int) -> set[int]:
    stub = request.app.state.grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)
    response = await stub.GetProjects(
        auth_pb2.GetProjectsRequest(account_id=account_id), timeout=5.0
    )
    return {project.project_id for project in response.projects}


@router.get(
    "/dashboard/health-summary",
    response_model=schemas.HealthSummaryResponse,
    summary="Get project health summary",
    description="Returns per-project health metrics for the HealthStrip component. Called on page mount and auto-refreshed every 60 seconds.",
)
async def get_health_summary(
    request: fastapi.Request,
    project_ids: list[str] = fastapi.Query(..., description="One or more project IDs"),
    period: str = fastapi.Query(
        "today",
        description="Time range preset: today | last7days | last30days | currentWeek | currentMonth | currentYear",
    ),
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
) -> schemas.HealthSummaryResponse:
    if period not in VALID_PERIODS:
        raise fastapi.HTTPException(
            status_code=400,
            detail=f"period must be one of: {', '.join(sorted(VALID_PERIODS))}",
        )

    if not project_ids:
        raise fastapi.HTTPException(status_code=400, detail="project_ids is required")

    if len(project_ids) > _MAX_PROJECTS_PER_REQUEST:
        raise fastapi.HTTPException(
            status_code=400,
            detail=f"At most {_MAX_PROJECTS_PER_REQUEST} project_ids per request",
        )

    try:
        int_project_ids = [int(pid) for pid in project_ids]
    except ValueError:
        raise fastapi.HTTPException(status_code=400, detail="project_ids must be numeric")

    grpc_pool = request.app.state.grpc_pool

    try:
        # Silently narrowed rather than rejected: a project the caller just left
        # may still be listed by an open dashboard, and one stale id should not
        # blank the whole health strip.
        accessible = await _accessible_project_ids(request, account_id)
        int_project_ids = [pid for pid in int_project_ids if pid in accessible]
        if not int_project_ids:
            return schemas.HealthSummaryResponse(summaries=[])

        async with grpc_pool.get_query_stub() as stub:
            response = await stub.GetHealthSummary(
                query_pb2.GetHealthSummaryRequest(
                    project_ids=[str(pid) for pid in int_project_ids],
                    period=period,
                ),
                timeout=15.0,
            )

        summaries = [
            schemas.HealthSummary(
                project_id=s.project_id,
                error_rate=s.error_rate,
                p95_ms=s.p95_ms,
                rps=s.rps,
                status=s.status,
                sparkline=list(s.sparkline),
                thresholds=schemas.HealthThresholds(
                    error_rate_warn=s.thresholds.error_rate_warn,
                    error_rate_crit=s.thresholds.error_rate_crit,
                    p95_warn_ms=s.thresholds.p95_warn_ms,
                    p95_crit_ms=s.thresholds.p95_crit_ms,
                ),
                generated_at=s.generated_at,
            )
            for s in response.summaries
        ]

        return schemas.HealthSummaryResponse(summaries=summaries)

    except grpc.RpcError as e:
        logger.error(f"gRPC error getting health summary: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(status_code=400, detail=e.details())
        raise fastapi.HTTPException(status_code=500, detail="Failed to retrieve health summary")

    except Exception as e:
        logger.error(f"Unexpected error getting health summary: {e}", exc_info=True)
        raise fastapi.HTTPException(status_code=500, detail="Internal server error")
