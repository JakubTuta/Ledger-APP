import asyncio
import signal
import sys

import analytics_workers.config as config
import analytics_workers.database as database
import analytics_workers.health as health
import analytics_workers.jobs as jobs
import analytics_workers.redis_client as redis_client
import analytics_workers.utils.logging as logging_utils
import apscheduler.schedulers.asyncio as async_scheduler
import apscheduler.triggers.interval as interval_trigger

logger = logging_utils.setup_logging()
settings = config.get_settings()

scheduler = async_scheduler.AsyncIOScheduler(
    job_defaults={
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": settings.JOB_MISFIRE_GRACE_TIME,
    }
)


async def startup() -> None:
    logger.info("Analytics Workers starting...")

    try:
        await database.init_db()
        logger.info("Database connections initialized")

        await redis_client.init_redis()
        logger.info("Redis connection initialized")

        logger.info("Startup completed successfully")

    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        sys.exit(1)


async def shutdown(sig: signal.Signals | None = None) -> None:
    if sig:
        logger.info(f"Received signal {sig.name}, shutting down...")
    else:
        logger.info("Shutting down...")

    try:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")

        await database.close_db()
        logger.info("Database connections closed")

        await redis_client.close_redis()
        logger.info("Redis connection closed")

        logger.info("Shutdown completed successfully")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


def setup_jobs() -> None:
    scheduler.add_job(
        jobs.aggregate_error_rates,
        trigger=interval_trigger.IntervalTrigger(
            minutes=settings.ERROR_RATE_INTERVAL_MINUTES
        ),
        id="aggregate_error_rates",
        name="Aggregate Error Rates",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.aggregate_log_volumes,
        trigger=interval_trigger.IntervalTrigger(
            minutes=settings.LOG_VOLUME_INTERVAL_MINUTES
        ),
        id="aggregate_log_volumes",
        name="Aggregate Log Volumes",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.compute_top_errors,
        trigger=interval_trigger.IntervalTrigger(
            minutes=settings.TOP_ERRORS_INTERVAL_MINUTES
        ),
        id="compute_top_errors",
        name="Compute Top Errors",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.generate_usage_stats,
        trigger=interval_trigger.IntervalTrigger(
            minutes=settings.USAGE_STATS_INTERVAL_MINUTES
        ),
        id="generate_usage_stats",
        name="Generate Usage Stats",
        replace_existing=True,
    )

    logger.info(f"Registered {len(scheduler.get_jobs())} scheduled jobs")


async def main() -> None:
    await startup()

    setup_jobs()
    scheduler.start()

    job_list = scheduler.get_jobs()
    logger.info(f"Scheduler started with {len(job_list)} jobs:")
    for job in job_list:
        logger.info(f"  - {job.name} (ID: {job.id}, Trigger: {job.trigger})")

    loop = asyncio.get_event_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

    health_task = asyncio.create_task(health.health_check_loop())

    logger.info("Analytics Workers is running. Press Ctrl+C to stop.")

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        health_task.cancel()
        await shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
