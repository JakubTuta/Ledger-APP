import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncGenerator, Set

import fastapi
import grpc
import redis.asyncio as redis
from gateway_service import config
from gateway_service.proto import auth_pb2, auth_pb2_grpc
from sse_starlette.sse import EventSourceResponse

router = fastapi.APIRouter(tags=["Notifications"])
logger = logging.getLogger(__name__)


from pydantic import BaseModel, Field


class ProjectNotificationSettings(BaseModel):
    enabled: bool = Field(default=True, description="Enable notifications for this project")
    levels: list[str] = Field(
        default_factory=list,
        description="Filter by log levels. Only 'error' and 'critical' are published. Empty means both.",
    )
    types: list[str] = Field(
        default_factory=list,
        description="Filter by log types. Only 'exception' type is published. Empty means all published types.",
    )


class NotificationPreferences(BaseModel):
    enabled: bool = Field(default=True, description="Enable notifications globally")
    projects: dict[int, ProjectNotificationSettings] = Field(
        default_factory=dict, description="Per-project notification settings"
    )


class NotificationPreferencesResponse(BaseModel):
    enabled: bool
    projects: dict[int, ProjectNotificationSettings]


class NotificationStream:
    def __init__(self, redis_url: str, project_ids: Set[int], preferences: dict):
        self.redis_url = redis_url
        self.project_ids = project_ids
        self.preferences = preferences
        self.redis_client = None
        self.pubsub = None

    async def subscribe(self):
        self.redis_client = redis.Redis.from_url(
            self.redis_url, decode_responses=True, max_connections=10
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

    def should_send_notification(self, notification_data: dict) -> bool:
        if not self.preferences.get("enabled", True):
            return False

        project_id = notification_data.get("project_id")
        if not project_id:
            return True

        project_prefs = self.preferences.get("projects", {}).get(str(project_id))
        if not project_prefs:
            return True

        if not project_prefs.get("enabled", True):
            return False

        level_filter = project_prefs.get("levels", [])
        if level_filter:
            notification_level = notification_data.get("level", "").lower()
            if notification_level not in [l.lower() for l in level_filter]:
                return False

        type_filter = project_prefs.get("types", [])
        if type_filter:
            notification_type = notification_data.get("log_type", "")
            if notification_type not in type_filter:
                return False

        return True

    async def listen(self) -> AsyncGenerator[dict, None]:
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])

                        if self.should_send_notification(data):
                            yield {
                                "event": "error_notification",
                                "data": json.dumps(data),
                            }
                    except json.JSONDecodeError:
                        logger.error(
                            f"Failed to decode notification message: {message['data']}"
                        )
        except asyncio.CancelledError:
            logger.info("Notification stream cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in notification stream: {e}", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({"error": "Stream error occurred"}),
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


async def get_notification_preferences(grpc_pool, account_id: int) -> dict:
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)

        request = auth_pb2.GetNotificationPreferencesRequest(account_id=account_id)
        response = await stub.GetNotificationPreferences(request, timeout=5.0)

        preferences = {
            "enabled": response.preferences.enabled,
            "projects": {},
        }

        for project_id, settings in response.preferences.projects.items():
            preferences["projects"][str(project_id)] = {
                "enabled": settings.enabled,
                "levels": list(settings.levels),
                "types": list(settings.types),
            }

        logger.info(f"Retrieved notification preferences for account {account_id}")
        return preferences

    except grpc.RpcError as e:
        logger.error(
            f"gRPC error fetching notification preferences: {e.code()}", exc_info=True
        )
        return {"enabled": True, "projects": {}}
    except Exception as e:
        logger.error(f"Error fetching notification preferences: {e}", exc_info=True)
        return {"enabled": True, "projects": {}}


@router.get(
    "/notifications/preferences",
    response_model=NotificationPreferencesResponse,
    summary="Get notification preferences",
    description="""
Get your notification preferences including global settings and per-project filters.

**Authentication:** Required (API Key or Session Token)

**Response includes:**
- Global notification enabled/disabled status
- Per-project settings with level and type filters

**Example Response:**
```json
{
  "enabled": true,
  "projects": {
    "1": {
      "enabled": true,
      "levels": ["error", "critical"],
      "types": ["exception"]
    },
    "2": {
      "enabled": false,
      "levels": [],
      "types": []
    }
  }
}
```
    """,
    responses={
        200: {
            "description": "Notification preferences retrieved successfully",
        },
        401: {
            "description": "Authentication required",
            "content": {
                "application/json": {"example": {"detail": "Authentication required"}}
            },
        },
    },
)
async def get_preferences(request: fastapi.Request):
    account_id = getattr(request.state, "account_id", None)

    if not account_id:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    grpc_pool = request.app.state.grpc_pool
    preferences = await get_notification_preferences(grpc_pool, account_id)

    projects_typed = {}
    for project_id_str, settings in preferences.get("projects", {}).items():
        projects_typed[int(project_id_str)] = ProjectNotificationSettings(**settings)

    return NotificationPreferencesResponse(
        enabled=preferences.get("enabled", True), projects=projects_typed
    )


@router.put(
    "/notifications/preferences",
    response_model=NotificationPreferencesResponse,
    summary="Update notification preferences",
    description="""
Update your notification preferences including global settings and per-project filters.

**Authentication:** Required (API Key or Session Token)

**Request Body:**
```json
{
  "enabled": true,
  "projects": {
    "1": {
      "enabled": true,
      "levels": ["error", "critical"],
      "types": ["exception"]
    },
    "2": {
      "enabled": false,
      "levels": [],
      "types": []
    }
  }
}
```

**Filtering Rules:**
- If `enabled` is false, no notifications will be sent
- If a project has `enabled` false, no notifications for that project
- If `levels` is specified, only matching levels will be sent
- If `types` is specified, only matching types will be sent
- Empty lists mean no filtering (all published notifications)

**Important:** Only error/critical logs and exceptions are published to the notification system.
**Available Levels:** error, critical (only these are published)
**Available Types:** exception (only this type is published, though error/critical logs of any type also trigger notifications)
    """,
    responses={
        200: {
            "description": "Preferences updated successfully",
        },
        400: {
            "description": "Invalid preferences format",
            "content": {
                "application/json": {
                    "example": {"detail": "Preferences must be a valid dictionary"}
                }
            },
        },
        401: {
            "description": "Authentication required",
            "content": {
                "application/json": {"example": {"detail": "Authentication required"}}
            },
        },
    },
)
async def update_preferences(
    request: fastapi.Request, preferences: NotificationPreferences
):
    account_id = getattr(request.state, "account_id", None)

    if not account_id:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    grpc_pool = request.app.state.grpc_pool

    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)

        projects_map = {}
        for project_id, settings in preferences.projects.items():
            projects_map[project_id] = auth_pb2.ProjectNotificationSettings(
                enabled=settings.enabled,
                levels=settings.levels,
                types=settings.types,
            )

        proto_preferences = auth_pb2.NotificationPreferences(
            enabled=preferences.enabled, projects=projects_map
        )

        update_request = auth_pb2.UpdateNotificationPreferencesRequest(
            account_id=account_id, preferences=proto_preferences
        )
        response = await stub.UpdateNotificationPreferences(
            update_request, timeout=5.0
        )

        if not response.success:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail="Failed to update preferences",
            )

        updated_preferences = {}
        for project_id, settings in response.preferences.projects.items():
            updated_preferences[int(project_id)] = ProjectNotificationSettings(
                enabled=settings.enabled,
                levels=list(settings.levels),
                types=list(settings.types),
            )

        return NotificationPreferencesResponse(
            enabled=response.preferences.enabled, projects=updated_preferences
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error updating preferences: {e.code()}", exc_info=True)
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update preferences: {e.details()}",
        )
    except Exception as e:
        logger.error(f"Error updating preferences: {e}", exc_info=True)
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update preferences",
        )


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
                    "example": 'event: connected\\ndata: {"timestamp": "2025-01-15T10:00:00Z", "projects": [1, 2]}\\n\\n'
                }
            },
        },
        401: {
            "description": "Authentication required",
            "content": {
                "application/json": {"example": {"detail": "Authentication required"}}
            },
        },
        503: {
            "description": "Notifications disabled",
            "content": {
                "application/json": {
                    "example": {"detail": "Notifications are currently disabled"}
                }
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

    project_id = getattr(request.state, "project_id", None)
    account_id = getattr(request.state, "account_id", None)

    if not account_id:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    grpc_pool = request.app.state.grpc_pool

    if project_id:
        project_ids = {project_id}
    else:
        project_ids = await get_user_projects(grpc_pool, account_id)

        if not project_ids:
            logger.warning(f"No projects found for account {account_id}")
            project_ids = set()

    preferences = await get_notification_preferences(grpc_pool, account_id)

    stream = NotificationStream(config.settings.REDIS_URL, project_ids, preferences)
    await stream.subscribe()

    async def event_generator():
        heartbeat_task = None
        try:
            yield {
                "event": "connected",
                "data": json.dumps(
                    {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "projects": list(project_ids),
                    }
                ),
            }

            async def heartbeat():
                while True:
                    await asyncio.sleep(
                        config.settings.NOTIFICATIONS_HEARTBEAT_INTERVAL
                    )
                    yield {
                        "event": "heartbeat",
                        "data": json.dumps(
                            {"timestamp": datetime.utcnow().isoformat() + "Z"}
                        ),
                    }

            heartbeat_task = asyncio.create_task(_generate_heartbeats())

            async for event in stream.listen():
                yield event

        except asyncio.CancelledError:
            logger.info(
                f"Client disconnected from notification stream (account: {account_id})"
            )
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
            await stream.unsubscribe()

    async def _generate_heartbeats():
        while True:
            await asyncio.sleep(config.settings.NOTIFICATIONS_HEARTBEAT_INTERVAL)

    return EventSourceResponse(event_generator())
