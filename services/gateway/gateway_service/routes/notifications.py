import asyncio
import json
import logging
from typing import AsyncGenerator, Set
from datetime import datetime

import fastapi
from sse_starlette.sse import EventSourceResponse
import redis.asyncio as redis
import grpc

from gateway_service import config
from gateway_service.proto import auth_pb2, auth_pb2_grpc

router = fastapi.APIRouter(tags=["Notifications"])
logger = logging.getLogger(__name__)


class NotificationStream:
    def __init__(self, redis_url: str, project_ids: Set[int]):
        self.redis_url = redis_url
        self.project_ids = project_ids
        self.redis_client = None
        self.pubsub = None

    async def subscribe(self):
        self.redis_client = redis.Redis.from_url(
            self.redis_url,
            decode_responses=True,
            max_connections=10
        )
        self.pubsub = self.redis_client.pubsub()
        channels = [f"notifications:errors:{pid}" for pid in self.project_ids]
        await self.pubsub.subscribe(*channels)
        logger.info(f"Subscribed to {len(channels)} notification channels")

    async def unsubscribe(self):
        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()
        logger.info("Unsubscribed from notification channels")

    async def listen(self) -> AsyncGenerator[dict, None]:
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        yield {
                            "event": "error_notification",
                            "data": json.dumps(data)
                        }
                    except json.JSONDecodeError:
                        logger.error(f"Failed to decode notification message: {message['data']}")
        except asyncio.CancelledError:
            logger.info("Notification stream cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in notification stream: {e}", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({"error": "Stream error occurred"})
            }


async def get_user_projects(grpc_pool, account_id: int) -> Set[int]:
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


@router.get(
    "/notifications/stream",
    summary="Real-time error notifications stream (SSE)",
    description="""
Server-Sent Events (SSE) stream for real-time error notifications.

Automatically receives notifications when error or critical logs are ingested for projects you have access to.

**Authentication:** Required (API Key or Session Token)

**Events:**
- `connected` - Initial connection confirmation with project list
- `error_notification` - New error/critical log received
- `heartbeat` - Keep-alive ping every 30 seconds

**Connection Handling:**
- Browser's EventSource automatically reconnects on disconnect
- Up to 5 concurrent connections per user (configurable)
- Filters notifications by projects you have access to

**Example usage (JavaScript):**
```javascript
const eventSource = new EventSource('/api/v1/notifications/stream', {
  headers: { 'X-API-Key': 'your-api-key' }
});

eventSource.addEventListener('error_notification', (event) => {
  const error = JSON.parse(event.data);
  console.log('New error:', error);
  showToast({
    title: error.error_type,
    message: error.message,
    level: error.level
  });
});

eventSource.addEventListener('connected', (event) => {
  const data = JSON.parse(event.data);
  console.log('Connected, watching projects:', data.projects);
});
```
    """,
    response_class=EventSourceResponse,
    responses={
        200: {
            "description": "SSE stream established",
            "content": {
                "text/event-stream": {
                    "example": "event: connected\\ndata: {\"timestamp\": \"2025-01-15T10:00:00Z\", \"projects\": [1, 2]}\\n\\n"
                }
            }
        },
        401: {
            "description": "Authentication required",
            "content": {
                "application/json": {
                    "example": {"detail": "Authentication required"}
                }
            }
        },
        503: {
            "description": "Notifications disabled",
            "content": {
                "application/json": {
                    "example": {"detail": "Notifications are currently disabled"}
                }
            }
        }
    }
)
async def stream_error_notifications(
    request: fastapi.Request
):
    if not config.settings.NOTIFICATIONS_ENABLED:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notifications are currently disabled"
        )

    project_id = getattr(request.state, "project_id", None)
    account_id = getattr(request.state, "account_id", None)

    if not account_id:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    if project_id:
        project_ids = {project_id}
    else:
        grpc_pool = request.app.state.grpc_pool
        project_ids = await get_user_projects(grpc_pool, account_id)

        if not project_ids:
            logger.warning(f"No projects found for account {account_id}")
            project_ids = set()

    stream = NotificationStream(config.settings.REDIS_URL, project_ids)
    await stream.subscribe()

    async def event_generator():
        heartbeat_task = None
        try:
            yield {
                "event": "connected",
                "data": json.dumps({
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "projects": list(project_ids)
                })
            }

            async def heartbeat():
                while True:
                    await asyncio.sleep(config.settings.NOTIFICATIONS_HEARTBEAT_INTERVAL)
                    yield {
                        "event": "heartbeat",
                        "data": json.dumps({"timestamp": datetime.utcnow().isoformat() + "Z"})
                    }

            heartbeat_task = asyncio.create_task(_generate_heartbeats())

            async for event in stream.listen():
                yield event

        except asyncio.CancelledError:
            logger.info(f"Client disconnected from notification stream (account: {account_id})")
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
            await stream.unsubscribe()

    async def _generate_heartbeats():
        while True:
            await asyncio.sleep(config.settings.NOTIFICATIONS_HEARTBEAT_INTERVAL)

    return EventSourceResponse(event_generator())


@router.get(
    "/notifications/health",
    summary="Check notification system health",
    description="Returns the current status of the notification system",
    response_description="Notification system health status",
    responses={
        200: {
            "description": "Health status",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "enabled": True,
                        "heartbeat_interval": 30
                    }
                }
            }
        }
    }
)
async def notifications_health():
    return {
        "status": "healthy",
        "enabled": config.settings.NOTIFICATIONS_ENABLED,
        "heartbeat_interval": config.settings.NOTIFICATIONS_HEARTBEAT_INTERVAL,
        "max_connections_per_user": config.settings.NOTIFICATIONS_MAX_CONNECTIONS_PER_USER
    }
