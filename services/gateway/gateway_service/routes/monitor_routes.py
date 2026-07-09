import logging
import typing

import fastapi
import gateway_service.proto.auth_pb2 as auth_pb2
import gateway_service.proto.auth_pb2_grpc as auth_pb2_grpc
import grpc
from gateway_service import dependencies
from pydantic import BaseModel, Field

router = fastapi.APIRouter(tags=["Monitors"])
logger = logging.getLogger(__name__)


def _stub(request: fastapi.Request) -> auth_pb2_grpc.AuthServiceStub:
    grpc_pool = request.app.state.grpc_pool
    channel = grpc_pool.get_channel("auth")
    return auth_pb2_grpc.AuthServiceStub(channel)


class MonitorResponse(BaseModel):
    id: int
    project_id: int
    kind: str
    name: str
    target_url: str | None
    token: str | None
    interval_s: int
    timeout_s: int
    expected_status: int
    grace_s: int
    enabled: bool
    state: str
    created_at: str
    updated_at: str
    last_checked_at: str | None
    last_ok: bool | None
    last_latency_ms: int | None
    uptime_pct_24h: float


class CreateMonitorRequest(BaseModel):
    project_id: int
    kind: typing.Literal["http", "heartbeat"]
    name: str
    target_url: str | None = None
    interval_s: int = Field(default=60, ge=10, le=86400)
    timeout_s: int = Field(default=10, ge=1, le=60)
    expected_status: int = Field(default=200, ge=100, le=599)
    grace_s: int = Field(default=0, ge=0, le=86400)


class UpdateMonitorRequest(BaseModel):
    name: str | None = None
    target_url: str | None = None
    interval_s: int | None = Field(default=None, ge=10, le=86400)
    timeout_s: int | None = Field(default=None, ge=1, le=60)
    expected_status: int | None = Field(default=None, ge=100, le=599)
    grace_s: int | None = Field(default=None, ge=0, le=86400)
    enabled: bool | None = None


def _proto_monitor_to_response(m) -> MonitorResponse:
    return MonitorResponse(
        id=m.id,
        project_id=m.project_id,
        kind=m.kind,
        name=m.name,
        target_url=m.target_url if m.HasField("target_url") else None,
        token=m.token if m.HasField("token") else None,
        interval_s=m.interval_s,
        timeout_s=m.timeout_s,
        expected_status=m.expected_status,
        grace_s=m.grace_s,
        enabled=m.enabled,
        state=m.state,
        created_at=m.created_at,
        updated_at=m.updated_at,
        last_checked_at=m.last_checked_at if m.HasField("last_checked_at") else None,
        last_ok=m.last_ok if m.HasField("last_ok") else None,
        last_latency_ms=m.last_latency_ms if m.HasField("last_latency_ms") else None,
        uptime_pct_24h=m.uptime_pct_24h,
    )


@router.get(
    "/monitors",
    response_model=list[MonitorResponse],
    summary="List monitors for a project",
    description="Lists uptime (http) and heartbeat monitors for a project, with latest check status and a 24h uptime percentage.",
)
async def list_monitors(
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> list[MonitorResponse]:
    try:
        response = await _stub(request).ListMonitors(
            auth_pb2.ListMonitorsRequest(project_id=project_id), timeout=5.0
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return [_proto_monitor_to_response(m) for m in response.monitors]


@router.post(
    "/monitors",
    status_code=201,
    response_model=MonitorResponse,
    summary="Create monitor",
    description="Create an http (uptime) or heartbeat (dead-man's-switch) monitor. For heartbeat monitors a public ping token is generated and returned.",
)
async def create_monitor(
    payload: CreateMonitorRequest, request: fastapi.Request
) -> MonitorResponse:
    if not hasattr(request.state, "account_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    is_member, _ = await dependencies._get_project_role(request, payload.project_id)
    if not is_member:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_403_FORBIDDEN,
            detail="Not a member of this project",
        )

    if payload.kind == "http" and not payload.target_url:
        raise fastapi.HTTPException(
            status_code=400, detail="target_url is required for http monitors"
        )

    proto_req = auth_pb2.CreateMonitorRequest(
        project_id=payload.project_id,
        kind=payload.kind,
        name=payload.name,
        interval_s=payload.interval_s,
        timeout_s=payload.timeout_s,
        expected_status=payload.expected_status,
        grace_s=payload.grace_s,
    )
    if payload.target_url:
        proto_req.target_url = payload.target_url

    try:
        response = await _stub(request).CreateMonitor(proto_req, timeout=5.0)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(status_code=400, detail=str(e.details()))
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return _proto_monitor_to_response(response.monitor)


@router.patch(
    "/monitors/{monitor_id}",
    response_model=MonitorResponse,
    summary="Update monitor",
)
async def update_monitor(
    monitor_id: int,
    payload: UpdateMonitorRequest,
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> MonitorResponse:
    proto_req = auth_pb2.UpdateMonitorRequest(monitor_id=monitor_id, project_id=project_id)
    if payload.name is not None:
        proto_req.name = payload.name
    if payload.target_url is not None:
        proto_req.target_url = payload.target_url
    if payload.interval_s is not None:
        proto_req.interval_s = payload.interval_s
    if payload.timeout_s is not None:
        proto_req.timeout_s = payload.timeout_s
    if payload.expected_status is not None:
        proto_req.expected_status = payload.expected_status
    if payload.grace_s is not None:
        proto_req.grace_s = payload.grace_s
    if payload.enabled is not None:
        proto_req.enabled = payload.enabled

    try:
        response = await _stub(request).UpdateMonitor(proto_req, timeout=5.0)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(status_code=404, detail="Monitor not found")
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return _proto_monitor_to_response(response.monitor)


@router.delete(
    "/monitors/{monitor_id}",
    status_code=204,
    summary="Delete monitor",
)
async def delete_monitor(
    monitor_id: int,
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> None:
    try:
        await _stub(request).DeleteMonitor(
            auth_pb2.DeleteMonitorRequest(monitor_id=monitor_id, project_id=project_id),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))


# NOTE: authenticated solely by the token embedded in the URL path -- see
# gateway_service/middleware/auth.py::_is_public_path for the exemption from
# the normal JWT/API-key auth middleware.


@router.post(
    "/monitors/{token}/ping",
    status_code=204,
    summary="Heartbeat ping (public, token-authenticated)",
    description="Public dead-man's-switch ping endpoint for heartbeat monitors. Call this on a schedule from the monitored job/service; no JWT or API key required, the token in the URL is the credential.",
)
async def heartbeat_ping(token: str, request: fastapi.Request) -> None:
    try:
        response = await _stub(request).RecordHeartbeatPing(
            auth_pb2.RecordHeartbeatPingRequest(token=token), timeout=5.0
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    if not response.success:
        raise fastapi.HTTPException(
            status_code=404, detail=response.error_message or "Monitor not found"
        )
