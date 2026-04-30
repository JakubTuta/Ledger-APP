import asyncio
import logging

import fastapi
import gateway_service.schemas as schemas
import grpc
from gateway_service import dependencies
from gateway_service.proto import auth_pb2, auth_pb2_grpc
from gateway_service.services import grpc_pool

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(tags=["Sharing"])


async def _require_project_owner(
    project_id: int,
    account_id: int,
    stub: auth_pb2_grpc.AuthServiceStub,
) -> None:
    response = await asyncio.wait_for(
        stub.GetProjectRole(
            auth_pb2.GetProjectRoleRequest(project_id=project_id, account_id=account_id)
        ),
        timeout=5.0,
    )
    if not response.is_member:
        raise fastapi.HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail="Not a member of this project")
    if response.role != "owner":
        raise fastapi.HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail="Only project owners can perform this action")


async def _require_project_member(
    project_id: int,
    account_id: int,
    stub: auth_pb2_grpc.AuthServiceStub,
) -> None:
    response = await asyncio.wait_for(
        stub.GetProjectRole(
            auth_pb2.GetProjectRoleRequest(project_id=project_id, account_id=account_id)
        ),
        timeout=5.0,
    )
    if not response.is_member:
        raise fastapi.HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail="Not a member of this project")


@router.post(
    "/projects/{project_id}/invite-code",
    response_model=schemas.GenerateInviteCodeResponse,
    status_code=fastapi.status.HTTP_201_CREATED,
    summary="Generate invite code",
    description="Generate a shareable invite code for the project. Valid for 1 hour. Owner only.",
    responses={
        201: {"description": "Invite code generated"},
        403: {"description": "Not owner of project"},
        503: {"description": "Service timeout"},
    },
)
async def generate_invite_code(
    project_id: int = fastapi.Path(..., description="Project ID"),
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        await _require_project_owner(project_id, account_id, stub)

        response = await asyncio.wait_for(
            stub.GenerateInviteCode(
                auth_pb2.GenerateInviteCodeRequest(
                    project_id=project_id,
                    requester_account_id=account_id,
                )
            ),
            timeout=5.0,
        )

        return schemas.GenerateInviteCodeResponse(
            code=response.code,
            expires_at=response.expires_at,
        )

    except fastapi.HTTPException:
        raise

    except asyncio.TimeoutError:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error generating invite code: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.PERMISSION_DENIED:
            raise fastapi.HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail=e.details())
        raise fastapi.HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate invite code")


@router.post(
    "/invitations/accept",
    response_model=schemas.AcceptInviteCodeResponse,
    status_code=fastapi.status.HTTP_200_OK,
    summary="Accept invite code",
    description="Join a project using a shareable invite code.",
    responses={
        200: {"description": "Successfully joined project"},
        400: {"description": "Invalid or expired code / already a member"},
        503: {"description": "Service timeout"},
    },
)
async def accept_invite_code(
    request_data: schemas.AcceptInviteCodeRequest,
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        response = await asyncio.wait_for(
            stub.AcceptInviteCode(
                auth_pb2.AcceptInviteCodeRequest(
                    code=request_data.code,
                    account_id=account_id,
                )
            ),
            timeout=5.0,
        )

        return schemas.AcceptInviteCodeResponse(
            project_id=response.project_id,
            role=response.role,
            project_name=response.project_name,
            project_slug=response.project_slug,
        )

    except fastapi.HTTPException:
        raise

    except asyncio.TimeoutError:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error accepting invite code: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail=e.details())
        raise fastapi.HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to accept invite code")


@router.get(
    "/projects/{project_id}/members",
    response_model=schemas.ListMembersResponse,
    summary="List project members",
    description="List all members of a project. Any member can view.",
    responses={
        200: {"description": "Members retrieved"},
        403: {"description": "Not a member of this project"},
        503: {"description": "Service timeout"},
    },
)
async def list_project_members(
    project_id: int = fastapi.Path(..., description="Project ID"),
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        await _require_project_member(project_id, account_id, stub)

        response = await asyncio.wait_for(
            stub.ListProjectMembers(
                auth_pb2.ListProjectMembersRequest(
                    project_id=project_id,
                    requester_account_id=account_id,
                )
            ),
            timeout=5.0,
        )

        members = [
            schemas.MemberInfo(
                account_id=m.account_id,
                email=m.email,
                name=m.name,
                role=m.role,
                joined_at=m.joined_at,
            )
            for m in response.members
        ]

        return schemas.ListMembersResponse(members=members, total=len(members))

    except fastapi.HTTPException:
        raise

    except asyncio.TimeoutError:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error listing project members: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.PERMISSION_DENIED:
            raise fastapi.HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail=e.details())
        raise fastapi.HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list members")


@router.delete(
    "/projects/{project_id}/members/{target_account_id}",
    response_model=schemas.RemoveMemberResponse,
    summary="Remove project member",
    description="Remove a member from the project. Owner only.",
    responses={
        200: {"description": "Member removed"},
        400: {"description": "Cannot remove self as owner"},
        403: {"description": "Not owner of project"},
        503: {"description": "Service timeout"},
    },
)
async def remove_project_member(
    project_id: int = fastapi.Path(..., description="Project ID"),
    target_account_id: int = fastapi.Path(..., description="Account ID of member to remove"),
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        await _require_project_owner(project_id, account_id, stub)

        response = await asyncio.wait_for(
            stub.RemoveProjectMember(
                auth_pb2.RemoveProjectMemberRequest(
                    project_id=project_id,
                    account_id=target_account_id,
                    requester_account_id=account_id,
                )
            ),
            timeout=5.0,
        )

        return schemas.RemoveMemberResponse(
            success=response.success,
            message=f"Member {target_account_id} removed from project",
        )

    except fastapi.HTTPException:
        raise

    except asyncio.TimeoutError:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error removing project member: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.PERMISSION_DENIED:
            raise fastapi.HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail=e.details())
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail=e.details())
        raise fastapi.HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove member")


@router.post(
    "/projects/{project_id}/leave",
    response_model=schemas.LeaveProjectResponse,
    summary="Leave project",
    description="Leave a project. Sole owners cannot leave without transferring ownership.",
    responses={
        200: {"description": "Left project"},
        400: {"description": "Cannot leave as sole owner"},
        403: {"description": "Not a member of this project"},
        503: {"description": "Service timeout"},
    },
)
async def leave_project(
    project_id: int = fastapi.Path(..., description="Project ID"),
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        response = await asyncio.wait_for(
            stub.LeaveProject(
                auth_pb2.LeaveProjectRequest(
                    project_id=project_id,
                    account_id=account_id,
                )
            ),
            timeout=5.0,
        )

        return schemas.LeaveProjectResponse(
            success=response.success,
            message=f"Left project {project_id}",
        )

    except fastapi.HTTPException:
        raise

    except asyncio.TimeoutError:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error leaving project: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail=e.details())
        raise fastapi.HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to leave project")
