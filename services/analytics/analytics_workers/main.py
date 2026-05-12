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
import apscheduler.triggers.cron as cron_trigger

logger = logging_utils.setup_logging()
settings = config.get_settings()

scheduler = async_scheduler.AsyncIOScheduler(
    job_defaults={
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": settings.ANALYTICS_JOB_MISFIRE_GRACE_TIME,
    }
)


async def startup() -> None:
    try:
        await database.init_db()

        await redis_client.init_redis()

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

        await database.close_db()

        await redis_client.close_redis()

    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


def setup_jobs() -> None:
    error_rate_cron = _parse_cron_expression(settings.ANALYTICS_ERROR_RATE_CRON)
    log_volume_cron = _parse_cron_expression(settings.ANALYTICS_LOG_VOLUME_CRON)
    top_errors_cron = _parse_cron_expression(settings.ANALYTICS_TOP_ERRORS_CRON)
    usage_stats_cron = _parse_cron_expression(settings.ANALYTICS_USAGE_STATS_CRON)
    hourly_metrics_cron = _parse_cron_expression(settings.ANALYTICS_HOURLY_METRICS_CRON)
    available_routes_cron = _parse_cron_expression(
        settings.ANALYTICS_AVAILABLE_ROUTES_CRON
    )
    bottleneck_metrics_cron = _parse_cron_expression(
        settings.ANALYTICS_BOTTLENECK_METRICS_CRON
    )
    lv1h_rollup_cron = _parse_cron_expression(settings.ANALYTICS_LOG_VOLUME_1H_ROLLUP_CRON)
    lv1d_rollup_cron = _parse_cron_expression(settings.ANALYTICS_LOG_VOLUME_1D_ROLLUP_CRON)
    partition_cron = _parse_cron_expression(settings.ANALYTICS_PARTITION_MANAGER_CRON)
    span_latency_cron = _parse_cron_expression(settings.ANALYTICS_SPAN_LATENCY_1H_CRON)
    cm5m_cron = _parse_cron_expression(settings.ANALYTICS_CUSTOM_METRICS_5M_CRON)
    cm1h_cron = _parse_cron_expression(settings.ANALYTICS_CUSTOM_METRICS_1H_CRON)
    cm1d_cron = _parse_cron_expression(settings.ANALYTICS_CUSTOM_METRICS_1D_CRON)
    alert_cron = _parse_cron_expression(settings.ANALYTICS_ALERT_EVALUATOR_CRON)
    cardinality_cron = _parse_cron_expression(settings.ANALYTICS_CARDINALITY_CHECK_CRON)
    notif_cleanup_cron = _parse_cron_expression(settings.ANALYTICS_NOTIFICATION_CLEANUP_CRON)

    scheduler.add_job(
        jobs.aggregate_error_rates,
        trigger=cron_trigger.CronTrigger(**error_rate_cron),
        id="aggregate_error_rates",
        name="Aggregate Error Rates",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.aggregate_log_volumes,
        trigger=cron_trigger.CronTrigger(**log_volume_cron),
        id="aggregate_log_volumes",
        name="Aggregate Log Volumes",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.compute_top_errors,
        trigger=cron_trigger.CronTrigger(**top_errors_cron),
        id="compute_top_errors",
        name="Compute Top Errors",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.generate_usage_stats,
        trigger=cron_trigger.CronTrigger(**usage_stats_cron),
        id="generate_usage_stats",
        name="Generate Usage Stats",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.aggregate_hourly_metrics,
        trigger=cron_trigger.CronTrigger(**hourly_metrics_cron),
        id="aggregate_hourly_metrics",
        name="Aggregate Hourly Metrics",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.update_available_routes,
        trigger=cron_trigger.CronTrigger(**available_routes_cron),
        id="update_available_routes",
        name="Update Available Routes",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.aggregate_bottleneck_metrics,
        trigger=cron_trigger.CronTrigger(**bottleneck_metrics_cron),
        id="aggregate_bottleneck_metrics",
        name="Aggregate Bottleneck Metrics",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.rollup_log_volume_1h,
        trigger=cron_trigger.CronTrigger(**lv1h_rollup_cron),
        id="rollup_log_volume_1h",
        name="Rollup Log Volume 1h",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.rollup_log_volume_1d,
        trigger=cron_trigger.CronTrigger(**lv1d_rollup_cron),
        id="rollup_log_volume_1d",
        name="Rollup Log Volume 1d",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.manage_partitions,
        trigger=cron_trigger.CronTrigger(**partition_cron),
        id="manage_partitions",
        name="Manage Partitions",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.rollup_span_latency_1h,
        trigger=cron_trigger.CronTrigger(**span_latency_cron),
        id="rollup_span_latency_1h",
        name="Rollup Span Latency 1h",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.rollup_custom_metrics_5m,
        trigger=cron_trigger.CronTrigger(**cm5m_cron),
        id="rollup_custom_metrics_5m",
        name="Rollup Custom Metrics 5m",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.rollup_custom_metrics_1h,
        trigger=cron_trigger.CronTrigger(**cm1h_cron),
        id="rollup_custom_metrics_1h",
        name="Rollup Custom Metrics 1h",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.rollup_custom_metrics_1d,
        trigger=cron_trigger.CronTrigger(**cm1d_cron),
        id="rollup_custom_metrics_1d",
        name="Rollup Custom Metrics 1d",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.evaluate_alert_rules,
        trigger=cron_trigger.CronTrigger(**alert_cron),
        id="evaluate_alert_rules",
        name="Evaluate Alert Rules",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.update_metric_series_cardinality,
        trigger=cron_trigger.CronTrigger(**cardinality_cron),
        id="update_metric_series_cardinality",
        name="Update Metric Series Cardinality",
        replace_existing=True,
    )

    scheduler.add_job(
        jobs.cleanup_expired_notifications,
        trigger=cron_trigger.CronTrigger(**notif_cleanup_cron),
        id="cleanup_expired_notifications",
        name="Cleanup Expired Notifications",
        replace_existing=True,
    )

    logger.info("Scheduled jobs with cron expressions:")
    logger.info(f"  - Aggregate Error Rates: {settings.ANALYTICS_ERROR_RATE_CRON}")
    logger.info(f"  - Aggregate Log Volumes: {settings.ANALYTICS_LOG_VOLUME_CRON}")
    logger.info(f"  - Compute Top Errors: {settings.ANALYTICS_TOP_ERRORS_CRON}")
    logger.info(f"  - Generate Usage Stats: {settings.ANALYTICS_USAGE_STATS_CRON}")
    logger.info(f"  - Aggregate Hourly Metrics: {settings.ANALYTICS_HOURLY_METRICS_CRON}")
    logger.info(f"  - Update Available Routes: {settings.ANALYTICS_AVAILABLE_ROUTES_CRON}")
    logger.info(f"  - Aggregate Bottleneck Metrics: {settings.ANALYTICS_BOTTLENECK_METRICS_CRON}")
    logger.info(f"  - Rollup Log Volume 1h: {settings.ANALYTICS_LOG_VOLUME_1H_ROLLUP_CRON}")
    logger.info(f"  - Rollup Log Volume 1d: {settings.ANALYTICS_LOG_VOLUME_1D_ROLLUP_CRON}")
    logger.info(f"  - Manage Partitions: {settings.ANALYTICS_PARTITION_MANAGER_CRON}")
    logger.info(f"  - Rollup Span Latency 1h: {settings.ANALYTICS_SPAN_LATENCY_1H_CRON}")
    logger.info(f"  - Rollup Custom Metrics 5m: {settings.ANALYTICS_CUSTOM_METRICS_5M_CRON}")
    logger.info(f"  - Rollup Custom Metrics 1h: {settings.ANALYTICS_CUSTOM_METRICS_1H_CRON}")
    logger.info(f"  - Rollup Custom Metrics 1d: {settings.ANALYTICS_CUSTOM_METRICS_1D_CRON}")
    logger.info(f"  - Evaluate Alert Rules: {settings.ANALYTICS_ALERT_EVALUATOR_CRON}")
    logger.info(f"  - Update Metric Series Cardinality: {settings.ANALYTICS_CARDINALITY_CHECK_CRON}")
    logger.info(f"  - Cleanup Expired Notifications: {settings.ANALYTICS_NOTIFICATION_CLEANUP_CRON}")


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


async def main() -> None:
    await startup()

    setup_jobs()
    scheduler.start()

    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

    health_task = asyncio.create_task(health.health_check_loop())

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        health_task.cancel()
        await shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
