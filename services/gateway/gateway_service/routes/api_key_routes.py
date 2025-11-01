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
        ...,
        min_length=1,
        max_length=255,
        description="Descriptive name for the API key",
        examples=["Production API Key"],
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={"example": {"name": "Production API Key"}}
    )


class CreateApiKeyResponse(pydantic.BaseModel):
    key_id: int = pydantic.Field(..., description="Unique API key identifier")
    full_key: str = pydantic.Field(
        ..., description="Complete API key (only shown once!)"
    )
    key_prefix: str = pydantic.Field(..., description="Key prefix for identification")
    warning: str = pydantic.Field(
        default="Save this key now! It will not be shown again.",
        description="Security warning",
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "key_id": 789,
                "full_key": "ldg_prod_1a2b3c4d5e6f7g8h9i0j",
                "key_prefix": "ldg_prod_1a2b",
                "warning": "Save this key now! It will not be shown again.",
            }
        }
    )


class RevokeApiKeyResponse(pydantic.BaseModel):
    success: bool = pydantic.Field(..., description="Whether revocation succeeded")
    message: str = pydantic.Field(..., description="Status message")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "API key 789 has been revoked",
            }
        }
    )


# ==================== ROUTE HANDLERS ====================


@router.post(
    "/projects/{project_id}/api-keys",
    response_model=CreateApiKeyResponse,
    status_code=fastapi.status.HTTP_201_CREATED,
    summary="Create API key",
    description="Generate a new API key for log ingestion and project access. The full key is only shown once.",
    response_description="Created API key (save immediately!)",
    responses={
        201: {
            "description": "API key created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "key_id": 789,
                        "full_key": "ldg_prod_1a2b3c4d5e6f7g8h9i0j",
                        "key_prefix": "ldg_prod_1a2b",
                        "warning": "Save this key now! It will not be shown again.",
                    }
                }
            },
        },
        403: {
            "description": "Permission denied (don't own this project)",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "You don't have permission to create API keys for this project"
                    }
                }
            },
        },
        404: {
            "description": "Project not found",
            "content": {
                "application/json": {"example": {"detail": "Project 456 not found"}}
            },
        },
        503: {
            "description": "Service timeout",
            "content": {
                "application/json": {
                    "example": {"detail": "Service timeout, please try again"}
                }
            },
        },
    },
)
async def create_api_key(
    project_id: int = fastapi.Path(
        ..., description="Project ID to create API key for", examples=[456]
    ),
    request_data: CreateApiKeyRequest = fastapi.Body(...),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Create a new API key for a project.

    **IMPORTANT:** The full API key is only shown once in the response.
    Save it securely - it cannot be retrieved again.

    API keys are used for:
    - Log ingestion via /api/v1/ingest endpoints
    - Accessing project-specific endpoints
    - SDK authentication

    Include the key in requests using the `X-API-Key` header.

    Requires JWT authentication.
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
    description="Permanently revoke an API key. This action cannot be undone and the key will immediately stop working.",
    response_description="Revocation confirmation",
    responses={
        200: {
            "description": "API key revoked successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "API key 789 has been revoked",
                    }
                }
            },
        },
        403: {
            "description": "Permission denied (don't own this API key)",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "You don't have permission to revoke this API key"
                    }
                }
            },
        },
        404: {
            "description": "API key not found",
            "content": {
                "application/json": {"example": {"detail": "API key 789 not found"}}
            },
        },
        503: {
            "description": "Service timeout",
            "content": {"application/json": {"example": {"detail": "Service timeout"}}},
        },
    },
)
async def revoke_api_key(
    key_id: int = fastapi.Path(..., description="API key ID to revoke", examples=[789]),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Permanently revoke an API key.

    Once revoked, the API key will immediately stop working and cannot be
    restored. Any requests using the revoked key will receive 401 Unauthorized.

    This is useful for:
    - Rotating compromised keys
    - Removing access for decommissioned services
    - Cleaning up unused keys

    Requires JWT authentication.
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
