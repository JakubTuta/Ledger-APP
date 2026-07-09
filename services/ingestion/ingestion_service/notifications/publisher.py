import json
import logging
import time
from typing import Optional
from datetime import datetime
import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ErrorNotification(BaseModel):
    log_id: Optional[str] = None
    project_id: int
    level: str
    log_type: str
    message: str
    error_type: Optional[str] = None
    timestamp: datetime
    error_fingerprint: Optional[str] = None
    attributes: dict = {}
    sdk_version: Optional[str] = None
    platform: Optional[str] = None


class NotificationPublisher:
    def __init__(self, redis_client: redis.Redis, enabled: bool = True):
        self.redis = redis_client
        self.enabled = enabled

    async def publish_error_notification(
        self, project_id: int, notification: ErrorNotification
    ) -> None:
        if not self.enabled:
            return

        try:
            channel = f"notifications:errors:{project_id}"
            message = notification.model_dump_json()

            published = await self.redis.publish(channel, message)

            if published > 0:
                logger.info(
                    f"Published error notification to {published} subscribers",
                    extra={
                        "channel": channel,
                        "project_id": project_id,
                        "level": notification.level,
                        "error_type": notification.error_type,
                    },
                )
            else:
                logger.debug(
                    "Published error notification but no active subscribers",
                    extra={"channel": channel, "project_id": project_id},
                )

        except Exception as e:
            logger.error(
                f"Failed to publish error notification: {e}",
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
        self._window: dict[int, tuple[int, int]] = {}  # project_id -> (second, count_in_second)

    def _allow(self, project_id: int) -> bool:
        now_second = int(time.time())
        window_second, count = self._window.get(project_id, (now_second, 0))
        if window_second != now_second:
            window_second, count = now_second, 0
        if count >= self.MAX_EVENTS_PER_PROJECT_PER_SECOND:
            self._window[project_id] = (window_second, count)
            return False
        self._window[project_id] = (window_second, count + 1)
        return True

    async def publish_tail_batch(self, project_id: int, records: list[dict]) -> None:
        if not self.enabled or not records:
            return

        channel = f"logs:tail:{project_id}"

        for record in records:
            if not self._allow(project_id):
                logger.debug(
                    "Tail sample cap reached; dropping remaining events in batch",
                    extra={"project_id": project_id},
                )
                break

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
            }

            try:
                await self.redis.publish(channel, json.dumps(summary, default=str))
            except Exception as e:
                logger.error(
                    f"Failed to publish tail event: {e}",
                    extra={"project_id": project_id},
                    exc_info=True,
                )
                break
