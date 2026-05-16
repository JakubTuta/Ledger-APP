import datetime
from typing import Literal

import sqlalchemy as sa

import query_service.database as database
import query_service.models as models
import query_service.schemas as schemas


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


async def get_bottleneck_list(
    project_id: int,
    statistic: Literal["min", "max", "avg", "median"],
    sort: Literal["asc", "desc"],
    period: str | None = None,
    period_from: datetime.date | None = None,
    period_to: datetime.date | None = None,
    limit: int = 25,
    offset: int = 0,
    search: str | None = None,
) -> schemas.BottleneckListResponse:
    start_date, end_date = _parse_period(period, period_from, period_to)
    start_date_str = start_date.strftime("%Y%m%d")
    end_date_str = end_date.strftime("%Y%m%d")

    m = models.BottleneckMetric

    weighted_avg = (
        sa.func.sum(m.avg_duration_ms * m.log_count)
        / sa.func.nullif(sa.func.sum(m.log_count), 0)
    )

    stat_expr_map = {
        "min": sa.func.min(sa.func.nullif(m.min_duration_ms, 0)),
        "max": sa.func.max(m.max_duration_ms),
        "avg": weighted_avg,
        "median": sa.func.avg(sa.func.nullif(m.median_duration_ms, 0)),
    }

    stat_expr = stat_expr_map[statistic]

    base_where = [
        m.project_id == project_id,
        m.date >= start_date_str,
        m.date <= end_date_str,
    ]
    if search:
        base_where.append(m.route.ilike(f"%{search}%"))

    async with database.get_logs_session() as session:
        agg_subq = (
            sa.select(
                m.route.label("route"),
                sa.func.sum(m.log_count).label("request_count"),
                sa.func.min(sa.func.nullif(m.min_duration_ms, 0)).label("min_value"),
                sa.func.max(m.max_duration_ms).label("max_value"),
                weighted_avg.label("avg_value"),
                sa.func.avg(sa.func.nullif(m.median_duration_ms, 0)).label("median_value"),
                stat_expr.label("stat_value"),
            )
            .where(*base_where)
            .group_by(m.route)
            .having(sa.func.sum(m.log_count) > 0)
            .subquery("agg")
        )

        count_result = await session.execute(
            sa.select(sa.func.count()).select_from(agg_subq)
        )
        total = count_result.scalar() or 0

        max_result = await session.execute(
            sa.select(sa.func.max(agg_subq.c.stat_value))
        )
        max_value = float(max_result.scalar() or 0)

        order_col = agg_subq.c.stat_value
        order_expr = order_col.asc().nulls_last() if sort == "asc" else order_col.desc().nulls_last()

        rows_result = await session.execute(
            sa.select(agg_subq).order_by(order_expr).limit(limit).offset(offset)
        )
        rows = rows_result.all()

    entries = [
        schemas.BottleneckListEntry(
            route=row.route,
            value=float(row.stat_value) if row.stat_value is not None else 0.0,
            request_count=int(row.request_count),
            min_value=float(row.min_value) if row.min_value is not None else None,
            max_value=float(row.max_value) if row.max_value is not None else None,
            avg_value=float(row.avg_value) if row.avg_value is not None else None,
            median_value=float(row.median_value) if row.median_value is not None else None,
        )
        for row in rows
    ]

    return schemas.BottleneckListResponse(
        project_id=project_id,
        statistic=statistic,
        sort=sort,
        start_date=start_date_str,
        end_date=end_date_str,
        max_value=max_value,
        entries=entries,
        total=total,
        has_more=(offset + len(entries)) < total,
    )
