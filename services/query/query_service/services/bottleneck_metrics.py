import datetime
from typing import Literal

import sqlalchemy as sa

import query_service.database as database
import query_service.models as models
import query_service.schemas as schemas


def _generate_time_buckets(
    start_date: datetime.date,
    end_date: datetime.date,
    granularity: Literal["hourly", "daily", "weekly", "monthly"],
) -> list[tuple[str, int | None]]:
    """
    Generate all expected time buckets for a date range and granularity.

    Returns list of tuples: (date_str, hour) where hour is None except for hourly granularity.
    Date format: YYYYMMDD
    """
    buckets = []

    if granularity == "hourly":
        date_str = start_date.strftime("%Y%m%d")
        for hour in range(24):
            buckets.append((date_str, hour))

    elif granularity == "daily":
        current = start_date
        while current <= end_date:
            buckets.append((current.strftime("%Y%m%d"), None))
            current += datetime.timedelta(days=1)

    elif granularity == "weekly":
        current = start_date
        while current <= end_date:
            buckets.append((current.strftime("%Y%m%d"), None))
            current += datetime.timedelta(weeks=1)

    elif granularity == "monthly":
        current = start_date
        while current <= end_date:
            buckets.append((current.strftime("%Y%m%d"), None))
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

    return buckets


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
        raise ValueError(
            "Either period or both period_from and period_to must be provided"
        )


async def get_bottleneck_metrics(
    project_id: int,
    routes: list[str],
    statistic: Literal["min", "max", "avg", "median", "count"],
    period: str | None = None,
    period_from: datetime.date | None = None,
    period_to: datetime.date | None = None,
    granularity: Literal["hourly", "daily", "weekly", "monthly"] = "daily",
) -> list[schemas.BottleneckMetricDataPoint]:
    if not routes:
        raise ValueError("At least one route must be provided")

    start_date, end_date = _parse_period(period, period_from, period_to)

    statistic_column_map = {
        "min": "min_duration_ms",
        "max": "max_duration_ms",
        "avg": "avg_duration_ms",
        "median": "median_duration_ms",
        "count": "log_count",
    }

    column_name = statistic_column_map[statistic]

    async with database.get_logs_session() as session:
        start_date_str = start_date.strftime("%Y%m%d")
        end_date_str = end_date.strftime("%Y%m%d")

        if granularity == "hourly":
            query = (
                sa.select(
                    models.BottleneckMetric.date,
                    models.BottleneckMetric.hour,
                    models.BottleneckMetric.route,
                    getattr(models.BottleneckMetric, column_name).label("value"),
                )
                .where(
                    models.BottleneckMetric.project_id == project_id,
                    models.BottleneckMetric.date == start_date_str,
                    models.BottleneckMetric.route.in_(routes),
                )
                .order_by(
                    models.BottleneckMetric.hour, models.BottleneckMetric.route
                )
            )

            result = await session.execute(query)
            rows = result.fetchall()

            metrics_map = {(row.date, row.hour, row.route): row for row in rows}

            all_buckets = _generate_time_buckets(start_date, end_date, granularity)

            filled_data = []
            for date_str, hour in all_buckets:
                for route in routes:
                    if (date_str, hour, route) in metrics_map:
                        row = metrics_map[(date_str, hour, route)]
                        filled_data.append(
                            schemas.BottleneckMetricDataPoint(
                                date=row.date,
                                hour=row.hour,
                                route=row.route,
                                value=row.value if row.value is not None else 0,
                            )
                        )
                    else:
                        filled_data.append(
                            schemas.BottleneckMetricDataPoint(
                                date=date_str,
                                hour=hour,
                                route=route,
                                value=0,
                            )
                        )

            return filled_data

        else:
            if statistic == "count":
                aggregation_expr = sa.func.sum(
                    getattr(models.BottleneckMetric, column_name)
                )
            elif statistic == "avg":
                aggregation_expr = sa.func.avg(
                    getattr(models.BottleneckMetric, column_name)
                )
            elif statistic == "min":
                aggregation_expr = sa.func.min(
                    getattr(models.BottleneckMetric, column_name)
                )
            elif statistic == "max":
                aggregation_expr = sa.func.max(
                    getattr(models.BottleneckMetric, column_name)
                )
            elif statistic == "median":
                aggregation_expr = sa.func.avg(
                    getattr(models.BottleneckMetric, column_name)
                )
            else:
                aggregation_expr = sa.func.avg(
                    getattr(models.BottleneckMetric, column_name)
                )

            query = (
                sa.select(
                    models.BottleneckMetric.date,
                    models.BottleneckMetric.route,
                    aggregation_expr.label("value"),
                )
                .where(
                    models.BottleneckMetric.project_id == project_id,
                    models.BottleneckMetric.date >= start_date_str,
                    models.BottleneckMetric.date <= end_date_str,
                    models.BottleneckMetric.route.in_(routes),
                )
                .group_by(models.BottleneckMetric.date, models.BottleneckMetric.route)
                .order_by(models.BottleneckMetric.date, models.BottleneckMetric.route)
            )

            result = await session.execute(query)
            rows = result.fetchall()

            metrics_map = {(row.date, row.route): row for row in rows}

            all_buckets = _generate_time_buckets(start_date, end_date, granularity)

            filled_data = []
            for date_str, _ in all_buckets:
                for route in routes:
                    if (date_str, route) in metrics_map:
                        row = metrics_map[(date_str, route)]
                        filled_data.append(
                            schemas.BottleneckMetricDataPoint(
                                date=row.date,
                                hour=None,
                                route=row.route,
                                value=row.value if row.value is not None else 0,
                            )
                        )
                    else:
                        filled_data.append(
                            schemas.BottleneckMetricDataPoint(
                                date=date_str,
                                hour=None,
                                route=route,
                                value=0,
                            )
                        )

            return filled_data
