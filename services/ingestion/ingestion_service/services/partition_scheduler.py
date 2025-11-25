import asyncio
import logging

import ingestion_service.config as config
import ingestion_service.database as database
import ingestion_service.services.partition_manager as partition_manager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class PartitionScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.running = False

    async def create_future_partitions(self) -> None:
        try:
            async with database.get_session() as session:
                result = await partition_manager.ensure_all_partitions(
                    session,
                    months_ahead=config.settings.PARTITION_MONTHS_AHEAD,
                )

        except Exception as e:
            logger.error(
                f"Failed to create future partitions in scheduled task: {e}",
                exc_info=True,
            )

    def start(self) -> None:
        if self.running:
            logger.warning("Partition scheduler is already running")
            return

        create_cron = self._parse_cron_expression(
            config.settings.PARTITION_CREATE_CRON
        )
        check_cron = self._parse_cron_expression(config.settings.PARTITION_CHECK_CRON)

        self.scheduler.add_job(
            self.create_future_partitions,
            trigger=CronTrigger(**create_cron),
            id="create_future_partitions",
            name="Create future log partitions",
            replace_existing=True,
            misfire_grace_time=config.settings.PARTITION_MISFIRE_GRACE_TIME,
        )

        self.scheduler.add_job(
            self.create_future_partitions,
            trigger=CronTrigger(**check_cron),
            id="daily_partition_check",
            name="Daily partition check",
            replace_existing=True,
            misfire_grace_time=config.settings.PARTITION_MISFIRE_GRACE_TIME // 2,
        )

        logger.info("Scheduled partition management jobs:")
        logger.info(
            f"  - Create partitions: {config.settings.PARTITION_CREATE_CRON}"
        )
        logger.info(f"  - Daily check: {config.settings.PARTITION_CHECK_CRON}")

        self.scheduler.start()
        self.running = True

    @staticmethod
    def _parse_cron_expression(cron_expr: str) -> dict:
        parts = cron_expr.split()
        if len(parts) != 5:
            raise ValueError(
                f"Invalid cron expression: {cron_expr}. Expected 5 parts (minute hour day month day_of_week)"
            )

        return {
            "minute": parts[0],
            "hour": parts[1],
            "day": parts[2],
            "month": parts[3],
            "day_of_week": parts[4],
        }

    def stop(self) -> None:
        if not self.running:
            return

        self.scheduler.shutdown(wait=True)
        self.running = False

    def get_jobs(self) -> list:
        return self.scheduler.get_jobs()


_scheduler_instance = None


def get_partition_scheduler() -> PartitionScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = PartitionScheduler()
    return _scheduler_instance
