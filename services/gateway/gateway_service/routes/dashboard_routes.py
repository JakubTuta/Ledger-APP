import asyncio
import logging

import fastapi
import grpc
import pydantic
from gateway_service import dependencies
from gateway_service.proto import auth_pb2, auth_pb2_grpc
from gateway_service.services import grpc_pool

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(tags=["Dashboard"])


class PanelRequest(pydantic.BaseModel):
    name: str = pydantic.Field(
        ...,
        min_length=1,
        max_length=255,
        description="Panel display name",
        examples=["Error Rate - Last 24h"],
    )
    index: int = pydantic.Field(
        ..., ge=0, description="Panel position index", examples=[0]
    )
    project_id: str = pydantic.Field(
        ..., min_length=1, description="Project ID", examples=["456"]
    )
    time_range_from: str = pydantic.Field(
        ...,
        description="Start of time range (ISO 8601)",
        examples=["2024-01-15T00:00:00Z"],
    )
    time_range_to: str = pydantic.Field(
        ...,
        description="End of time range (ISO 8601)",
        examples=["2024-01-16T00:00:00Z"],
    )
    type: str = pydantic.Field(
        ...,
        pattern=r"^(logs|errors|metrics)$",
        description="Panel type (logs, errors, metrics)",
        examples=["errors"],
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Error Rate - Last 24h",
                "index": 0,
                "project_id": "456",
                "time_range_from": "2024-01-15T00:00:00Z",
                "time_range_to": "2024-01-16T00:00:00Z",
                "type": "errors",
            }
        }
    )


class PanelResponse(pydantic.BaseModel):
    id: str = pydantic.Field(..., description="Unique panel identifier")
    name: str = pydantic.Field(..., description="Panel display name")
    index: int = pydantic.Field(..., description="Panel position index")
    project_id: str = pydantic.Field(..., description="Associated project ID")
    time_range_from: str = pydantic.Field(..., description="Time range start")
    time_range_to: str = pydantic.Field(..., description="Time range end")
    type: str = pydantic.Field(..., description="Panel type")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "id": "panel_abc123",
                "name": "Error Rate - Last 24h",
                "index": 0,
                "project_id": "456",
                "time_range_from": "2024-01-15T00:00:00Z",
                "time_range_to": "2024-01-16T00:00:00Z",
                "type": "errors",
            }
        }
    )


class PanelListResponse(pydantic.BaseModel):
    panels: list[PanelResponse] = pydantic.Field(..., description="List of panels")
    total: int = pydantic.Field(..., description="Total number of panels")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "panels": [
                    {
                        "id": "panel_abc123",
                        "name": "Error Rate - Last 24h",
                        "index": 0,
                        "project_id": "456",
                        "time_range_from": "2024-01-15T00:00:00Z",
                        "time_range_to": "2024-01-16T00:00:00Z",
                        "type": "errors",
                    }
                ],
                "total": 1,
            }
        }
    )


class UpdatePanelRequest(pydantic.BaseModel):
    name: str = pydantic.Field(
        ...,
        min_length=1,
        max_length=255,
        description="Panel display name",
        examples=["Error Rate - Last 24h"],
    )
    index: int = pydantic.Field(
        ..., ge=0, description="Panel position index", examples=[0]
    )
    project_id: str = pydantic.Field(
        ..., min_length=1, description="Project ID", examples=["456"]
    )
    time_range_from: str = pydantic.Field(
        ...,
        description="Start of time range (ISO 8601)",
        examples=["2024-01-15T00:00:00Z"],
    )
    time_range_to: str = pydantic.Field(
        ...,
        description="End of time range (ISO 8601)",
        examples=["2024-01-16T00:00:00Z"],
    )
    type: str = pydantic.Field(
        ...,
        pattern=r"^(logs|errors|metrics)$",
        description="Panel type (logs, errors, metrics)",
        examples=["errors"],
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Error Rate - Last 24h",
                "index": 0,
                "project_id": "456",
                "time_range_from": "2024-01-15T00:00:00Z",
                "time_range_to": "2024-01-16T00:00:00Z",
                "type": "errors",
            }
        }
    )


class DeletePanelResponse(pydantic.BaseModel):
    success: bool = pydantic.Field(..., description="Whether deletion succeeded")
    message: str = pydantic.Field(..., description="Status message")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Panel panel_abc123 deleted successfully",
            }
        }
    )


@router.get(
    "/dashboard/panels",
    response_model=PanelListResponse,
    summary="Get dashboard panels",
    description="Retrieve all dashboard panels for the authenticated user",
)
async def get_dashboard_panels(
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Get all dashboard panels for the authenticated user.

    Returns:
        List of panels with their configuration
    """

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.GetDashboardPanelsRequest(user_id=account_id)

        response = await asyncio.wait_for(
            stub.GetDashboardPanels(grpc_request), timeout=5.0
        )

        panels = [
            PanelResponse(
                id=panel.id,
                name=panel.name,
                index=panel.index,
                project_id=panel.project_id,
                time_range_from=panel.time_range_from,
                time_range_to=panel.time_range_to,
                type=panel.type,
            )
            for panel in response.panels
        ]

        return PanelListResponse(panels=panels, total=len(panels))

    except asyncio.TimeoutError:
        logger.error("Auth Service timeout getting dashboard panels")
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout, please try again",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error getting dashboard panels: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail="Dashboard not found",
            )
        else:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get dashboard panels",
            )

    except Exception as e:
        logger.error(f"Unexpected error getting dashboard panels: {e}", exc_info=True)
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post(
    "/dashboard/panels",
    response_model=PanelResponse,
    status_code=fastapi.status.HTTP_201_CREATED,
    summary="Create dashboard panel",
    description="Create a new dashboard panel for the authenticated user",
)
async def create_dashboard_panel(
    request_data: PanelRequest,
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Create a new dashboard panel.

    Args:
        request_data: Panel configuration

    Returns:
        Created panel with generated ID
    """

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.CreateDashboardPanelRequest(
            user_id=account_id,
            name=request_data.name,
            index=request_data.index,
            project_id=request_data.project_id,
            time_range_from=request_data.time_range_from,
            time_range_to=request_data.time_range_to,
            type=request_data.type,
        )

        response = await asyncio.wait_for(
            stub.CreateDashboardPanel(grpc_request), timeout=5.0
        )

        if not response.panel.id:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create panel",
            )

        return PanelResponse(
            id=response.panel.id,
            name=response.panel.name,
            index=response.panel.index,
            project_id=response.panel.project_id,
            time_range_from=response.panel.time_range_from,
            time_range_to=response.panel.time_range_to,
            type=response.panel.type,
        )

    except asyncio.TimeoutError:
        logger.error("Auth Service timeout creating dashboard panel")
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout, please try again",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error creating dashboard panel: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail=e.details(),
            )
        else:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create dashboard panel",
            )

    except Exception as e:
        logger.error(f"Unexpected error creating dashboard panel: {e}", exc_info=True)
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.put(
    "/dashboard/panels/{panel_id}",
    response_model=PanelResponse,
    summary="Update dashboard panel",
    description="Update an existing dashboard panel for the authenticated user",
)
async def update_dashboard_panel(
    panel_id: str,
    request_data: UpdatePanelRequest,
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Update an existing dashboard panel.

    Args:
        panel_id: Panel ID to update
        request_data: Updated panel configuration

    Returns:
        Updated panel
    """

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.UpdateDashboardPanelRequest(
            user_id=account_id,
            panel_id=panel_id,
            name=request_data.name,
            index=request_data.index,
            project_id=request_data.project_id,
            time_range_from=request_data.time_range_from,
            time_range_to=request_data.time_range_to,
            type=request_data.type,
        )

        response = await asyncio.wait_for(
            stub.UpdateDashboardPanel(grpc_request), timeout=5.0
        )

        if not response.panel.id:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail=f"Panel {panel_id} not found",
            )

        return PanelResponse(
            id=response.panel.id,
            name=response.panel.name,
            index=response.panel.index,
            project_id=response.panel.project_id,
            time_range_from=response.panel.time_range_from,
            time_range_to=response.panel.time_range_to,
            type=response.panel.type,
        )

    except asyncio.TimeoutError:
        logger.error("Auth Service timeout updating dashboard panel")
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout, please try again",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error updating dashboard panel: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail=f"Panel {panel_id} not found",
            )
        elif e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail=e.details(),
            )
        else:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update dashboard panel",
            )

    except Exception as e:
        logger.error(f"Unexpected error updating dashboard panel: {e}", exc_info=True)
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.delete(
    "/dashboard/panels/{panel_id}",
    response_model=DeletePanelResponse,
    summary="Delete dashboard panel",
    description="Delete a dashboard panel for the authenticated user",
)
async def delete_dashboard_panel(
    panel_id: str,
    account_id: int = fastapi.Depends(dependencies.get_current_account_id),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Delete a dashboard panel.

    Args:
        panel_id: Panel ID to delete

    Returns:
        Success status
    """

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.DeleteDashboardPanelRequest(
            user_id=account_id,
            panel_id=panel_id,
        )

        response = await asyncio.wait_for(
            stub.DeleteDashboardPanel(grpc_request), timeout=5.0
        )

        if response.success:
            return DeletePanelResponse(
                success=True, message=f"Panel {panel_id} deleted successfully"
            )
        else:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail=f"Panel {panel_id} not found",
            )

    except asyncio.TimeoutError:
        logger.error("Auth Service timeout deleting dashboard panel")
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout, please try again",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error deleting dashboard panel: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail=f"Panel {panel_id} not found",
            )
        else:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete dashboard panel",
            )

    except Exception as e:
        logger.error(f"Unexpected error deleting dashboard panel: {e}", exc_info=True)
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
