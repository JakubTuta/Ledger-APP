import datetime
from typing import Literal

import sqlalchemy as sa

import query_service.database as database
import query_service.models as models
import query_service.schemas as schemas


async def get_aggregated_metrics(
    project_id: int,
    metric_type: Literal["exception", "endpoint", "log_volume"],
    period: str | None = None,
    period_from: datetime.date | None = None,
    period_to: datetime.date | None = None,
    endpoint_path: str | None = None,
) -> list[schemas.AggregatedMetricData]:
    start_date, end_date = _parse_period(period, period_from, period_to)

    is_single_day = start_date == end_date
    granularity = "hourly" if is_single_day else "daily"

    async with database.get_logs_session() as session:
        start_date_str = start_date.strftime("%Y%m%d")
        end_date_str = end_date.strftime("%Y%m%d")

        if granularity == "hourly":
            query = (
                sa.select(models.AggregatedMetric)
                .where(
                    models.AggregatedMetric.project_id == project_id,
                    models.AggregatedMetric.metric_type == metric_type,
                    models.AggregatedMetric.date == start_date_str,
                )
            )

            if endpoint_path is not None:
                query = query.where(models.AggregatedMetric.endpoint_path == endpoint_path)

            query = query.order_by(models.AggregatedMetric.hour)

            result = await session.execute(query)
            metrics = result.scalars().all()

            return [
                schemas.AggregatedMetricData(
                    date=m.date,
                    hour=m.hour,
                    endpoint_method=m.endpoint_method,
                    endpoint_path=m.endpoint_path,
                    log_level=m.log_level,
                    log_type=m.log_type,
                    log_count=m.log_count,
                    error_count=m.error_count,
                    avg_duration_ms=m.avg_duration_ms,
                    min_duration_ms=m.min_duration_ms,
                    max_duration_ms=m.max_duration_ms,
                    p95_duration_ms=m.p95_duration_ms,
                    p99_duration_ms=m.p99_duration_ms,
                )
                for m in metrics
            ]
        else:
            if metric_type == "endpoint":
                where_clauses = [
                    "project_id = :project_id",
                    "metric_type = :metric_type",
                    "date >= :start_date",
                    "date <= :end_date",
                ]
                params = {
                    "project_id": project_id,
                    "metric_type": metric_type,
                    "start_date": start_date_str,
                    "end_date": end_date_str,
                }

                if endpoint_path is not None:
                    where_clauses.append("endpoint_path = :endpoint_path")
                    params["endpoint_path"] = endpoint_path

                where_clause = " AND ".join(where_clauses)

                query = sa.text(f"""
                    SELECT
                        date,
                        endpoint_method,
                        endpoint_path,
                        NULL as log_level,
                        NULL as log_type,
                        SUM(log_count) as log_count,
                        SUM(error_count) as error_count,
                        AVG(avg_duration_ms) as avg_duration_ms,
                        MIN(min_duration_ms) as min_duration_ms,
                        MAX(max_duration_ms) as max_duration_ms,
                        AVG(p95_duration_ms) as p95_duration_ms,
                        AVG(p99_duration_ms) as p99_duration_ms
                    FROM aggregated_metrics
                    WHERE {where_clause}
                    GROUP BY date, endpoint_method, endpoint_path
                    ORDER BY date, endpoint_path, endpoint_method
                """)
            elif metric_type == "log_volume":
                query = sa.text("""
                    SELECT
                        date,
                        NULL as endpoint_method,
                        NULL as endpoint_path,
                        log_level,
                        log_type,
                        SUM(log_count) as log_count,
                        SUM(error_count) as error_count,
                        NULL as avg_duration_ms,
                        NULL as min_duration_ms,
                        NULL as max_duration_ms,
                        NULL as p95_duration_ms,
                        NULL as p99_duration_ms
                    FROM aggregated_metrics
                    WHERE
                        project_id = :project_id
                        AND metric_type = :metric_type
                        AND date >= :start_date
                        AND date <= :end_date
                    GROUP BY date, log_level, log_type
                    ORDER BY date, log_level, log_type
                """)
                params = {
                    "project_id": project_id,
                    "metric_type": metric_type,
                    "start_date": start_date_str,
                    "end_date": end_date_str,
                }
            else:
                query = sa.text("""
                    SELECT
                        date,
                        NULL as endpoint_method,
                        NULL as endpoint_path,
                        NULL as log_level,
                        NULL as log_type,
                        SUM(log_count) as log_count,
                        SUM(error_count) as error_count,
                        NULL as avg_duration_ms,
                        NULL as min_duration_ms,
                        NULL as max_duration_ms,
                        NULL as p95_duration_ms,
                        NULL as p99_duration_ms
                    FROM aggregated_metrics
                    WHERE
                        project_id = :project_id
                        AND metric_type = :metric_type
                        AND date >= :start_date
                        AND date <= :end_date
                    GROUP BY date
                    ORDER BY date
                """)
                params = {
                    "project_id": project_id,
                    "metric_type": metric_type,
                    "start_date": start_date_str,
                    "end_date": end_date_str,
                }

            result = await session.execute(query, params)

            rows = result.fetchall()

            return [
                schemas.AggregatedMetricData(
                    date=row[0],
                    hour=None,
                    endpoint_method=row[1],
                    endpoint_path=row[2],
                    log_level=row[3],
                    log_type=row[4],
                    log_count=row[5],
                    error_count=row[6],
                    avg_duration_ms=row[7],
                    min_duration_ms=row[8],
                    max_duration_ms=row[9],
                    p95_duration_ms=row[10],
                    p99_duration_ms=row[11],
                )
                for row in rows
            ]


def _parse_period(
    period: str | None,
    period_from: datetime.date | None,
    period_to: datetime.date | None,
) -> tuple[datetime.date, datetime.date]:
    today = datetime.date.today()

    if period:
        if period == "today":
            return today, today
        elif period == "last7days":
            return today - datetime.timedelta(days=6), today
        elif period == "last30days":
            return today - datetime.timedelta(days=29), today
        elif period == "currentWeek":
            start = today - datetime.timedelta(days=today.weekday())
            return start, today
        elif period == "currentMonth":
            start = today.replace(day=1)
            return start, today
        elif period == "currentYear":
            start = today.replace(month=1, day=1)
            return start, today
        else:
            raise ValueError(f"Invalid period: {period}")
    elif period_from and period_to:
        if period_from > period_to:
            raise ValueError("period_from must be before or equal to period_to")
        if period_from > today or period_to > today:
            raise ValueError("Dates cannot be in the future")
        return period_from, period_to
    else:
        raise ValueError("Either period or both period_from and period_to must be provided")
