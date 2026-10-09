import datetime
import logging

import fastapi
import grpc
from gateway_service import config
from gateway_service.proto import auth_pb2, auth_pb2_grpc
from gateway_service.services import pubsub_hub
from sse_starlette.sse import EventSourceResponse

router = fastapi.APIRouter(tags=["Notifications"])
logger = logging.getLogger(__name__)


async def get_user_projects(grpc_pool, account_id: int) -> set[int]:
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)

        request = auth_pb2.GetProjectsRequest(account_id=account_id)
        response = await stub.GetProjects(request, timeout=5.0)

        project_ids = {project.project_id for project in response.projects}
        logger.info(f"Retrieved {len(project_ids)} projects for account {account_id}")
        return project_ids

    except grpc.RpcError as e:
        logger.error(f"gRPC error fetching user projects: {e.code()}", exc_info=True)
        return set()
    except Exception as e:
        logger.error(f"Error fetching user projects: {e}", exc_info=True)
        return set()


async def _streamed_project_ids(request: fastapi.Request) -> set[int]:
    if getattr(request.state, "auth_type", None) == "api_key":
        return {request.state.project_id}

    account_id = getattr(request.state, "account_id", None)
    if not account_id:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return await get_user_projects(request.app.state.grpc_pool, account_id)


@router.get(
    "/notifications/stream",
    summary="Real-time error notifications stream (SSE)",
    description="""
Server-Sent Events (SSE) stream for real-time error notifications.

Automatically receives notifications when error or critical logs are ingested for projects you have access to.

**Authentication:** Required (Session Token, or an API Key for its own project)

**Events:**
- `connected` - Initial connection confirmation with project list
- `error_notification` - New error/critical log received
- `heartbeat` - Keep-alive ping every 30 seconds

**Connection Handling:**
- Browser's EventSource automatically reconnects on disconnect
- Filters notifications by projects you have access to

**Example usage (JavaScript):**
```javascript
const eventSource = new EventSource('/api/v1/notifications/stream', {
  headers: { 'Authorization': 'Bearer <session-token>' }
});

eventSource.addEventListener('error_notification', (event) => {
  const error = JSON.parse(event.data);
  console.log('New error:', error);
});
```
    """,
    response_class=EventSourceResponse,
    responses={
        200: {
            "description": "SSE stream established",
            "content": {
                "text/event-stream": {
                    "example": 'event: connected\\ndata: {"timestamp": "2025-01-15T10:00:00Z", "projects": [1, 2]}\\n\\n'
                }
            },
        },
        401: {
            "description": "Authentication required",
            "content": {"application/json": {"example": {"detail": "Authentication required"}}},
        },
        503: {
            "description": "Notifications disabled",
            "content": {
                "application/json": {"example": {"detail": "Notifications are currently disabled"}}
            },
        },
    },
)
async def stream_error_notifications(request: fastapi.Request):
    if not config.settings.NOTIFICATIONS_ENABLED:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notifications are currently disabled",
        )

    project_ids = sorted(await _streamed_project_ids(request))
    if not project_ids:
        logger.warning("No projects available for notification stream; it will stay idle")

    connected_payload = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "projects": project_ids,
        "warning": "No projects available — stream idle" if not project_ids else None,
    }
    return EventSourceResponse(
        pubsub_hub.channel_events(
            request.app.state.pubsub_hub,
            [f"notifications:errors:{project_id}" for project_id in project_ids],
            "error_notification",
            connected_payload,
            config.settings.NOTIFICATIONS_HEARTBEAT_INTERVAL,
        )
    )
