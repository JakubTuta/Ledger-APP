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


class CreateAlertRuleRequest(BaseModel):
    project_id: int
    name: str
    metric: str
    comparator: str
    threshold: float
    unit: str = Field(default="count")
    severity: int = Field(default=1, ge=0, le=2)
    connector_ids: list[int] = Field(default_factory=list)


class UpdateAlertRuleRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    threshold: float | None = None
    unit: str | None = None
    severity: int | None = None
    comparator: str | None = None
    metric: str | None = None
    connector_ids: list[int] | None = None


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


class AlertEventListResponse(BaseModel):
    events: list[AlertEventResponse]
    has_more: bool


# ==================== Converters ====================


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
    )


def _stub(request: fastapi.Request) -> auth_pb2_grpc.AuthServiceStub:
    grpc_pool = request.app.state.grpc_pool
    channel = grpc_pool.get_channel("auth")
    return auth_pb2_grpc.AuthServiceStub(channel)


# ==================== Connector Endpoints ====================


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
    proto_req = auth_pb2.UpdateConnectorRequest(
        connector_id=connector_id, account_id=account_id
    )
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
async def delete_connector(
    connector_id: int, request: fastapi.Request
) -> None:
    account_id = _require_account(request)
    try:
        await _stub(request).DeleteConnector(
            auth_pb2.DeleteConnectorRequest(
                connector_id=connector_id, account_id=account_id
            ),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))


@router.post(
    "/connectors/{connector_id}/test",
    status_code=204,
    summary="Send a test notification through a connector",
)
async def test_connector(
    connector_id: int, request: fastapi.Request
) -> None:
    account_id = _require_account(request)
    try:
        ch_response = await _stub(request).GetConnector(
            auth_pb2.GetConnectorRequest(
                connector_id=connector_id, account_id=account_id
            ),
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
        try:
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

    elif c.kind == "email":
        logger.info(
            f"[email stub] Test notification for connector {connector_id} "
            f"(account {account_id}): {test_payload}"
        )


# ==================== Alert Rule Endpoints ====================


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
    project_id: int = fastapi.Query(...),
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
    try:
        response = await _stub(request).CreateAlertRule(
            auth_pb2.CreateAlertRuleRequest(
                project_id=payload.project_id,
                name=payload.name,
                metric=payload.metric,
                comparator=payload.comparator,
                threshold=payload.threshold,
                unit=payload.unit,
                severity=payload.severity,
                connector_ids=payload.connector_ids,
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
    proto_req = auth_pb2.UpdateAlertRuleRequest(
        rule_id=rule_id, project_id=project_id
    )
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
    project_id: int = fastapi.Query(...),
) -> None:
    _require_account(request)
    try:
        await _stub(request).DeleteAlertRule(
            auth_pb2.DeleteAlertRuleRequest(rule_id=rule_id, project_id=project_id),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))


# ==================== Alert History Endpoint ====================


@router.get(
    "/alerts/history",
    response_model=AlertEventListResponse,
    summary="List alert event history for a project",
)
async def list_alert_history(
    request: fastapi.Request,
    project_id: int = fastapi.Query(...),
    limit: int = fastapi.Query(25, ge=1, le=100),
    before_id: int | None = fastapi.Query(None),
) -> AlertEventListResponse:
    _require_account(request)
    proto_req = auth_pb2.ListAlertEventsRequest(
        project_id=project_id, limit=limit
    )
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
