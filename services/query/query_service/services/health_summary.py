import datetime
from datetime import timezone

import sqlalchemy as sa

import query_service.database as database
from query_service.services.aggregated_metrics import _parse_period

ERROR_RATE_WARN = 0.01
ERROR_RATE_CRIT = 0.05
P95_WARN_MS = 500
P95_CRIT_MS = 1500

VALID_PERIODS = {"today", "last7days", "last30days", "currentWeek", "currentMonth", "currentYear"}

# Totals, error counts and the request-weighted p95 all come out of the same
# aggregated_metrics slice, so one grouped scan answers them for every project
# the caller asked about. The p95 columns only exist on 'endpoint' rows, hence
# the FILTER rather than a second query.
_TOTALS_SQL = sa.text("""
    SELECT
        project_id,
        SUM(log_count) AS total_logs,
        SUM(error_count) AS total_errors,
        SUM(p95_duration_ms::FLOAT * log_count)
            FILTER (WHERE metric_type = 'endpoint' AND p95_duration_ms IS NOT NULL)
            / NULLIF(
                SUM(log_count) FILTER (
                    WHERE metric_type = 'endpoint' AND p95_duration_ms IS NOT NULL
                ), 0
            ) AS p95_ms
    FROM aggregated_metrics
    WHERE
        project_id IN :project_ids
        AND metric_type IN ('endpoint', 'exception')
        AND date >= :start_date
        AND date <= :end_date
    GROUP BY project_id
""").bindparams(sa.bindparam("project_ids", expanding=True))

_SPARKLINE_SQL = sa.text("""
    SELECT project_id, hour, SUM(log_count) AS vol
    FROM aggregated_metrics
    WHERE
        project_id IN :project_ids
        AND metric_type IN ('endpoint', 'exception')
        AND (date > :cutoff_date OR (date = :cutoff_date AND hour >= :cutoff_hour))
    GROUP BY project_id, hour
""").bindparams(sa.bindparam("project_ids", expanding=True))


def _compute_status(error_rate: float, p95_ms: float) -> str:
    if error_rate >= ERROR_RATE_CRIT or p95_ms >= P95_CRIT_MS:
        return "down"
    if error_rate >= ERROR_RATE_WARN or p95_ms >= P95_WARN_MS:
        return "degraded"
    return "healthy"


def _period_seconds(start_date: datetime.date, end_date: datetime.date) -> int:
    days = (end_date - start_date).days + 1
    return days * 86400


def _thresholds() -> dict:
    return {
        "error_rate_warn": ERROR_RATE_WARN,
        "error_rate_crit": ERROR_RATE_CRIT,
        "p95_warn_ms": P95_WARN_MS,
        "p95_crit_ms": P95_CRIT_MS,
    }


def _empty_summary(project_id: int, now: datetime.datetime) -> dict:
    return {
        "project_id": str(project_id),
        "error_rate": 0.0,
        "p95_ms": 0.0,
        "rps": 0.0,
        "status": "healthy",
        "sparkline": [0] * 24,
        "thresholds": _thresholds(),
        "generated_at": now.isoformat(),
    }


async def get_health_summaries(project_ids: list[int], period: str) -> list[dict]:
    """
    Per-project health tiles for the dashboard. Two grouped queries cover the
    whole project list; previously each project ran its own three queries on
    its own pooled connection, so a dashboard with N projects issued 3N
    round trips and held N connections at once.
    """
    if period not in VALID_PERIODS:
        raise ValueError(f"Invalid period '{period}'. Must be one of: {', '.join(VALID_PERIODS)}")

    now = datetime.datetime.now(timezone.utc)
    if not project_ids:
        return []

    start_date, end_date = _parse_period(period, None, None)
    sparkline_cutoff = now - datetime.timedelta(hours=23)

    async with database.get_logs_session() as session:
        totals_result = await session.execute(
            _TOTALS_SQL,
            {
                "project_ids": project_ids,
                "start_date": start_date.strftime("%Y%m%d"),
                "end_date": end_date.strftime("%Y%m%d"),
            },
        )
        totals = {row[0]: row for row in totals_result.fetchall()}

        sparkline_result = await session.execute(
            _SPARKLINE_SQL,
            {
                "project_ids": project_ids,
                "cutoff_date": sparkline_cutoff.strftime("%Y%m%d"),
                "cutoff_hour": sparkline_cutoff.hour,
            },
        )
        sparkline_rows = sparkline_result.fetchall()

    sparklines: dict[int, list[int]] = {}
    for project_id, row_hour, vol in sparkline_rows:
        buckets = sparklines.setdefault(project_id, [0] * 24)
        buckets[((row_hour or 0) - now.hour) % 24] += int(vol or 0)

    period_seconds = _period_seconds(start_date, end_date)

    summaries = []
    for project_id in project_ids:
        row = totals.get(project_id)
        if row is None:
            summaries.append(_empty_summary(project_id, now))
            continue

        total_logs = row[1] or 0
        total_errors = row[2] or 0
        p95_ms = float(row[3] or 0)
        error_rate = total_errors / total_logs if total_logs > 0 else 0.0

        summaries.append(
            {
                "project_id": str(project_id),
                "error_rate": error_rate,
                "p95_ms": p95_ms,
                "rps": total_logs / period_seconds,
                "status": _compute_status(error_rate, p95_ms),
                "sparkline": sparklines.get(project_id, [0] * 24),
                "thresholds": _thresholds(),
                "generated_at": now.isoformat(),
            }
        )

    return summaries
