import json
import logging
import time
from datetime import datetime

import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ErrorNotification(BaseModel):
    log_id: str | None = None
    project_id: int
    level: str
    log_type: str
    message: str
    error_type: str | None = None
    timestamp: datetime
    error_fingerprint: str | None = None
    attributes: dict = {}
    sdk_version: str | None = None
    platform: str | None = None


class PerSecondBudget:
    """How many events each project may still emit in the current second."""

    def __init__(self, per_second: int):
        self.per_second = per_second
        self._window: dict[int, tuple[int, int]] = {}  # project_id -> (second, used)

    def take(self, project_id: int, wanted: int) -> int:
        now_second = int(time.time())
        window_second, used = self._window.get(project_id, (now_second, 0))
        if window_second != now_second:
            window_second, used = now_second, 0
        granted = max(0, min(wanted, self.per_second - used))
        self._window[project_id] = (window_second, used + granted)
        return granted


class NotificationPublisher:
    # Live error notifications are read by people: past a few per second per
    # project a dashboard cannot show them, while an error storm used to cost one
    # PUBLISH - and one SSE event in every open tab - per error log.
    MAX_NOTIFICATIONS_PER_PROJECT_PER_SECOND = 20

    def __init__(self, redis_client: redis.Redis, enabled: bool = True):
        self.redis = redis_client
        self.enabled = enabled
        self._budget = PerSecondBudget(self.MAX_NOTIFICATIONS_PER_PROJECT_PER_SECOND)

    async def publish_error_notification(
        self, project_id: int, notification: ErrorNotification
    ) -> None:
        await self.publish_error_notifications(project_id, [notification])

    async def publish_error_notifications(
        self, project_id: int, notifications: list[ErrorNotification]
    ) -> None:
        """Publish up to the project's per-second budget, in one pipelined round trip."""
        if not self.enabled or not notifications:
            return

        granted = self._budget.take(project_id, len(notifications))
        if granted < len(notifications):
            logger.debug(
                "Error notification budget reached; skipping the rest of the batch",
                extra={"project_id": project_id, "skipped": len(notifications) - granted},
            )
        if granted == 0:
            return

        channel = f"notifications:errors:{project_id}"
        messages = [notification.model_dump_json() for notification in notifications[:granted]]
        try:
            if len(messages) == 1:
                await self.redis.publish(channel, messages[0])
            else:
                pipe = self.redis.pipeline(transaction=False)
                for message in messages:
                    pipe.publish(channel, message)
                await pipe.execute()
        except Exception as e:
            logger.error(
                f"Failed to publish error notifications: {e}",
                extra={"project_id": project_id, "error": str(e)},
                exc_info=True,
            )

    def should_notify(
        self, level: str, log_type: str, publish_errors: bool = True, publish_critical: bool = True
    ) -> bool:
        if not self.enabled:
            return False

        if level == "critical" and publish_critical:
            return True

        if level == "error" and publish_errors:
            return True

        if log_type == "exception":
            return True

        return False


class TailPublisher:
    """Publishes compact per-log summaries to `logs:tail:{project_id}` for the
    gateway's live-tail SSE route (GET /api/v1/logs/tail), mirroring
    NotificationPublisher's Redis pub/sub pattern. Unlike error notifications,
    every accepted log is a candidate event, so a per-project sample cap keeps
    a bursty producer from flooding subscribers or the Redis pub/sub channel.
    """

    MAX_EVENTS_PER_PROJECT_PER_SECOND = 50

    def __init__(self, redis_client: redis.Redis, enabled: bool = True):
        self.redis = redis_client
        self.enabled = enabled
        self._budget = PerSecondBudget(self.MAX_EVENTS_PER_PROJECT_PER_SECOND)

    async def publish_tail_batch(self, project_id: int, records: list[dict]) -> None:
        if not self.enabled or not records:
            return

        granted = self._budget.take(project_id, len(records))
        if granted < len(records):
            logger.debug(
                "Tail sample cap reached; dropping remaining events in batch",
                extra={"project_id": project_id},
            )
        if granted == 0:
            return

        channel = f"logs:tail:{project_id}"
        pipe = self.redis.pipeline(transaction=False)
        for record in records[:granted]:
            summary = {
                "id": record.get("log_id"),
                "project_id": project_id,
                "timestamp": record["timestamp"].isoformat(),
                "ingested_at": record["ingested_at"].isoformat(),
                "level": record["level"],
                "log_type": record["log_type"],
                "importance": record.get("importance"),
                "environment": record.get("environment"),
                "message": record.get("message"),
                "error_type": record.get("error_type"),
                "error_fingerprint": record.get("error_fingerprint"),
                "method": record.get("method"),
                "path": record.get("path"),
                "status_code": record.get("status_code"),
                "duration_ms": record.get("duration_ms"),
                "service_name": record.get("service_name"),
                "trace_id": record.get("trace_id"),
            }
            pipe.publish(channel, json.dumps(summary, default=str))

        try:
            await pipe.execute()
        except Exception as e:
            logger.error(
                f"Failed to publish tail events: {e}",
                extra={"project_id": project_id},
                exc_info=True,
            )
