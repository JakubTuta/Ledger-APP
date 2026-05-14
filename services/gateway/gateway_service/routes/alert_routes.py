import json
import logging

import fastapi
import gateway_service.proto.auth_pb2 as auth_pb2
import gateway_service.proto.auth_pb2_grpc as auth_pb2_grpc
import grpc
import httpx
from pydantic import BaseModel, Field

router = fastapi.APIRouter(tags=["Alerts"])
logger = logging.getLogger(__name__)


def _require_account(request: fastapi.Request) -> int:
    account_id = getattr(request.state, "account_id", None)
    if not account_id:
        raise fastapi.HTTPException(status_code=401, detail="Authentication required")
    return account_id


# ==================== Schemas ====================


class AlertRuleResponse(BaseModel):
    id: int
    project_id: int
    name: str
    enabled: bool
    metric: str
    tag_filter: str
    comparator: str
    threshold: float
    window_seconds: int
    cooldown_seconds: int
    severity: int
    last_fired_at: str | None
    last_state: str
    created_at: str
    updated_at: str


class CreateAlertRuleRequest(BaseModel):
    project_id: int
    name: str
    metric: str
    tag_filter: str = Field(default="{}")
    comparator: str
    threshold: float
    window_seconds: int = Field(default=300, ge=60)
    cooldown_seconds: int = Field(default=3600, ge=60)
    severity: int = Field(default=1, ge=0, le=2)


class UpdateAlertRuleRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    threshold: float | None = None
    cooldown_seconds: int | None = None


class AlertChannelResponse(BaseModel):
    id: int
    project_id: int
    user_id: int
    kind: str
    name: str
    config: str
    enabled: bool
    created_at: str


class CreateAlertChannelRequest(BaseModel):
    project_id: int
    kind: str
    config: str = Field(default="{}")


class UpdateAlertChannelRequest(BaseModel):
    config: str | None = None
    enabled: bool | None = None


class AlertNotificationPreferenceResponse(BaseModel):
    user_id: int
    project_id: int
    rule_id: int | None
    severity: int | None
    muted: bool
    channels: str


class UpsertAlertNotificationPreferenceRequest(BaseModel):
    project_id: int
    rule_id: int | None = None
    severity: int | None = None
    muted: bool = False
    channels: str = Field(default="[]")


# ==================== Alert Rule Endpoints ====================


def _proto_rule_to_response(r) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=r.id,
        project_id=r.project_id,
        name=r.name,
        enabled=r.enabled,
        metric=r.metric,
        tag_filter=r.tag_filter,
        comparator=r.comparator,
        threshold=r.threshold,
        window_seconds=r.window_seconds,
        cooldown_seconds=r.cooldown_seconds,
        severity=r.severity,
        last_fired_at=r.last_fired_at if r.HasField("last_fired_at") else None,
        last_state=r.last_state,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get(
    "/alerts/rules",
    response_model=list[AlertRuleResponse],
    summary="List alert rules for a project",
)
async def list_alert_rules(
    request: fastapi.Request,
    project_id: int = fastapi.Query(...),
) -> list[AlertRuleResponse]:
    _require_account(request)
    grpc_pool = request.app.state.grpc_pool
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = await stub.ListAlertRules(
            auth_pb2.ListAlertRulesRequest(project_id=project_id), timeout=5.0
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return [_proto_rule_to_response(r) for r in response.rules]


@router.get(
    "/alerts/rules/{rule_id}",
    response_model=AlertRuleResponse,
    summary="Get alert rule",
)
async def get_alert_rule(
    request: fastapi.Request,
    rule_id: int,
    project_id: int = fastapi.Query(...),
) -> AlertRuleResponse:
    _require_account(request)
    grpc_pool = request.app.state.grpc_pool
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = await stub.GetAlertRule(
            auth_pb2.GetAlertRuleRequest(rule_id=rule_id, project_id=project_id),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    if not response.found:
        raise fastapi.HTTPException(status_code=404, detail="Alert rule not found")
    return _proto_rule_to_response(response.rule)


@router.post(
    "/alerts/rules",
    status_code=201,
    response_model=AlertRuleResponse,
    summary="Create alert rule",
)
async def create_alert_rule(
    payload: CreateAlertRuleRequest,
    request: fastapi.Request,
) -> AlertRuleResponse:
    _require_account(request)
    grpc_pool = request.app.state.grpc_pool
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = await stub.CreateAlertRule(
            auth_pb2.CreateAlertRuleRequest(
                project_id=payload.project_id,
                name=payload.name,
                metric=payload.metric,
                tag_filter=payload.tag_filter,
                comparator=payload.comparator,
                threshold=payload.threshold,
                window_seconds=payload.window_seconds,
                cooldown_seconds=payload.cooldown_seconds,
                severity=payload.severity,
            ),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return _proto_rule_to_response(response.rule)


@router.patch(
    "/alerts/rules/{rule_id}",
    response_model=AlertRuleResponse,
    summary="Update alert rule",
)
async def update_alert_rule(
    rule_id: int,
    payload: UpdateAlertRuleRequest,
    request: fastapi.Request,
    project_id: int = fastapi.Query(...),
) -> AlertRuleResponse:
    _require_account(request)
    grpc_pool = request.app.state.grpc_pool
    proto_req = auth_pb2.UpdateAlertRuleRequest(
        rule_id=rule_id, project_id=project_id
    )
    if payload.name is not None:
        proto_req.name = payload.name
    if payload.enabled is not None:
        proto_req.enabled = payload.enabled
    if payload.threshold is not None:
        proto_req.threshold = payload.threshold
    if payload.cooldown_seconds is not None:
        proto_req.cooldown_seconds = payload.cooldown_seconds
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = await stub.UpdateAlertRule(proto_req, timeout=5.0)
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return _proto_rule_to_response(response.rule)


@router.delete(
    "/alerts/rules/{rule_id}",
    status_code=204,
    summary="Delete alert rule",
)
async def delete_alert_rule(
    rule_id: int,
    request: fastapi.Request,
    project_id: int = fastapi.Query(...),
) -> None:
    _require_account(request)
    grpc_pool = request.app.state.grpc_pool
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        await stub.DeleteAlertRule(
            auth_pb2.DeleteAlertRuleRequest(rule_id=rule_id, project_id=project_id),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))


# ==================== Alert Channel Endpoints ====================


def _proto_channel_to_response(c) -> AlertChannelResponse:
    return AlertChannelResponse(
        id=c.id,
        project_id=c.project_id,
        user_id=c.user_id,
        kind=c.kind,
        name=c.name,
        config=c.config,
        enabled=c.enabled,
        created_at=c.created_at,
    )


@router.get(
    "/alerts/channels",
    response_model=list[AlertChannelResponse],
    summary="List alert channels for a project",
)
async def list_alert_channels(
    request: fastapi.Request,
    project_id: int = fastapi.Query(...),
) -> list[AlertChannelResponse]:
    _require_account(request)
    grpc_pool = request.app.state.grpc_pool
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = await stub.ListAlertChannels(
            auth_pb2.ListAlertChannelsRequest(project_id=project_id), timeout=5.0
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return [_proto_channel_to_response(c) for c in response.channels]


@router.post(
    "/alerts/channels",
    status_code=201,
    response_model=AlertChannelResponse,
    summary="Create alert channel",
)
async def create_alert_channel(
    payload: CreateAlertChannelRequest,
    request: fastapi.Request,
) -> AlertChannelResponse:
    account_id = _require_account(request)
    grpc_pool = request.app.state.grpc_pool
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = await stub.CreateAlertChannel(
            auth_pb2.CreateAlertChannelRequest(
                project_id=payload.project_id,
                user_id=account_id,
                kind=payload.kind,
                name=payload.kind,
                config=payload.config,
            ),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return _proto_channel_to_response(response.channel)


@router.patch(
    "/alerts/channels/{channel_id}",
    response_model=AlertChannelResponse,
    summary="Update alert channel",
)
async def update_alert_channel(
    channel_id: int,
    payload: UpdateAlertChannelRequest,
    request: fastapi.Request,
    project_id: int = fastapi.Query(...),
) -> AlertChannelResponse:
    _require_account(request)
    grpc_pool = request.app.state.grpc_pool
    proto_req = auth_pb2.UpdateAlertChannelRequest(
        channel_id=channel_id, project_id=project_id
    )
    if payload.config is not None:
        proto_req.config = payload.config
    if payload.enabled is not None:
        proto_req.enabled = payload.enabled
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = await stub.UpdateAlertChannel(proto_req, timeout=5.0)
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return _proto_channel_to_response(response.channel)


@router.delete(
    "/alerts/channels/{channel_id}",
    status_code=204,
    summary="Delete alert channel",
)
async def delete_alert_channel(
    channel_id: int,
    request: fastapi.Request,
    project_id: int = fastapi.Query(...),
) -> None:
    _require_account(request)
    grpc_pool = request.app.state.grpc_pool
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        await stub.DeleteAlertChannel(
            auth_pb2.DeleteAlertChannelRequest(
                channel_id=channel_id, project_id=project_id
            ),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))


@router.post(
    "/alerts/channels/{channel_id}/test",
    status_code=204,
    summary="Send a test notification through an alert channel",
    description=(
        "Dispatches a synthetic test alert through the specified channel. "
        "For in_app channels, creates a test notification in the inbox. "
        "For webhook channels, POSTs a test payload to the configured URL. "
        "For email channels, logs the test (email stub)."
    ),
)
async def test_alert_channel(
    channel_id: int,
    request: fastapi.Request,
    project_id: int = fastapi.Query(...),
) -> None:
    account_id = _require_account(request)
    grpc_pool = request.app.state.grpc_pool

    try:
        auth_channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(auth_channel)
        ch_response = await stub.GetAlertChannel(
            auth_pb2.GetAlertChannelRequest(
                channel_id=channel_id, project_id=project_id
            ),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    if not ch_response.found:
        raise fastapi.HTTPException(status_code=404, detail="Alert channel not found")

    ch = ch_response.channel
    test_payload = {
        "test": True,
        "channel_id": channel_id,
        "channel_kind": ch.kind,
        "message": "This is a test notification from Ledger.",
    }

    if ch.kind == "in_app":
        try:
            auth_channel = grpc_pool.get_channel("auth")
            stub = auth_pb2_grpc.AuthServiceStub(auth_channel)
            await stub.CreateNotification(
                auth_pb2.CreateNotificationRequest(
                    user_id=ch.user_id,
                    project_id=ch.project_id,
                    kind="alert_firing",
                    severity=1,
                    payload=json.dumps(test_payload),
                ),
                timeout=5.0,
            )
        except grpc.RpcError as e:
            raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    elif ch.kind == "webhook":
        try:
            config_dict = json.loads(ch.config) if ch.config else {}
            url = config_dict.get("url")
            if not url:
                raise fastapi.HTTPException(
                    status_code=400, detail="Webhook channel has no URL configured"
                )
            async with httpx.AsyncClient(timeout=10.0) as http:
                await http.post(
                    url,
                    json=test_payload,
                    headers={"Content-Type": "application/json"},
                )
        except httpx.RequestError as e:
            raise fastapi.HTTPException(
                status_code=502, detail=f"Webhook delivery failed: {str(e)}"
            )

    elif ch.kind == "email":
        logger.info(
            f"[email stub] Test notification for channel {channel_id} "
            f"(user {account_id}): {test_payload}"
        )


# ==================== Notification Preferences Endpoints ====================


@router.get(
    "/alerts/notification-preferences",
    response_model=list[AlertNotificationPreferenceResponse],
    summary="Get alert notification preferences",
)
async def get_alert_notification_preferences(
    request: fastapi.Request,
    project_id: int = fastapi.Query(...),
) -> list[AlertNotificationPreferenceResponse]:
    account_id = _require_account(request)
    grpc_pool = request.app.state.grpc_pool
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = await stub.GetAlertNotificationPreferences(
            auth_pb2.GetAlertNotificationPreferencesRequest(
                user_id=account_id, project_id=project_id
            ),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return [
        AlertNotificationPreferenceResponse(
            user_id=p.user_id,
            project_id=p.project_id,
            rule_id=p.rule_id if p.HasField("rule_id") else None,
            severity=p.severity if p.HasField("severity") else None,
            muted=p.muted,
            channels=p.channels,
        )
        for p in response.preferences
    ]


@router.put(
    "/alerts/notification-preferences",
    response_model=AlertNotificationPreferenceResponse,
    summary="Upsert alert notification preference",
)
async def upsert_alert_notification_preference(
    payload: UpsertAlertNotificationPreferenceRequest,
    request: fastapi.Request,
) -> AlertNotificationPreferenceResponse:
    account_id = _require_account(request)
    grpc_pool = request.app.state.grpc_pool
    proto_req = auth_pb2.UpsertAlertNotificationPreferenceRequest(
        user_id=account_id,
        project_id=payload.project_id,
        muted=payload.muted,
        channels=payload.channels,
    )
    if payload.rule_id is not None:
        proto_req.rule_id = payload.rule_id
    if payload.severity is not None:
        proto_req.severity = payload.severity
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = await stub.UpsertAlertNotificationPreference(proto_req, timeout=5.0)
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    p = response.preference
    return AlertNotificationPreferenceResponse(
        user_id=p.user_id,
        project_id=p.project_id,
        rule_id=p.rule_id if p.HasField("rule_id") else None,
        severity=p.severity if p.HasField("severity") else None,
        muted=p.muted,
        channels=p.channels,
    )
