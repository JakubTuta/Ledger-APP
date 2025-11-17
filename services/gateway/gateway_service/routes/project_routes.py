import asyncio
import datetime
import logging
import typing

import fastapi
import grpc
import gateway_service.schemas as schemas
from gateway_service import dependencies
from gateway_service.proto import auth_pb2, auth_pb2_grpc
from gateway_service.services import grpc_pool

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(tags=["Projects"])


# ==================== ROUTE HANDLERS ====================
# Note: Request/Response models moved to gateway_service/schemas/projects.py


@router.post(
    "/projects",
    response_model=schemas.ProjectResponse,
    status_code=fastapi.status.HTTP_201_CREATED,
    summary="Create new project",
    description="Create a new project for organizing and isolating logs. Each project has its own API keys, quotas, and settings.",
    response_description="Created project details",
    responses={
        201: {
            "description": "Project created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "project_id": 456,
                        "name": "My Production App",
                        "slug": "my-production-app",
                        "environment": "production",
                        "retention_days": 30,
                        "daily_quota": 1000000,
                    }
                }
            },
        },
        400: {
            "description": "Invalid input (slug format, environment value)",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Slug must contain only alphanumeric characters, hyphens, and underscores"
                    }
                }
            },
        },
        409: {
            "description": "Project slug already exists",
            "content": {
                "application/json": {
                    "example": {"detail": "Project with slug 'my-production-app' already exists"}
                }
            },
        },
        503: {
            "description": "Service timeout",
            "content": {
                "application/json": {"example": {"detail": "Service timeout, please try again"}}
            },
        },
    },
)
async def create_project(
    request_data: schemas.CreateProjectRequest,
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Create a new project for organizing logs.

    Projects provide isolation between different applications or environments.
    Each project has:
    - Unique slug identifier
    - Separate API keys
    - Individual quotas and rate limits
    - Configurable retention period

    Requires JWT authentication.
    """

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.CreateProjectRequest(
            account_id=account_id,
            name=request_data.name,
            slug=request_data.slug,
            environment=request_data.environment,
        )

        response = await asyncio.wait_for(stub.CreateProject(grpc_request), timeout=5.0)

        return schemas.ProjectResponse(
            project_id=response.project_id,
            name=response.name,
            slug=response.slug,
            environment=response.environment,
            retention_days=response.retention_days,
            daily_quota=response.daily_quota,
        )

    except asyncio.TimeoutError:
        logger.error("Auth Service timeout during project creation")
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout, please try again",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error during project creation: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.ALREADY_EXISTS:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_409_CONFLICT,
                detail=f"Project with slug '{request_data.slug}' already exists",
            )

        elif e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail=e.details()
            )

        else:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create project",
            )


@router.get(
    "/projects",
    response_model=schemas.ProjectListResponse,
    summary="List projects",
    description="Retrieve all projects owned by the authenticated account",
    response_description="List of projects with metadata",
    responses={
        200: {
            "description": "Projects retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "projects": [
                            {
                                "project_id": 456,
                                "name": "My Production App",
                                "slug": "my-production-app",
                                "environment": "production",
                                "retention_days": 30,
                                "daily_quota": 1000000,
                            }
                        ],
                        "total": 1,
                    }
                }
            },
        },
        503: {
            "description": "Service timeout",
            "content": {
                "application/json": {"example": {"detail": "Service timeout"}}
            },
        },
    },
)
async def list_projects(
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    List all projects for the authenticated account.

    Returns a list of all projects owned by the current user, including
    their configuration, quotas, and settings. Requires JWT authentication.
    """

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.GetProjectsRequest(account_id=account_id)

        response = await asyncio.wait_for(stub.GetProjects(grpc_request), timeout=5.0)

        projects = [
            schemas.ProjectResponse(
                project_id=p.project_id,
                name=p.name,
                slug=p.slug,
                environment=p.environment,
                retention_days=p.retention_days,
                daily_quota=p.daily_quota,
            )
            for p in response.projects
        ]

        return schemas.ProjectListResponse(projects=projects, total=len(projects))

    except asyncio.TimeoutError:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error listing projects: {e.code()} - {e.details()}")
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list projects",
        )


@router.get(
    "/projects/{project_slug}",
    response_model=schemas.ProjectResponse,
    summary="Get project by slug",
    description="Retrieve detailed information about a specific project using its slug identifier",
    response_description="Project details",
    responses={
        200: {
            "description": "Project found",
            "content": {
                "application/json": {
                    "example": {
                        "project_id": 456,
                        "name": "My Production App",
                        "slug": "my-production-app",
                        "environment": "production",
                        "retention_days": 30,
                        "daily_quota": 1000000,
                    }
                }
            },
        },
        404: {
            "description": "Project not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Project 'my-production-app' not found"}
                }
            },
        },
        503: {
            "description": "Service timeout",
            "content": {
                "application/json": {"example": {"detail": "Service timeout"}}
            },
        },
    },
)
async def get_project_by_slug(
    project_slug: str = fastapi.Path(..., description="Project slug identifier", examples=["my-production-app"]),
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Get project details by slug.

    Retrieves a specific project's configuration and settings using its
    unique slug identifier. Only projects owned by the authenticated
    account can be accessed. Requires JWT authentication.
    """
    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.GetProjectsRequest(account_id=account_id)

        response = await asyncio.wait_for(stub.GetProjects(grpc_request), timeout=5.0)

        for p in response.projects:
            if p.slug == project_slug:
                return schemas.ProjectResponse(
                    project_id=p.project_id,
                    name=p.name,
                    slug=p.slug,
                    environment=p.environment,
                    retention_days=p.retention_days,
                    daily_quota=p.daily_quota,
                )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_slug}' not found",
        )

    except fastapi.HTTPException:
        raise

    except asyncio.TimeoutError:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error getting project: {e.code()} - {e.details()}")
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get project",
        )


@router.get(
    "/projects/{project_id}/quota",
    response_model=schemas.ProjectQuotaResponse,
    summary="Get project quota and usage",
    description="Retrieve quota and daily usage information for a specific project. Designed for frontend dashboard display.",
    response_description="Project quota and usage details",
    responses={
        200: {
            "description": "Quota information retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "project_id": 456,
                        "project_name": "My Production App",
                        "project_slug": "my-production-app",
                        "environment": "production",
                        "daily_quota": 1000000,
                        "daily_usage": 45678,
                        "quota_remaining": 954322,
                        "quota_reset_at": "2024-01-16T00:00:00Z",
                        "retention_days": 30,
                    }
                }
            },
        },
        403: {
            "description": "Permission denied (don't own this project)",
            "content": {
                "application/json": {
                    "example": {"detail": "You don't have permission to view this project"}
                }
            },
        },
        404: {
            "description": "Project not found",
            "content": {
                "application/json": {"example": {"detail": "Project not found"}}
            },
        },
        503: {
            "description": "Service timeout",
            "content": {
                "application/json": {"example": {"detail": "Service timeout"}}
            },
        },
    },
)
async def get_project_quota(
    project_id: int = fastapi.Path(..., description="Project ID", examples=[456]),
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Get quota and usage information for a specific project.

    Returns daily quota, current usage, and remaining quota for the project.
    This endpoint is designed for frontend dashboard display and uses JWT
    authentication. The user must own the project to view its quota.

    Requires JWT authentication (Authorization: Bearer token_xxx).
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
                detail="You don't have permission to view this project",
            )

        project_response = await asyncio.wait_for(
            stub.GetProjectById(auth_pb2.GetProjectByIdRequest(project_id=project_id)),
            timeout=5.0,
        )

        usage_response = await asyncio.wait_for(
            stub.GetDailyUsage(
                auth_pb2.GetDailyUsageRequest(
                    project_id=project_id, date=datetime.date.today().isoformat()
                )
            ),
            timeout=5.0,
        )

        quota_remaining = project_response.daily_quota - usage_response.log_count
        tomorrow = datetime.datetime.now(datetime.timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + datetime.timedelta(days=1)

        return schemas.ProjectQuotaResponse(
            project_id=project_id,
            project_name=project_response.name,
            project_slug=project_response.slug,
            environment=project_response.environment,
            daily_quota=project_response.daily_quota,
            daily_usage=usage_response.log_count,
            quota_remaining=max(0, quota_remaining),
            quota_reset_at=tomorrow.isoformat(),
            retention_days=project_response.retention_days,
        )

    except fastapi.HTTPException:
        raise

    except asyncio.TimeoutError:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error getting project quota: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail="Project not found",
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get project quota",
        )
