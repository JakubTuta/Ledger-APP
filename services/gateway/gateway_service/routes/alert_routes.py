import json
import logging

import fastapi
import gateway_service.proto.auth_pb2 as auth_pb2
import gateway_service.proto.auth_pb2_grpc as auth_pb2_grpc
import grpc
import httpx
from gateway_service import dependencies
from gateway_service.services import net_guard
from pydantic import BaseModel, Field

router = fastapi.APIRouter(tags=["Alerts"])
logger = logging.getLogger(__name__)


def _require_account(request: fastapi.Request) -> int:
    account_id = getattr(request.state, "account_id", None)
    if not account_id:
        raise fastapi.HTTPException(status_code=401, detail="Authentication required")
    return account_id


class ConnectorResponse(BaseModel):
    id: int
    account_id: int
    kind: str
    name: str
    config: str
    enabled: bool
    created_at: str


class CreateConnectorRequest(BaseModel):
    kind: str
    name: str
    config: str = Field(default="{}")


class UpdateConnectorRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    config: str | None = None


class AlertRuleResponse(BaseModel):
    id: int
    project_id: int
    name: str
    enabled: bool
    metric: str
    comparator: str
    threshold: float
    unit: str
    severity: int
    connector_ids: list[int]
    last_fired_at: str | None
    created_at: str
    updated_at: str
    escalation_after_minutes: int | None = None
    escalate_connector_id: int | None = None


class CreateAlertRuleRequest(BaseModel):
    project_id: int
    name: str
    metric: str
    comparator: str
    threshold: float
    unit: str = Field(default="count")
    severity: int = Field(default=1, ge=0, le=2)
    connector_ids: list[int] = Field(default_factory=list)
    escalation_after_minutes: int | None = Field(default=None, ge=1, le=1440)
    escalate_connector_id: int | None = None


class UpdateAlertRuleRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    threshold: float | None = None
    unit: str | None = None
    severity: int | None = None
    comparator: str | None = None
    metric: str | None = None
    connector_ids: list[int] | None = None
    escalation_after_minutes: int | None = Field(default=None, ge=1, le=1440)
    escalate_connector_id: int | None = None
    clear_escalate_connector_id: bool = False


class AlertEventResponse(BaseModel):
    id: int
    rule_id: int | None
    project_id: int
    rule_name: str
    metric: str
    comparator: str
    threshold: float
    unit: str
    value: float
    severity: int
    connectors_sent: str
    fired_at: str
    acked_by: int | None = None
    acked_at: str | None = None
    snoozed_until: str | None = None


class SnoozeAlertEventRequest(BaseModel):
    minutes: int = Field(gt=0, le=7 * 24 * 60)


class AlertEventListResponse(BaseModel):
    events: list[AlertEventResponse]
    has_more: bool


def _proto_connector_to_response(c) -> ConnectorResponse:
    return ConnectorResponse(
        id=c.id,
        account_id=c.account_id,
        kind=c.kind,
        name=c.name,
        config=c.config,
        enabled=c.enabled,
        created_at=c.created_at,
    )


def _proto_rule_to_response(r) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=r.id,
        project_id=r.project_id,
        name=r.name,
        enabled=r.enabled,
        metric=r.metric,
        comparator=r.comparator,
        threshold=r.threshold,
        unit=r.unit,
        severity=r.severity,
        connector_ids=list(r.connector_ids),
        last_fired_at=r.last_fired_at if r.HasField("last_fired_at") else None,
        created_at=r.created_at,
        updated_at=r.updated_at,
        escalation_after_minutes=(
            r.escalation_after_minutes if r.HasField("escalation_after_minutes") else None
        ),
        escalate_connector_id=(
            r.escalate_connector_id if r.HasField("escalate_connector_id") else None
        ),
    )


def _proto_event_to_response(e) -> AlertEventResponse:
    return AlertEventResponse(
        id=e.id,
        rule_id=e.rule_id if e.HasField("rule_id") else None,
        project_id=e.project_id,
        rule_name=e.rule_name,
        metric=e.metric,
        comparator=e.comparator,
        threshold=e.threshold,
        unit=e.unit,
        value=e.value,
        severity=e.severity,
        connectors_sent=e.connectors_sent,
        fired_at=e.fired_at,
        acked_by=e.acked_by if e.HasField("acked_by") else None,
        acked_at=e.acked_at if e.HasField("acked_at") else None,
        snoozed_until=e.snoozed_until if e.HasField("snoozed_until") else None,
    )


def _stub(request: fastapi.Request) -> auth_pb2_grpc.AuthServiceStub:
    grpc_pool = request.app.state.grpc_pool
    channel = grpc_pool.get_channel("auth")
    return auth_pb2_grpc.AuthServiceStub(channel)


@router.get(
    "/connectors",
    response_model=list[ConnectorResponse],
    summary="List account connectors",
)
async def list_connectors(request: fastapi.Request) -> list[ConnectorResponse]:
    account_id = _require_account(request)
    try:
        response = await _stub(request).ListConnectors(
            auth_pb2.ListConnectorsRequest(account_id=account_id), timeout=5.0
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return [_proto_connector_to_response(c) for c in response.connectors]


@router.post(
    "/connectors",
    status_code=201,
    response_model=ConnectorResponse,
    summary="Create connector",
)
async def create_connector(
    payload: CreateConnectorRequest, request: fastapi.Request
) -> ConnectorResponse:
    account_id = _require_account(request)
    try:
        response = await _stub(request).CreateConnector(
            auth_pb2.CreateConnectorRequest(
                account_id=account_id,
                kind=payload.kind,
                name=payload.name,
                config=payload.config,
            ),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return _proto_connector_to_response(response.connector)


@router.patch(
    "/connectors/{connector_id}",
    response_model=ConnectorResponse,
    summary="Update connector",
)
async def update_connector(
    connector_id: int,
    payload: UpdateConnectorRequest,
    request: fastapi.Request,
) -> ConnectorResponse:
    account_id = _require_account(request)
    proto_req = auth_pb2.UpdateConnectorRequest(connector_id=connector_id, account_id=account_id)
    if payload.name is not None:
        proto_req.name = payload.name
    if payload.enabled is not None:
        proto_req.enabled = payload.enabled
    if payload.config is not None:
        proto_req.config = payload.config
    try:
        response = await _stub(request).UpdateConnector(proto_req, timeout=5.0)
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return _proto_connector_to_response(response.connector)


@router.delete(
    "/connectors/{connector_id}",
    status_code=204,
    summary="Delete connector",
)
async def delete_connector(connector_id: int, request: fastapi.Request) -> None:
    account_id = _require_account(request)
    try:
        await _stub(request).DeleteConnector(
            auth_pb2.DeleteConnectorRequest(connector_id=connector_id, account_id=account_id),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))


@router.post(
    "/connectors/{connector_id}/test",
    status_code=204,
    summary="Send a test notification through a connector",
)
async def test_connector(connector_id: int, request: fastapi.Request) -> None:
    account_id = _require_account(request)
    try:
        ch_response = await _stub(request).GetConnector(
            auth_pb2.GetConnectorRequest(connector_id=connector_id, account_id=account_id),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    if not ch_response.found:
        raise fastapi.HTTPException(status_code=404, detail="Connector not found")

    c = ch_response.connector
    test_payload = {
        "test": True,
        "connector_id": connector_id,
        "connector_kind": c.kind,
        "message": "This is a test notification from Ledger.",
    }
    config_dict = json.loads(c.config) if c.config else {}

    if c.kind == "in_app":
        try:
            await _stub(request).CreateNotification(
                auth_pb2.CreateNotificationRequest(
                    user_id=account_id,
                    project_id=0,
                    kind="alert_firing",
                    severity=1,
                    payload=json.dumps(test_payload),
                ),
                timeout=5.0,
            )
        except grpc.RpcError as e:
            raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    elif c.kind == "webhook":
        url = config_dict.get("url")
        if not url:
            raise fastapi.HTTPException(
                status_code=400, detail="Webhook connector has no URL configured"
            )
        await _guarded_post(url, json=test_payload, headers={"Content-Type": "application/json"})

    elif c.kind == "email":
        logger.info(
            f"[email stub] Test notification for connector {connector_id} "
            f"(account {account_id}): {test_payload}"
        )

    elif c.kind == "slack":
        url = config_dict.get("url")
        if not url:
            raise fastapi.HTTPException(
                status_code=400, detail="Slack connector has no URL configured"
            )
        await _guarded_post(url, json={"text": "Ledger test notification: this connector works."})

    elif c.kind == "discord":
        url = config_dict.get("url")
        if not url:
            raise fastapi.HTTPException(
                status_code=400, detail="Discord connector has no URL configured"
            )
        await _guarded_post(
            url, json={"content": "Ledger test notification: this connector works."}
        )

    elif c.kind == "pagerduty":
        integration_key = config_dict.get("integration_key")
        if not isinstance(integration_key, str) or not integration_key:
            raise fastapi.HTTPException(
                status_code=400,
                detail="PagerDuty connector has no integration_key configured",
            )
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                response = await http.post(
                    "https://events.pagerduty.com/v2/enqueue",
                    json={
                        "routing_key": integration_key,
                        "event_action": "trigger",
                        "dedup_key": f"ledger-test-connector-{connector_id}",
                        "payload": {
                            "summary": "Ledger test notification: this connector works.",
                            "severity": "warning",
                            "source": "ledger",
                        },
                    },
                )
                if response.status_code >= 400:
                    raise fastapi.HTTPException(
                        status_code=502,
                        detail=f"PagerDuty returned HTTP {response.status_code}",
                    )
        except httpx.RequestError as e:
            raise fastapi.HTTPException(
                status_code=502, detail=f"PagerDuty delivery failed: {str(e)}"
            )

    elif c.kind == "opsgenie":
        api_key = config_dict.get("api_key")
        if not isinstance(api_key, str) or not api_key:
            raise fastapi.HTTPException(
                status_code=400, detail="Opsgenie connector has no api_key configured"
            )
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                response = await http.post(
                    "https://api.opsgenie.com/v2/alerts",
                    json={
                        "message": "Ledger test notification: this connector works.",
                        "alias": f"ledger-test-connector-{connector_id}",
                        "priority": "P3",
                    },
                    headers={"Authorization": f"GenieKey {api_key}"},
                )
                if response.status_code >= 400:
                    raise fastapi.HTTPException(
                        status_code=502,
                        detail=f"Opsgenie returned HTTP {response.status_code}",
                    )
        except httpx.RequestError as e:
            raise fastapi.HTTPException(
                status_code=502, detail=f"Opsgenie delivery failed: {str(e)}"
            )

    else:
        raise fastapi.HTTPException(
            status_code=400, detail=f"Unsupported connector kind '{c.kind}' for test-fire"
        )


async def _guarded_post(url: str, **kwargs) -> None:
    """POST to a user-supplied connector URL, after an SSRF check.

    Used for webhook/slack/discord test-fire delivery. PagerDuty/Opsgenie
    hit fixed vendor hosts and don't go through this helper.
    """
    try:
        await net_guard.validate_webhook_url(url)
    except net_guard.UnsafeWebhookURLError as e:
        raise fastapi.HTTPException(status_code=400, detail=f"Unsafe URL: {str(e)}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.post(url, **kwargs)
            if response.status_code >= 400:
                raise fastapi.HTTPException(
                    status_code=502, detail=f"Delivery returned HTTP {response.status_code}"
                )
    except httpx.RequestError as e:
        raise fastapi.HTTPException(status_code=502, detail=f"Delivery failed: {str(e)}")


@router.get(
    "/alerts/rules",
    response_model=list[AlertRuleResponse],
    summary="List alert rules for a project",
)
async def list_alert_rules(
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> list[AlertRuleResponse]:
    _require_account(request)
    try:
        response = await _stub(request).ListAlertRules(
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
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> AlertRuleResponse:
    _require_account(request)
    try:
        response = await _stub(request).GetAlertRule(
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
    proto_req = auth_pb2.CreateAlertRuleRequest(
        project_id=payload.project_id,
        name=payload.name,
        metric=payload.metric,
        comparator=payload.comparator,
        threshold=payload.threshold,
        unit=payload.unit,
        severity=payload.severity,
        connector_ids=payload.connector_ids,
    )
    if payload.escalation_after_minutes is not None:
        proto_req.escalation_after_minutes = payload.escalation_after_minutes
    if payload.escalate_connector_id is not None:
        proto_req.escalate_connector_id = payload.escalate_connector_id
    try:
        response = await _stub(request).CreateAlertRule(proto_req, timeout=5.0)
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
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> AlertRuleResponse:
    _require_account(request)
    proto_req = auth_pb2.UpdateAlertRuleRequest(rule_id=rule_id, project_id=project_id)
    if payload.name is not None:
        proto_req.name = payload.name
    if payload.enabled is not None:
        proto_req.enabled = payload.enabled
    if payload.threshold is not None:
        proto_req.threshold = payload.threshold
    if payload.unit is not None:
        proto_req.unit = payload.unit
    if payload.severity is not None:
        proto_req.severity = payload.severity
    if payload.comparator is not None:
        proto_req.comparator = payload.comparator
    if payload.metric is not None:
        proto_req.metric = payload.metric
    if payload.connector_ids is not None:
        proto_req.update_connectors = True
        proto_req.connector_ids.extend(payload.connector_ids)
    if payload.escalation_after_minutes is not None:
        proto_req.escalation_after_minutes = payload.escalation_after_minutes
    if payload.clear_escalate_connector_id:
        proto_req.clear_escalate_connector_id = True
    elif payload.escalate_connector_id is not None:
        proto_req.escalate_connector_id = payload.escalate_connector_id
    try:
        response = await _stub(request).UpdateAlertRule(proto_req, timeout=5.0)
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
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> None:
    _require_account(request)
    try:
        await _stub(request).DeleteAlertRule(
            auth_pb2.DeleteAlertRuleRequest(rule_id=rule_id, project_id=project_id),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))


@router.get(
    "/alerts/history",
    response_model=AlertEventListResponse,
    summary="List alert event history for a project",
)
async def list_alert_history(
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
    limit: int = fastapi.Query(25, ge=1, le=100),
    before_id: int | None = fastapi.Query(None),
) -> AlertEventListResponse:
    _require_account(request)
    proto_req = auth_pb2.ListAlertEventsRequest(project_id=project_id, limit=limit)
    if before_id is not None:
        proto_req.before_id = before_id
    try:
        response = await _stub(request).ListAlertEvents(proto_req, timeout=5.0)
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return AlertEventListResponse(
        events=[_proto_event_to_response(e) for e in response.events],
        has_more=response.has_more,
    )


@router.post(
    "/alerts/history/{event_id}/ack",
    response_model=AlertEventResponse,
    summary="Acknowledge an alert event",
)
async def ack_alert_event(
    event_id: int,
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> AlertEventResponse:
    account_id = _require_account(request)
    try:
        response = await _stub(request).AckAlertEvent(
            auth_pb2.AckAlertEventRequest(
                event_id=event_id, project_id=project_id, account_id=account_id
            ),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    if not response.success:
        raise fastapi.HTTPException(
            status_code=404, detail=response.error_message or "Alert event not found"
        )
    return _proto_event_to_response(response.event)


@router.post(
    "/alerts/history/{event_id}/snooze",
    response_model=AlertEventResponse,
    summary="Snooze re-notification for an alert event",
)
async def snooze_alert_event(
    event_id: int,
    payload: SnoozeAlertEventRequest,
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> AlertEventResponse:
    _require_account(request)
    try:
        response = await _stub(request).SnoozeAlertEvent(
            auth_pb2.SnoozeAlertEventRequest(
                event_id=event_id, project_id=project_id, minutes=payload.minutes
            ),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    if not response.success:
        raise fastapi.HTTPException(
            status_code=404, detail=response.error_message or "Alert event not found"
        )
    return _proto_event_to_response(response.event)


class MaintenanceWindowResponse(BaseModel):
    id: int
    project_id: int
    name: str
    starts_at: str
    ends_at: str
    recurrence: str | None
    created_at: str
    updated_at: str


class CreateMaintenanceWindowRequest(BaseModel):
    project_id: int
    name: str
    starts_at: str
    ends_at: str
    recurrence: str | None = Field(default=None, pattern="^(none|daily|weekly)$")


def _proto_window_to_response(w) -> MaintenanceWindowResponse:
    return MaintenanceWindowResponse(
        id=w.id,
        project_id=w.project_id,
        name=w.name,
        starts_at=w.starts_at,
        ends_at=w.ends_at,
        recurrence=w.recurrence if w.HasField("recurrence") else None,
        created_at=w.created_at,
        updated_at=w.updated_at,
    )


@router.get(
    "/maintenance-windows",
    response_model=list[MaintenanceWindowResponse],
    summary="List maintenance windows for a project",
)
async def list_maintenance_windows(
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> list[MaintenanceWindowResponse]:
    _require_account(request)
    try:
        response = await _stub(request).ListMaintenanceWindows(
            auth_pb2.ListMaintenanceWindowsRequest(project_id=project_id), timeout=5.0
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return [_proto_window_to_response(w) for w in response.windows]


@router.post(
    "/maintenance-windows",
    status_code=201,
    response_model=MaintenanceWindowResponse,
    summary="Create a maintenance window",
)
async def create_maintenance_window(
    payload: CreateMaintenanceWindowRequest,
    request: fastapi.Request,
) -> MaintenanceWindowResponse:
    _require_account(request)
    proto_req = auth_pb2.CreateMaintenanceWindowRequest(
        project_id=payload.project_id,
        name=payload.name,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    if payload.recurrence:
        proto_req.recurrence = payload.recurrence
    try:
        response = await _stub(request).CreateMaintenanceWindow(proto_req, timeout=5.0)
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return _proto_window_to_response(response.window)


@router.delete(
    "/maintenance-windows/{window_id}",
    status_code=204,
    summary="Delete a maintenance window",
)
async def delete_maintenance_window(
    window_id: int,
    request: fastapi.Request,
    project_id: int = fastapi.Depends(dependencies.require_project_member),
) -> None:
    _require_account(request)
    try:
        await _stub(request).DeleteMaintenanceWindow(
            auth_pb2.DeleteMaintenanceWindowRequest(window_id=window_id, project_id=project_id),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
