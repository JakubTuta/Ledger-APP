import asyncio
import logging
import typing

import fastapi
import grpc
import pydantic
from gateway_service import dependencies
from gateway_service.proto import auth_pb2, auth_pb2_grpc
from gateway_service.services import grpc_pool

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(tags=["Projects"])


# ==================== REQUEST/RESPONSE MODELS ====================


class CreateProjectRequest(pydantic.BaseModel):
    name: str = pydantic.Field(
        ...,
        min_length=1,
        max_length=255,
        description="Project display name",
        examples=["My Production App"],
    )
    slug: str = pydantic.Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9-]+$",
        description="Unique project identifier (lowercase, alphanumeric, hyphens only)",
        examples=["my-production-app"],
    )
    environment: str = pydantic.Field(
        default="production",
        pattern=r"^(production|staging|dev)$",
        description="Deployment environment (production, staging, or dev)",
        examples=["production"],
    )

    @pydantic.field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                "Slug must contain only alphanumeric characters, hyphens, and underscores"
            )

        return v.lower()

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "name": "My Production App",
                "slug": "my-production-app",
                "environment": "production",
            }
        }
    )


class ProjectResponse(pydantic.BaseModel):
    project_id: int = pydantic.Field(..., description="Unique project identifier")
    name: str = pydantic.Field(..., description="Project display name")
    slug: str = pydantic.Field(..., description="Project slug")
    environment: str = pydantic.Field(..., description="Deployment environment")
    retention_days: int = pydantic.Field(..., description="Log retention period in days")
    daily_quota: int = pydantic.Field(..., description="Daily log ingestion quota")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": 456,
                "name": "My Production App",
                "slug": "my-production-app",
                "environment": "production",
                "retention_days": 30,
                "daily_quota": 1000000,
            }
        }
    )


class ProjectListResponse(pydantic.BaseModel):
    projects: typing.List[ProjectResponse] = pydantic.Field(
        ..., description="List of projects"
    )
    total: int = pydantic.Field(..., description="Total number of projects")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
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
    )


# ==================== ROUTE HANDLERS ====================


@router.post(
    "/projects",
    response_model=ProjectResponse,
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
    request_data: CreateProjectRequest,
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

        return ProjectResponse(
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
    response_model=ProjectListResponse,
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
            ProjectResponse(
                project_id=p.project_id,
                name=p.name,
                slug=p.slug,
                environment=p.environment,
                retention_days=p.retention_days,
                daily_quota=p.daily_quota,
            )
            for p in response.projects
        ]

        return ProjectListResponse(projects=projects, total=len(projects))

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
    response_model=ProjectResponse,
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
                return ProjectResponse(
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
