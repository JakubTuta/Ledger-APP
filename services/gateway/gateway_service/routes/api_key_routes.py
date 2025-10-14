import asyncio
import logging

import fastapi
import grpc
import pydantic
from gateway_service import dependencies
from gateway_service.proto import auth_pb2, auth_pb2_grpc
from gateway_service.services import grpc_pool

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(tags=["API Keys"])


# ==================== REQUEST/RESPONSE MODELS ====================


class CreateApiKeyRequest(pydantic.BaseModel):
    name: str = pydantic.Field(
        ..., min_length=1, max_length=255, description="API key name"
    )


class CreateApiKeyResponse(pydantic.BaseModel):
    key_id: int
    full_key: str = pydantic.Field(
        ..., description="Complete API key (only shown once!)"
    )
    key_prefix: str = pydantic.Field(..., description="Key prefix for identification")
    warning: str = pydantic.Field(
        default="Save this key now! It will not be shown again.",
        description="Security warning",
    )


class RevokeApiKeyResponse(pydantic.BaseModel):
    success: bool
    message: str


# ==================== ROUTE HANDLERS ====================


@router.post(
    "/projects/{project_id}/api-keys",
    response_model=CreateApiKeyResponse,
    status_code=fastapi.status.HTTP_201_CREATED,
    summary="Create API key",
    description="Create a new API key for a project",
)
async def create_api_key(
    project_id: int,
    request_data: CreateApiKeyRequest,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Create a new API key for a project.

    Args:
        project_id: Project ID to create key for
        request_data: API key details
        auth: Auth context from middleware
        grpc_pool: gRPC connection pool

    Returns:
        Created API key details (full key shown once!)

    Raises:
        403: User doesn't own this project
        404: Project not found
        500: Internal server error
    """

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.CreateApiKeyRequest(
            project_id=project_id, name=request_data.name
        )

        response = await asyncio.wait_for(
            stub.CreateApiKey(grpc_request),
            timeout=10.0,
        )

        logger.info(
            f"API key created: key_id={response.key_id}, "
            f"project_id={project_id}, prefix={response.key_prefix}"
        )

        return CreateApiKeyResponse(
            key_id=response.key_id,
            full_key=response.full_key,
            key_prefix=response.key_prefix,
        )

    except asyncio.TimeoutError:
        logger.error("Auth Service timeout during API key creation")
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout, please try again",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error creating API key: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail=f"Project {project_id} not found",
            )

        elif e.code() == grpc.StatusCode.PERMISSION_DENIED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create API keys for this project",
            )

        else:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create API key",
            )


@router.delete(
    "/api-keys/{key_id}",
    response_model=RevokeApiKeyResponse,
    summary="Revoke API key",
    description="Revoke an API key (cannot be undone)",
)
async def revoke_api_key(
    key_id: int,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Revoke an API key.

    Args:
        key_id: API key ID to revoke
        auth: Auth context from middleware
        grpc_pool: gRPC connection pool
        redis: Redis client for cache invalidation

    Returns:
        Revocation status

    Raises:
        403: User doesn't own this API key
        404: API key not found
        500: Internal server error
    """

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.RevokeApiKeyRequest(key_id=key_id)

        response = await asyncio.wait_for(stub.RevokeApiKey(grpc_request), timeout=5.0)

        if response.success:
            logger.info(f"API key revoked: key_id={key_id}")

            return RevokeApiKeyResponse(
                success=True, message=f"API key {key_id} has been revoked"
            )

        else:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to revoke API key",
            )

    except asyncio.TimeoutError:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error revoking API key: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail=f"API key {key_id} not found",
            )

        elif e.code() == grpc.StatusCode.PERMISSION_DENIED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to revoke this API key",
            )

        else:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to revoke API key",
            )
