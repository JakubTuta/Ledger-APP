import logging
import typing

import fastapi
import gateway_service.proto.query_pb2 as query_pb2
import gateway_service.schemas as schemas
import grpc
from gateway_service import dependencies

router = fastapi.APIRouter(tags=["Error Groups"])
logger = logging.getLogger(__name__)


def _proto_to_error_group(group: "query_pb2.ErrorGroupData") -> schemas.ErrorGroupResponse:
    return schemas.ErrorGroupResponse(
        id=group.id,
        project_id=group.project_id,
        fingerprint=group.fingerprint,
        error_type=group.error_type,
        error_message=group.error_message if group.error_message else None,
        first_seen=group.first_seen,
        last_seen=group.last_seen,
        occurrence_count=group.occurrence_count,
        status=group.status,
        assigned_to=group.assigned_to if group.HasField("assigned_to") else None,
        sample_log_id=group.sample_log_id if group.HasField("sample_log_id") else None,
        resolved_at=group.resolved_at if group.HasField("resolved_at") else None,
        resolved_in_release=(
            group.resolved_in_release if group.HasField("resolved_in_release") else None
        ),
    )


@router.get(
    "/error-groups",
    status_code=200,
    summary="List error groups",
    description="Retrieve error groups for a project, optionally filtered by workflow status.",
    response_model=schemas.ErrorGroupListResponse,
)
async def list_error_groups(
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
    status: typing.Optional[
        typing.Literal["unresolved", "resolved", "ignored", "muted"]
    ] = fastapi.Query(None, description="Filter by workflow status"),
    limit: int = fastapi.Query(100, ge=1, le=1000, description="Max number of groups to return"),
    offset: int = fastapi.Query(0, ge=0, description="Number of groups to skip for pagination"),
) -> schemas.ErrorGroupListResponse:
    grpc_pool = request.app.state.grpc_pool

    try:
        req_kwargs: dict = dict(project_id=project_id, limit=limit, offset=offset)
        if status:
            req_kwargs["status"] = status

        async with grpc_pool.get_query_stub() as stub:
            response = await stub.ListErrorGroups(
                query_pb2.ListErrorGroupsRequest(**req_kwargs),
                timeout=10.0,
            )

        return schemas.ErrorGroupListResponse(
            project_id=response.project_id,
            groups=[_proto_to_error_group(g) for g in response.groups],
            total=response.total,
            has_more=response.has_more,
        )

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(status_code=400, detail=e.details())
        logger.error(f"gRPC error listing error groups: {e.code()} - {e.details()}")
        raise fastapi.HTTPException(status_code=500, detail="Failed to list error groups")

    except fastapi.HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to list error groups: {e}", exc_info=True)
        raise fastapi.HTTPException(status_code=500, detail="Failed to list error groups")


@router.get(
    "/error-groups/{group_id}",
    status_code=200,
    summary="Get error group detail",
    description="Retrieve a single error group with its sample log, stack trace, and occurrence sparkline.",
    response_model=schemas.ErrorGroupDetailResponse,
    responses={404: {"description": "Error group not found"}},
)
async def get_error_group(
    group_id: int,
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> schemas.ErrorGroupDetailResponse:
    grpc_pool = request.app.state.grpc_pool

    try:
        async with grpc_pool.get_query_stub() as stub:
            response = await stub.GetErrorGroup(
                query_pb2.GetErrorGroupRequest(project_id=project_id, group_id=group_id),
                timeout=10.0,
            )

        if not response.found:
            raise fastapi.HTTPException(status_code=404, detail="Error group not found")

        sample_log = None
        if response.HasField("sample_log"):
            log = response.sample_log
            sample_log = {
                "id": log.id,
                "project_id": log.project_id,
                "timestamp": log.timestamp,
                "ingested_at": log.ingested_at,
                "level": log.level,
                "log_type": log.log_type,
                "importance": log.importance,
                "environment": log.environment or None,
                "release": log.release or None,
                "message": log.message or None,
                "error_type": log.error_type or None,
                "error_message": log.error_message or None,
                "stack_trace": log.stack_trace or None,
                "sdk_version": log.sdk_version or None,
                "platform": log.platform or None,
                "platform_version": log.platform_version or None,
                "error_fingerprint": log.error_fingerprint or None,
                "method": log.method if log.HasField("method") else None,
                "path": log.path if log.HasField("path") else None,
                "status_code": log.status_code if log.HasField("status_code") else None,
                "duration_ms": log.duration_ms if log.HasField("duration_ms") else None,
            }

        sparkline = [
            schemas.ErrorOccurrenceBucket(bucket=b.bucket, count=b.count)
            for b in response.occurrence_sparkline
        ]

        return schemas.ErrorGroupDetailResponse(
            group=_proto_to_error_group(response.group),
            sample_stack_trace=(
                response.sample_stack_trace if response.HasField("sample_stack_trace") else None
            ),
            sample_log=sample_log,
            occurrence_sparkline=sparkline,
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error getting error group: {e.code()} - {e.details()}")
        raise fastapi.HTTPException(status_code=500, detail="Failed to retrieve error group")

    except fastapi.HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to retrieve error group: {e}", exc_info=True)
        raise fastapi.HTTPException(status_code=500, detail="Failed to retrieve error group")


@router.patch(
    "/error-groups/{group_id}/status",
    status_code=200,
    summary="Update error group status",
    description="Transition an error group's workflow status (resolve/ignore/mute/reopen).",
    response_model=schemas.ErrorGroupResponse,
    responses={404: {"description": "Error group not found"}},
)
async def update_error_group_status(
    group_id: int,
    payload: schemas.UpdateErrorGroupStatusRequest,
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> schemas.ErrorGroupResponse:
    grpc_pool = request.app.state.grpc_pool

    try:
        req_kwargs: dict = dict(project_id=project_id, group_id=group_id, status=payload.status)
        if payload.resolved_in_release:
            req_kwargs["resolved_in_release"] = payload.resolved_in_release

        async with grpc_pool.get_query_stub() as stub:
            response = await stub.UpdateErrorGroupStatus(
                query_pb2.UpdateErrorGroupStatusRequest(**req_kwargs),
                timeout=10.0,
            )

        if not response.found:
            raise fastapi.HTTPException(status_code=404, detail="Error group not found")

        return _proto_to_error_group(response.group)

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(status_code=400, detail=e.details())
        logger.error(f"gRPC error updating error group status: {e.code()} - {e.details()}")
        raise fastapi.HTTPException(status_code=500, detail="Failed to update error group status")

    except fastapi.HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to update error group status: {e}", exc_info=True)
        raise fastapi.HTTPException(status_code=500, detail="Failed to update error group status")


@router.patch(
    "/error-groups/{group_id}/assign",
    status_code=200,
    summary="Assign error group",
    description="Assign (or unassign) an error group to a project member.",
    response_model=schemas.ErrorGroupResponse,
    responses={404: {"description": "Error group not found"}},
)
async def assign_error_group(
    group_id: int,
    payload: schemas.AssignErrorGroupRequest,
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> schemas.ErrorGroupResponse:
    grpc_pool = request.app.state.grpc_pool

    try:
        req_kwargs: dict = dict(project_id=project_id, group_id=group_id)
        if payload.assigned_to is not None:
            req_kwargs["assigned_to"] = payload.assigned_to

        async with grpc_pool.get_query_stub() as stub:
            response = await stub.AssignErrorGroup(
                query_pb2.AssignErrorGroupRequest(**req_kwargs),
                timeout=10.0,
            )

        if not response.found:
            raise fastapi.HTTPException(status_code=404, detail="Error group not found")

        return _proto_to_error_group(response.group)

    except grpc.RpcError as e:
        logger.error(f"gRPC error assigning error group: {e.code()} - {e.details()}")
        raise fastapi.HTTPException(status_code=500, detail="Failed to assign error group")

    except fastapi.HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to assign error group: {e}", exc_info=True)
        raise fastapi.HTTPException(status_code=500, detail="Failed to assign error group")
