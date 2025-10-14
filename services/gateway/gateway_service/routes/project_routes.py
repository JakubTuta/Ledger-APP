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
    name: str = pydantic.Field(..., min_length=1, max_length=255)
    slug: str = pydantic.Field(
        ..., min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$"
    )
    environment: str = pydantic.Field(
        default="production", pattern=r"^(production|staging|dev)$"
    )

    @pydantic.field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                "Slug must contain only alphanumeric characters, hyphens, and underscores"
            )

        return v.lower()


class ProjectResponse(pydantic.BaseModel):
    project_id: int
    name: str
    slug: str
    environment: str
    retention_days: int
    daily_quota: int


class ProjectListResponse(pydantic.BaseModel):
    projects: typing.List[ProjectResponse]
    total: int


# ==================== ROUTE HANDLERS ====================


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=fastapi.status.HTTP_201_CREATED,
    summary="Create new project",
    description="Create a new project for the authenticated account",
)
async def create_project(
    request_data: CreateProjectRequest,
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Create a new project.

    Args:
        request_data: Project details
        account_id: From auth middleware (already validated)
        grpc_pool: gRPC connection pool

    Returns:
        Created project details

    Raises:
        409: Project slug already exists
        500: Internal server error
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
    description="Get all projects for the authenticated account",
)
async def list_projects(
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    List all projects for authenticated account.

    Args:
        account_id: From auth middleware
        grpc_pool: gRPC connection pool

    Returns:
        List of projects
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
    description="Get project details by slug",
)
async def get_project_by_slug(
    project_slug: str,
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Get project by slug.

    Args:
        project_slug: Project slug
        account_id: From auth middleware
        grpc_pool: gRPC connection pool

    Returns:
        Project details

    Raises:
        404: Project not found
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
