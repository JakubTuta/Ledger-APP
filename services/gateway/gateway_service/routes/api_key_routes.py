import asyncio
import logging

import fastapi
import gateway_service.schemas as schemas
import grpc
from gateway_service import dependencies
from gateway_service.proto import auth_pb2, auth_pb2_grpc
from gateway_service.services import grpc_pool

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(tags=["API Keys"])


# ==================== ROUTE HANDLERS ====================
# Note: Request/Response models moved to gateway_service/schemas/api_keys.py


@router.post(
    "/projects/{project_id}/api-keys",
    response_model=schemas.CreateApiKeyResponse,
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
                        "full_key": "ledger_prod_1a2b3c4d5e6f7g8h9i0j",
                        "key_prefix": "ledger_prod_1a2b",
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
        409: {
            "description": "API key name already exists",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "API key with name 'Production API Key' already exists for this project"
                    }
                }
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
    request_data: schemas.CreateApiKeyRequest = fastapi.Body(...),
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

        return schemas.CreateApiKeyResponse(
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

        elif e.code() == grpc.StatusCode.ALREADY_EXISTS:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_409_CONFLICT,
                detail=e.details(),
            )

        else:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create API key",
            )


@router.get(
    "/projects/{project_id}/api-keys",
    response_model=schemas.ListApiKeysResponse,
    summary="List API keys",
    description="Retrieve all API keys for a specific project. Shows key metadata but not the full key value.",
    response_description="List of API keys with metadata",
    responses={
        200: {
            "description": "API keys retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "api_keys": [
                            {
                                "key_id": 789,
                                "project_id": 456,
                                "name": "Production API Key",
                                "key_prefix": "ledger_prod_1a2b",
                                "status": "active",
                                "created_at": "2024-01-15T10:30:00Z",
                                "last_used_at": "2024-01-20T15:45:00Z",
                            }
                        ],
                        "total": 1,
                    }
                }
            },
        },
        403: {
            "description": "Permission denied (don't own this project)",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "You don't have permission to view API keys for this project"
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
            "content": {"application/json": {"example": {"detail": "Service timeout"}}},
        },
    },
)
async def list_api_keys(
    project_id: int = fastapi.Path(
        ..., description="Project ID to list API keys for", examples=[456]
    ),
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    List all API keys for a project.

    Returns metadata about all API keys including:
    - Key ID (for revocation)
    - Key prefix (for identification)
    - Name and creation date
    - Last used timestamp
    - Status (active/revoked)

    **IMPORTANT:** The full API key value is never returned for security.
    Only the prefix is shown for identification purposes.

    Requires JWT authentication and project ownership.
    """

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        projects_request = auth_pb2.GetProjectsRequest(account_id=account_id)
        projects_response = await asyncio.wait_for(
            stub.GetProjects(projects_request), timeout=5.0
        )

        project_ids = [p.project_id for p in projects_response.projects]
        if project_id not in project_ids:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view API keys for this project",
            )

        grpc_request = auth_pb2.ListApiKeysRequest(project_id=project_id)

        response = await asyncio.wait_for(
            stub.ListApiKeys(grpc_request),
            timeout=5.0,
        )

        api_keys = [
            schemas.ApiKeyInfo(
                key_id=key.key_id,
                project_id=key.project_id,
                name=key.name,
                key_prefix=key.key_prefix,
                status=key.status,
                created_at=key.created_at,
                last_used_at=key.last_used_at if key.last_used_at else None,
            )
            for key in response.api_keys
        ]

        return schemas.ListApiKeysResponse(api_keys=api_keys, total=len(api_keys))

    except asyncio.TimeoutError:
        logger.error("Auth Service timeout during API key listing")
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error listing API keys: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail=f"Project {project_id} not found",
            )

        elif e.code() == grpc.StatusCode.PERMISSION_DENIED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view API keys for this project",
            )

        else:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to list API keys",
            )


@router.delete(
    "/api-keys/{key_id}",
    response_model=schemas.RevokeApiKeyResponse,
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
            return schemas.RevokeApiKeyResponse(
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
