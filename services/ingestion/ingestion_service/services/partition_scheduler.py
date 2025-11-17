import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import ingestion_service.config as config
import ingestion_service.database as database
import ingestion_service.services.partition_manager as partition_manager

logger = logging.getLogger(__name__)


class PartitionScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.running = False

    async def create_future_partitions(self) -> None:
        try:
            logger.info("Running scheduled partition creation task...")

            async with database.get_session() as session:
                result = await partition_manager.ensure_all_partitions(
                    session,
                    months_ahead=config.settings.PARTITION_MONTHS_AHEAD,
                )

            logger.info(
                f"Scheduled partition creation complete: {result}"
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

        self.scheduler.add_job(
            self.create_future_partitions,
            trigger=CronTrigger(
                day=1,
                hour=0,
                minute=0,
            ),
            id="create_future_partitions",
            name="Create future log partitions",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        self.scheduler.add_job(
            self.create_future_partitions,
            trigger=CronTrigger(
                hour=0,
                minute=30,
            ),
            id="daily_partition_check",
            name="Daily partition check",
            replace_existing=True,
            misfire_grace_time=1800,
        )

        self.scheduler.start()
        self.running = True

        logger.info(
            "Partition scheduler started with 2 jobs:\n"
            "  1. Monthly partition creation (1st day of month at 00:00)\n"
            "  2. Daily partition check (every day at 00:30)"
        )

    def stop(self) -> None:
        if not self.running:
            return

        self.scheduler.shutdown(wait=True)
        self.running = False
        logger.info("Partition scheduler stopped")

    def get_jobs(self) -> list:
        return self.scheduler.get_jobs()


_scheduler_instance = None


def get_partition_scheduler() -> PartitionScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = PartitionScheduler()
    return _scheduler_instance
