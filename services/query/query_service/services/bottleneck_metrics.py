import datetime
from typing import Literal

import sqlalchemy as sa

import query_service.database as database
import query_service.models as models
import query_service.schemas as schemas
from query_service.services.aggregated_metrics import _parse_period


async def get_bottleneck_list(
    project_id: int,
    statistic: Literal["min", "max", "avg", "median", "count"],
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

    weighted_avg = sa.func.sum(m.avg_duration_ms * m.log_count) / sa.func.nullif(
        sa.func.sum(m.log_count), 0
    )

    stat_expr_map = {
        "min": sa.func.min(sa.func.nullif(m.min_duration_ms, 0)),
        "max": sa.func.max(m.max_duration_ms),
        "avg": weighted_avg,
        "median": sa.func.avg(sa.func.nullif(m.median_duration_ms, 0)),
        "count": sa.func.sum(m.log_count),
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

        count_result = await session.execute(sa.select(sa.func.count()).select_from(agg_subq))
        total = count_result.scalar() or 0

        max_result = await session.execute(sa.select(sa.func.max(agg_subq.c.stat_value)))
        max_value = float(max_result.scalar() or 0)

        order_col = agg_subq.c.stat_value
        order_expr = (
            order_col.asc().nulls_last() if sort == "asc" else order_col.desc().nulls_last()
        )

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
