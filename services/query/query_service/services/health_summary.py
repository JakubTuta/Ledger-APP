import asyncio
import datetime
from datetime import timezone

import sqlalchemy as sa

import query_service.database as database
import query_service.models as models
from query_service.services.aggregated_metrics import _parse_period

ERROR_RATE_WARN = 0.01
ERROR_RATE_CRIT = 0.05
P95_WARN_MS = 500
P95_CRIT_MS = 1500

VALID_PERIODS = {"today", "last7days", "last30days", "currentWeek", "currentMonth", "currentYear"}


def _compute_status(error_rate: float, p95_ms: float) -> str:
    if error_rate >= ERROR_RATE_CRIT or p95_ms >= P95_CRIT_MS:
        return "down"
    if error_rate >= ERROR_RATE_WARN or p95_ms >= P95_WARN_MS:
        return "degraded"
    return "healthy"


def _period_seconds(start_date: datetime.date, end_date: datetime.date) -> int:
    days = (end_date - start_date).days + 1
    return days * 86400


async def _compute_project_summary(project_id: int, period: str) -> dict:
    start_date, end_date = _parse_period(period, None, None)
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    now = datetime.datetime.now(timezone.utc)
    sparkline_cutoff = (now - datetime.timedelta(hours=23)).strftime("%Y%m%d%H")

    async with database.get_logs_session() as session:
        agg_query = sa.text("""
            SELECT
                SUM(log_count) AS total_logs,
                SUM(error_count) AS total_errors,
                MAX(p95_duration_ms) AS p95_ms
            FROM aggregated_metrics
            WHERE
                project_id = :project_id
                AND metric_type IN ('endpoint', 'exception')
                AND date >= :start_date
                AND date <= :end_date
        """)
        agg_result = await session.execute(
            agg_query,
            {"project_id": project_id, "start_date": start_str, "end_date": end_str},
        )
        row = agg_result.fetchone()

        total_logs = row[0] or 0
        total_errors = row[1] or 0
        p95_ms = float(row[2] or 0)

        error_rate = total_errors / total_logs if total_logs > 0 else 0.0
        rps = total_logs / _period_seconds(start_date, end_date)

        sparkline_query = sa.text("""
            SELECT date, hour, SUM(log_count) AS vol
            FROM aggregated_metrics
            WHERE
                project_id = :project_id
                AND metric_type IN ('endpoint', 'exception')
                AND (date > :cutoff_date OR (date = :cutoff_date AND hour >= :cutoff_hour))
            GROUP BY date, hour
            ORDER BY date, hour
        """)
        cutoff_date = (now - datetime.timedelta(hours=23)).strftime("%Y%m%d")
        cutoff_hour = (now - datetime.timedelta(hours=23)).hour

        sparkline_result = await session.execute(
            sparkline_query,
            {
                "project_id": project_id,
                "cutoff_date": cutoff_date,
                "cutoff_hour": cutoff_hour,
            },
        )
        sparkline_rows = sparkline_result.fetchall()

    buckets: dict[int, int] = {}
    current_hour = now.hour
    for srow in sparkline_rows:
        row_hour = srow[1] if srow[1] is not None else 0
        bucket_index = (row_hour - current_hour) % 24
        buckets[bucket_index] = buckets.get(bucket_index, 0) + int(srow[2] or 0)

    sparkline = [buckets.get(i, 0) for i in range(24)]

    return {
        "project_id": str(project_id),
        "error_rate": error_rate,
        "p95_ms": p95_ms,
        "rps": rps,
        "status": _compute_status(error_rate, p95_ms),
        "sparkline": sparkline,
        "thresholds": {
            "error_rate_warn": ERROR_RATE_WARN,
            "error_rate_crit": ERROR_RATE_CRIT,
            "p95_warn_ms": P95_WARN_MS,
            "p95_crit_ms": P95_CRIT_MS,
        },
        "generated_at": now.isoformat(),
    }


async def get_health_summaries(project_ids: list[int], period: str) -> list[dict]:
    if period not in VALID_PERIODS:
        raise ValueError(f"Invalid period '{period}'. Must be one of: {', '.join(VALID_PERIODS)}")

    results = await asyncio.gather(
        *[_compute_project_summary(pid, period) for pid in project_ids],
        return_exceptions=True,
    )

    summaries = []
    for pid, result in zip(project_ids, results):
        if isinstance(result, Exception):
            summaries.append({
                "project_id": str(pid),
                "error_rate": 0.0,
                "p95_ms": 0.0,
                "rps": 0.0,
                "status": "down",
                "sparkline": [0] * 24,
                "thresholds": {
                    "error_rate_warn": ERROR_RATE_WARN,
                    "error_rate_crit": ERROR_RATE_CRIT,
                    "p95_warn_ms": P95_WARN_MS,
                    "p95_crit_ms": P95_CRIT_MS,
                },
                "generated_at": datetime.datetime.now(timezone.utc).isoformat(),
            })
        else:
            summaries.append(result)

    return summaries
