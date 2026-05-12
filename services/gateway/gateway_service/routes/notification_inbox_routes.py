import logging

import fastapi
import gateway_service.proto.auth_pb2 as auth_pb2
import gateway_service.proto.auth_pb2_grpc as auth_pb2_grpc
import grpc
from pydantic import BaseModel

router = fastapi.APIRouter(tags=["Notification Inbox"])
logger = logging.getLogger(__name__)


def _require_account(request: fastapi.Request) -> int:
    account_id = getattr(request.state, "account_id", None)
    if not account_id:
        raise fastapi.HTTPException(status_code=401, detail="Authentication required")
    return account_id


class NotificationItemResponse(BaseModel):
    id: int
    user_id: int
    project_id: int
    kind: str
    severity: int
    payload: str
    created_at: str
    read_at: str | None
    expires_at: str


class ListNotificationsResponse(BaseModel):
    notifications: list[NotificationItemResponse]
    has_more: bool


class UnreadCountResponse(BaseModel):
    count: int


def _proto_to_notif(n) -> NotificationItemResponse:
    return NotificationItemResponse(
        id=n.id,
        user_id=n.user_id,
        project_id=n.project_id,
        kind=n.kind,
        severity=n.severity,
        payload=n.payload,
        created_at=n.created_at,
        read_at=n.read_at if n.HasField("read_at") else None,
        expires_at=n.expires_at,
    )


@router.get(
    "/inbox",
    response_model=ListNotificationsResponse,
    summary="List notification inbox",
)
async def list_notifications(
    request: fastapi.Request,
    unread_only: bool = fastapi.Query(False),
    limit: int = fastapi.Query(50, ge=1, le=200),
    before_id: int | None = fastapi.Query(None),
) -> ListNotificationsResponse:
    account_id = _require_account(request)
    grpc_pool = request.app.state.grpc_pool

    proto_req = auth_pb2.ListNotificationsRequest(
        user_id=account_id,
        unread_only=unread_only,
        limit=limit,
    )
    if before_id is not None:
        proto_req.before_id = before_id

    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = await stub.ListNotifications(proto_req, timeout=5.0)
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    return ListNotificationsResponse(
        notifications=[_proto_to_notif(n) for n in response.notifications],
        has_more=response.has_more,
    )


@router.get(
    "/inbox/unread-count",
    response_model=UnreadCountResponse,
    summary="Get unread notification count",
)
async def get_unread_count(request: fastapi.Request) -> UnreadCountResponse:
    account_id = _require_account(request)
    grpc_pool = request.app.state.grpc_pool

    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = await stub.GetUnreadNotificationCount(
            auth_pb2.GetUnreadNotificationCountRequest(user_id=account_id),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))

    return UnreadCountResponse(count=response.count)


@router.post(
    "/inbox/{notification_id}/read",
    status_code=204,
    summary="Mark notification as read",
)
async def mark_notification_read(
    notification_id: int, request: fastapi.Request
) -> None:
    account_id = _require_account(request)
    grpc_pool = request.app.state.grpc_pool

    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        await stub.MarkNotificationRead(
            auth_pb2.MarkNotificationReadRequest(
                notification_id=notification_id, user_id=account_id
            ),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))


@router.post(
    "/inbox/read-all",
    status_code=204,
    summary="Mark all notifications as read",
)
async def mark_all_notifications_read(request: fastapi.Request) -> None:
    account_id = _require_account(request)
    grpc_pool = request.app.state.grpc_pool

    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        await stub.MarkAllNotificationsRead(
            auth_pb2.MarkAllNotificationsReadRequest(user_id=account_id),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))


@router.delete(
    "/inbox/{notification_id}",
    status_code=204,
    summary="Delete notification",
)
async def delete_notification(
    notification_id: int, request: fastapi.Request
) -> None:
    account_id = _require_account(request)
    grpc_pool = request.app.state.grpc_pool

    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        await stub.DeleteNotification(
            auth_pb2.DeleteNotificationRequest(
                notification_id=notification_id, user_id=account_id
            ),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
