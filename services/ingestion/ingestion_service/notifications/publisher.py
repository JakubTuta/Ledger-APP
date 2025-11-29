import json
from typing import Optional
from datetime import datetime
import redis.asyncio as redis
from pydantic import BaseModel

from ingestion_service.logger import logger

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
        self,
        project_id: int,
        notification: ErrorNotification
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
                        "error_type": notification.error_type
                    }
                )
            else:
                logger.debug(
                    f"Published error notification but no active subscribers",
                    extra={"channel": channel, "project_id": project_id}
                )

        except Exception as e:
            logger.error(
                f"Failed to publish error notification: {e}",
                extra={
                    "project_id": project_id,
                    "error": str(e)
                },
                exc_info=True
            )

    def should_notify(self, level: str, log_type: str, publish_errors: bool = True, publish_critical: bool = True) -> bool:
        if not self.enabled:
            return False

        if level == "critical" and publish_critical:
            return True

        if level == "error" and publish_errors:
            return True

        if log_type == "exception":
            return True

        return False
