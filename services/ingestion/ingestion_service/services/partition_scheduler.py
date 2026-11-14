import logging

import ingestion_service.config as config
import ingestion_service.database as database
import ingestion_service.services.partition_manager as partition_manager
import ledger_common.cron as cron
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
                await partition_manager.ensure_all_partitions(
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

        check_cron = cron.parse_cron_expression(config.settings.PARTITION_CHECK_CRON)

        self.scheduler.add_job(
            self.create_future_partitions,
            trigger=CronTrigger(**check_cron),
            id="daily_partition_check",
            name="Daily partition check",
            replace_existing=True,
            misfire_grace_time=config.settings.PARTITION_MISFIRE_GRACE_TIME,
        )

        logger.info(f"Scheduled partition check: {config.settings.PARTITION_CHECK_CRON}")

        self.scheduler.start()
        self.running = True

    def stop(self) -> None:
        if not self.running:
            return

        self.scheduler.shutdown(wait=True)
        self.running = False


_scheduler_instance = None


def get_partition_scheduler() -> PartitionScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = PartitionScheduler()
    return _scheduler_instance
