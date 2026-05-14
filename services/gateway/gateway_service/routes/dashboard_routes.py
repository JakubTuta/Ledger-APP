import asyncio
import json
import logging

import fastapi
import grpc
import gateway_service.schemas as schemas
from gateway_service import dependencies
from gateway_service.proto import auth_pb2, auth_pb2_grpc
from gateway_service.services import grpc_pool

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(tags=["Dashboard"])


def _panel_proto_to_response(panel) -> schemas.PanelResponse:
    panel_layout = None
    if panel.HasField("layout"):
        panel_layout = schemas.PanelLayout(
            x=panel.layout.x,
            y=panel.layout.y,
            w=panel.layout.w,
            h=panel.layout.h,
        )
    tag_filter = None
    if panel.HasField("tag_filter_json") and panel.tag_filter_json:
        try:
            tag_filter = json.loads(panel.tag_filter_json)
        except (json.JSONDecodeError, ValueError):
            pass
    return schemas.PanelResponse(
        id=panel.id,
        name=panel.name,
        index=panel.index,
        project_id=panel.project_id,
        period=panel.period if panel.HasField("period") else None,
        periodFrom=panel.periodFrom if panel.HasField("periodFrom") else None,
        periodTo=panel.periodTo if panel.HasField("periodTo") else None,
        type=panel.type,
        endpoint=panel.endpoint if panel.endpoint else None,
        routes=list(panel.routes) if panel.routes else None,
        statistic=panel.statistic if panel.statistic else None,
        layout=panel_layout,
        trace_id=panel.trace_id if panel.HasField("trace_id") else None,
        service_filter=panel.service_filter if panel.HasField("service_filter") else None,
        operation_filter=panel.operation_filter if panel.HasField("operation_filter") else None,
        min_duration_ms=panel.min_duration_ms if panel.HasField("min_duration_ms") else None,
        has_error=panel.has_error if panel.HasField("has_error") else None,
        limit=panel.limit if panel.HasField("limit") else None,
        metric_name=panel.metric_name if panel.HasField("metric_name") else None,
        tag_filter=tag_filter,
        agg=panel.agg if panel.HasField("agg") else None,
        viz=panel.viz if panel.HasField("viz") else None,
        step=panel.step if panel.HasField("step") else None,
        statusClass=panel.status_class if panel.HasField("status_class") else None,
        search=panel.logs_search if panel.HasField("logs_search") else None,
    )


# ==================== ROUTE HANDLERS ====================
# Note: Request/Response models moved to gateway_service/schemas/dashboard.py


@router.get(
    "/dashboard/panels",
    response_model=schemas.PanelListResponse,
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

        panels = [_panel_proto_to_response(panel) for panel in response.panels]

        return schemas.PanelListResponse(panels=panels, total=len(panels))

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
    response_model=schemas.PanelResponse,
    status_code=fastapi.status.HTTP_201_CREATED,
    summary="Create dashboard panel",
    description="Create a new dashboard panel for the authenticated user",
)
async def create_dashboard_panel(
    request_data: schemas.PanelRequest,
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

        grpc_request_kwargs = {
            "user_id": account_id,
            "name": request_data.name,
            "index": request_data.index,
            "project_id": request_data.project_id,
            "type": request_data.type,
            "endpoint": request_data.endpoint if request_data.endpoint else "",
            "routes": request_data.routes if request_data.routes else [],
            "statistic": request_data.statistic if request_data.statistic else "",
        }

        if request_data.period is not None:
            grpc_request_kwargs["period"] = request_data.period
        if request_data.periodFrom is not None:
            grpc_request_kwargs["periodFrom"] = request_data.periodFrom
        if request_data.periodTo is not None:
            grpc_request_kwargs["periodTo"] = request_data.periodTo
        if request_data.layout is not None:
            grpc_request_kwargs["layout"] = auth_pb2.PanelLayout(
                x=request_data.layout.x,
                y=request_data.layout.y,
                w=request_data.layout.w,
                h=request_data.layout.h,
            )
        if request_data.trace_id is not None:
            grpc_request_kwargs["trace_id"] = request_data.trace_id
        if request_data.service_filter is not None:
            grpc_request_kwargs["service_filter"] = request_data.service_filter
        if request_data.operation_filter is not None:
            grpc_request_kwargs["operation_filter"] = request_data.operation_filter
        if request_data.min_duration_ms is not None:
            grpc_request_kwargs["min_duration_ms"] = request_data.min_duration_ms
        if request_data.has_error is not None:
            grpc_request_kwargs["has_error"] = request_data.has_error
        if request_data.limit is not None:
            grpc_request_kwargs["limit"] = request_data.limit
        if request_data.metric_name is not None:
            grpc_request_kwargs["metric_name"] = request_data.metric_name
        if request_data.tag_filter is not None:
            grpc_request_kwargs["tag_filter_json"] = json.dumps(request_data.tag_filter)
        if request_data.agg is not None:
            grpc_request_kwargs["agg"] = request_data.agg
        if request_data.viz is not None:
            grpc_request_kwargs["viz"] = request_data.viz
        if request_data.step is not None:
            grpc_request_kwargs["step"] = request_data.step
        if request_data.statusClass is not None:
            grpc_request_kwargs["status_class"] = request_data.statusClass
        if request_data.search is not None:
            grpc_request_kwargs["logs_search"] = request_data.search

        grpc_request = auth_pb2.CreateDashboardPanelRequest(**grpc_request_kwargs)

        response = await asyncio.wait_for(
            stub.CreateDashboardPanel(grpc_request), timeout=5.0
        )

        if not response.panel.id:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create panel",
            )

        return _panel_proto_to_response(response.panel)

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
    response_model=schemas.PanelResponse,
    summary="Update dashboard panel",
    description="Update an existing dashboard panel for the authenticated user",
)
async def update_dashboard_panel(
    panel_id: str,
    request_data: schemas.UpdatePanelRequest,
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

        grpc_request_kwargs = {
            "user_id": account_id,
            "panel_id": panel_id,
            "name": request_data.name,
            "index": request_data.index,
            "project_id": request_data.project_id,
            "type": request_data.type,
            "endpoint": request_data.endpoint if request_data.endpoint else "",
            "routes": request_data.routes if request_data.routes else [],
            "statistic": request_data.statistic if request_data.statistic else "",
        }

        if request_data.period is not None:
            grpc_request_kwargs["period"] = request_data.period
        if request_data.periodFrom is not None:
            grpc_request_kwargs["periodFrom"] = request_data.periodFrom
        if request_data.periodTo is not None:
            grpc_request_kwargs["periodTo"] = request_data.periodTo
        if request_data.layout is not None:
            grpc_request_kwargs["layout"] = auth_pb2.PanelLayout(
                x=request_data.layout.x,
                y=request_data.layout.y,
                w=request_data.layout.w,
                h=request_data.layout.h,
            )
        if request_data.trace_id is not None:
            grpc_request_kwargs["trace_id"] = request_data.trace_id
        if request_data.service_filter is not None:
            grpc_request_kwargs["service_filter"] = request_data.service_filter
        if request_data.operation_filter is not None:
            grpc_request_kwargs["operation_filter"] = request_data.operation_filter
        if request_data.min_duration_ms is not None:
            grpc_request_kwargs["min_duration_ms"] = request_data.min_duration_ms
        if request_data.has_error is not None:
            grpc_request_kwargs["has_error"] = request_data.has_error
        if request_data.limit is not None:
            grpc_request_kwargs["limit"] = request_data.limit
        if request_data.metric_name is not None:
            grpc_request_kwargs["metric_name"] = request_data.metric_name
        if request_data.tag_filter is not None:
            grpc_request_kwargs["tag_filter_json"] = json.dumps(request_data.tag_filter)
        if request_data.agg is not None:
            grpc_request_kwargs["agg"] = request_data.agg
        if request_data.viz is not None:
            grpc_request_kwargs["viz"] = request_data.viz
        if request_data.step is not None:
            grpc_request_kwargs["step"] = request_data.step
        if request_data.statusClass is not None:
            grpc_request_kwargs["status_class"] = request_data.statusClass
        if request_data.search is not None:
            grpc_request_kwargs["logs_search"] = request_data.search

        grpc_request = auth_pb2.UpdateDashboardPanelRequest(**grpc_request_kwargs)

        response = await asyncio.wait_for(
            stub.UpdateDashboardPanel(grpc_request), timeout=5.0
        )

        if not response.panel.id:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail=f"Panel {panel_id} not found",
            )

        return _panel_proto_to_response(response.panel)

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
    response_model=schemas.DeletePanelResponse,
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
            return schemas.DeletePanelResponse(
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
