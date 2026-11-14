def parse_cron_expression(cron_expr: str) -> dict[str, str]:
    """Split a 5-field crontab expression into the kwargs APScheduler's CronTrigger takes."""
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
