"""Read path for OTLP metric points.

Distinct from `metrics.py`, which serves metrics *derived from logs* (error
rate, log volume, endpoint latency). This module reads the `metric_points`
table - counters, gauges and histograms a user emitted explicitly through the
SDK's `metric_increment` / `metric_gauge` / `metric_histogram` or any stock
OpenTelemetry exporter.
"""

import datetime
import json
import typing

import sqlalchemy as sa

import query_service.database as database

SUM = 0
GAUGE = 1
HISTOGRAM = 2

TEMPORALITY_DELTA = 1
TEMPORALITY_CUMULATIVE = 2

_QUANTILE_AGGREGATIONS = {"p50": 0.50, "p95": 0.95, "p99": 0.99}
_PLAIN_AGGREGATIONS = frozenset({"avg", "sum", "min", "max", "count"})
VALID_AGGREGATIONS = _PLAIN_AGGREGATIONS | set(_QUANTILE_AGGREGATIONS)

_INTERVAL_SECONDS = {"1m": 60, "5m": 300, "1h": 3600, "1d": 86400}

_ROLLUP_THRESHOLD = datetime.timedelta(days=2)
_DEFAULT_WINDOW = datetime.timedelta(hours=1)

# A histogram's quantiles are interpolated from bucket_counts/explicit_bounds in
# Python, so those rows are fetched rather than aggregated in SQL. The cap keeps
# a pathological window (many series x a short export interval) from pulling an
# unbounded result set into memory.
_MAX_HISTOGRAM_ROWS = 50_000

MAX_TAG_VALUES_PER_KEY = 50


def _parse_iso(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _resolve_window(
    from_time: str | None, to_time: str | None
) -> tuple[datetime.datetime, datetime.datetime]:
    end = _parse_iso(to_time) if to_time else datetime.datetime.now(datetime.timezone.utc)
    start = _parse_iso(from_time) if from_time else end - _DEFAULT_WINDOW
    return start, end


def _resolve_interval(start: datetime.datetime, end: datetime.datetime, requested: str | None) -> str:
    if requested in _INTERVAL_SECONDS:
        return requested

    span = end - start
    if span <= datetime.timedelta(hours=2):
        return "1m"
    if span <= datetime.timedelta(hours=12):
        return "5m"
    if span <= datetime.timedelta(days=14):
        return "1h"
    return "1d"


def _bucket_expression(column: str, interval: str) -> str:
    seconds = _INTERVAL_SECONDS[interval]
    if seconds >= 3600:
        unit = "hour" if seconds == 3600 else "day"
        return f"date_trunc('{unit}', {column})"
    return f"to_timestamp(floor(extract(epoch from {column}) / {seconds}) * {seconds})"


async def list_metric_names(
    project_id: int,
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict:
    """Metric names a project has sent, with type, tag keys and last-seen.

    Users pick a name in code and have to find it again in the UI months later;
    without this they would have to remember the exact string they typed.
    """
    start, end = _resolve_window(from_time, to_time)

    async with database.get_logs_session() as session:
        result = await session.execute(
            sa.text("""
                SELECT name,
                       MAX(type)        AS type,
                       MAX(temporality) AS temporality,
                       MAX(ts)          AS last_seen,
                       COUNT(DISTINCT tags_hash) AS series_count,
                       jsonb_agg(DISTINCT tag_key) AS tag_keys
                FROM (
                    SELECT mp.name, mp.type, mp.temporality, mp.ts, mp.tags_hash, tag_key
                    FROM metric_points mp
                    LEFT JOIN LATERAL jsonb_object_keys(mp.tags) AS tag_key ON TRUE
                    WHERE mp.project_id = :project_id
                      AND mp.ts >= :start
                      AND mp.ts <= :end
                ) expanded
                GROUP BY name
                ORDER BY name
            """),
            {"project_id": project_id, "start": start, "end": end},
        )
        rows = result.fetchall()

    metrics = []
    for row in rows:
        tag_keys = [key for key in (row.tag_keys or []) if key is not None]
        metrics.append(
            {
                "name": row.name,
                "type": row.type or 0,
                "temporality": row.temporality or 0,
                "tag_keys": sorted(tag_keys),
                "last_seen": row.last_seen.isoformat() if row.last_seen else "",
                "series_count": row.series_count or 0,
            }
        )

    return {"project_id": project_id, "metrics": metrics}


async def get_metric_tags(
    project_id: int,
    name: str,
    from_time: str | None = None,
    to_time: str | None = None,
    max_values_per_key: int = MAX_TAG_VALUES_PER_KEY,
) -> dict:
    """Tag keys on one metric, each with a sample of its values.

    Feeds the group-by and filter pickers, so the values are capped per key and
    the cap is reported - a high-cardinality tag must not silently look complete.
    """
    start, end = _resolve_window(from_time, to_time)
    limit = max(1, min(max_values_per_key, MAX_TAG_VALUES_PER_KEY))

    async with database.get_logs_session() as session:
        result = await session.execute(
            sa.text("""
                SELECT tag.key AS key, tag.value AS value, COUNT(*) AS hits
                FROM metric_points mp,
                     LATERAL jsonb_each_text(mp.tags) AS tag(key, value)
                WHERE mp.project_id = :project_id
                  AND mp.name = :name
                  AND mp.ts >= :start
                  AND mp.ts <= :end
                GROUP BY tag.key, tag.value
                ORDER BY tag.key, hits DESC
            """),
            {"project_id": project_id, "name": name, "start": start, "end": end},
        )
        rows = result.fetchall()

    by_key: dict[str, list[str]] = {}
    for row in rows:
        by_key.setdefault(row.key, []).append(row.value)

    keys = [
        {
            "key": key,
            "values": values[:limit],
            "truncated": len(values) > limit,
        }
        for key, values in sorted(by_key.items())
    ]

    return {"project_id": project_id, "name": name, "keys": keys}


async def _describe_metric(session, project_id: int, name: str) -> tuple[int, int]:
    result = await session.execute(
        sa.text("""
            SELECT type, temporality
            FROM metric_points
            WHERE project_id = :project_id AND name = :name
            ORDER BY ts DESC
            LIMIT 1
        """),
        {"project_id": project_id, "name": name},
    )
    row = result.fetchone()
    if not row:
        return GAUGE, 0
    return row.type or 0, row.temporality or 0


def _group_by_selects(group_by: list[str]) -> tuple[str, dict]:
    """Render group-by tag keys as bound parameters, never as inlined SQL."""
    selects = []
    params = {}
    for index, key in enumerate(group_by):
        params[f"gb{index}"] = key
        selects.append(f"mp.tags->>:gb{index} AS gb{index}")
    return ", ".join(selects), params


def _series_tags(row, group_by: list[str]) -> dict[str, str]:
    return {
        key: getattr(row, f"gb{index}") or ""
        for index, key in enumerate(group_by)
    }


async def query_metric_series(
    project_id: int,
    name: str,
    tag_filters: dict[str, str] | None = None,
    group_by: list[str] | None = None,
    aggregation: str = "avg",
    from_time: str | None = None,
    to_time: str | None = None,
    interval: str | None = None,
) -> dict:
    """Bucketed time series for one metric, split by the requested tag keys."""
    tag_filters = tag_filters or {}
    group_by = group_by or []

    if aggregation not in VALID_AGGREGATIONS:
        raise ValueError(
            f"Unsupported aggregation {aggregation!r}. "
            f"Expected one of: {', '.join(sorted(VALID_AGGREGATIONS))}"
        )

    start, end = _resolve_window(from_time, to_time)
    resolved_interval = _resolve_interval(start, end, interval)

    async with database.get_logs_session() as session:
        metric_type, temporality = await _describe_metric(session, project_id, name)

        if metric_type == HISTOGRAM:
            series, histograms, truncated = await _query_histogram(
                session, project_id, name, tag_filters, group_by,
                aggregation, start, end, resolved_interval,
            )
            downsampled = False
        else:
            downsampled = _should_use_rollup(
                start, end, resolved_interval, aggregation, metric_type, temporality
            )
            series = await _query_numeric(
                session, project_id, name, tag_filters, group_by, aggregation,
                start, end, resolved_interval, metric_type, temporality, downsampled,
            )
            histograms = []
            truncated = False

    return {
        "project_id": project_id,
        "name": name,
        "type": metric_type,
        "temporality": temporality,
        "aggregation": aggregation,
        "interval": resolved_interval,
        "series": series,
        "histograms": histograms,
        "downsampled": downsampled,
        "truncated": truncated,
    }


def _should_use_rollup(
    start: datetime.datetime,
    end: datetime.datetime,
    interval: str,
    aggregation: str,
    metric_type: int,
    temporality: int,
) -> bool:
    """Whether metric_points_1h can answer this query instead of the raw table.

    The rollup stores count/sum/min/max/avg per hour, so it cannot serve a
    percentile (the source values are gone) and cannot serve a cumulative
    counter (differencing needs the individual points, in order).
    """
    if end - start <= _ROLLUP_THRESHOLD:
        return False
    if _INTERVAL_SECONDS[interval] < 3600:
        return False
    if aggregation in _QUANTILE_AGGREGATIONS:
        return False
    return not (metric_type == SUM and temporality == TEMPORALITY_CUMULATIVE)


def _numeric_value_expression(
    aggregation: str, metric_type: int, temporality: int
) -> tuple[str, str]:
    """SQL for the per-bucket value, plus the inner projection it needs.

    A cumulative counter holds a running total since process start, so summing
    raw values is meaningless - it has to be differenced per series first. A
    negative difference means the process restarted and the counter reset, in
    which case the new value *is* the increase since the reset (same rule
    Prometheus' increase() uses).
    """
    if metric_type == SUM and temporality == TEMPORALITY_CUMULATIVE:
        delta = (
            "CASE WHEN mp.value - LAG(mp.value) OVER "
            "(PARTITION BY mp.tags_hash ORDER BY mp.ts) < 0 "
            "THEN mp.value "
            "ELSE mp.value - LAG(mp.value) OVER "
            "(PARTITION BY mp.tags_hash ORDER BY mp.ts) END AS metric_value"
        )
        return delta, "SUM(COALESCE(metric_value, 0))"

    inner = "mp.value AS metric_value"

    if aggregation in _QUANTILE_AGGREGATIONS:
        quantile = _QUANTILE_AGGREGATIONS[aggregation]
        return inner, f"percentile_cont({quantile}) WITHIN GROUP (ORDER BY metric_value)"
    if aggregation == "count":
        return inner, "COUNT(metric_value)"
    return inner, f"{aggregation.upper()}(metric_value)"


_ROLLUP_VALUE_EXPRESSIONS = {
    "avg": "SUM(mp.sum_v) / NULLIF(SUM(mp.count), 0)",
    "sum": "SUM(mp.sum_v)",
    "min": "MIN(mp.min_v)",
    "max": "MAX(mp.max_v)",
    "count": "SUM(mp.count)",
}


async def _query_numeric_rollup(
    session,
    project_id: int,
    name: str,
    tag_filters: dict[str, str],
    group_by: list[str],
    aggregation: str,
    start: datetime.datetime,
    end: datetime.datetime,
    interval: str,
) -> list[dict]:
    # avg is recomputed from the summed count/sum rather than averaging the
    # stored avg_v: hourly buckets carry different point counts, so averaging
    # the averages weights a quiet hour the same as a busy one.
    value_expression = _ROLLUP_VALUE_EXPRESSIONS[aggregation]
    group_selects, group_params = _group_by_selects(group_by)

    select_parts = [_bucket_expression("mp.bucket", interval) + " AS bucket"]
    if group_selects:
        select_parts.append(group_selects)
    select_parts.append(f"{value_expression} AS value")

    group_columns = ", ".join(
        [_bucket_expression("mp.bucket", interval)]
        + [f"mp.tags->>:gb{i}" for i in range(len(group_by))]
    )

    params: dict[str, typing.Any] = {
        "project_id": project_id,
        "name": name,
        "start": start,
        "end": end,
        **group_params,
    }

    tag_predicate = ""
    if tag_filters:
        # CAST(), not `:param::jsonb` - SQLAlchemy's bindparam regex refuses to
        # match a name followed by ':' and silently binds a truncated name.
        tag_predicate = "AND mp.tags @> CAST(:tag_filters AS jsonb)"
        params["tag_filters"] = json.dumps(tag_filters)

    result = await session.execute(
        sa.text(f"""
            SELECT {", ".join(select_parts)}
            FROM metric_points_1h mp
            WHERE mp.project_id = :project_id
              AND mp.name = :name
              AND mp.bucket >= :start
              AND mp.bucket <= :end
              {tag_predicate}
            GROUP BY {group_columns}
            ORDER BY bucket
        """),
        params,
    )

    return _rows_to_series(result.fetchall(), group_by)


async def _query_numeric(
    session,
    project_id: int,
    name: str,
    tag_filters: dict[str, str],
    group_by: list[str],
    aggregation: str,
    start: datetime.datetime,
    end: datetime.datetime,
    interval: str,
    metric_type: int,
    temporality: int,
    use_rollup: bool,
) -> list[dict]:
    if use_rollup:
        return await _query_numeric_rollup(
            session, project_id, name, tag_filters, group_by,
            aggregation, start, end, interval,
        )

    inner_value, outer_value = _numeric_value_expression(aggregation, metric_type, temporality)
    group_selects, group_params = _group_by_selects(group_by)

    inner_projection = ", ".join(
        part for part in [_bucket_expression("mp.ts", interval) + " AS bucket",
                          group_selects, inner_value] if part
    )
    outer_groups = ", ".join(["bucket"] + [f"gb{i}" for i in range(len(group_by))])
    outer_selects = ", ".join(["bucket"] + [f"gb{i}" for i in range(len(group_by))])

    params: dict[str, typing.Any] = {
        "project_id": project_id,
        "name": name,
        "start": start,
        "end": end,
        **group_params,
    }

    tag_predicate = ""
    if tag_filters:
        # CAST(), not `:param::jsonb` - SQLAlchemy's bindparam regex refuses to
        # match a name followed by ':' and silently binds a truncated name.
        tag_predicate = "AND mp.tags @> CAST(:tag_filters AS jsonb)"
        params["tag_filters"] = json.dumps(tag_filters)

    result = await session.execute(
        sa.text(f"""
            WITH points AS (
                SELECT {inner_projection}
                FROM metric_points mp
                WHERE mp.project_id = :project_id
                  AND mp.name = :name
                  AND mp.ts >= :start
                  AND mp.ts <= :end
                  {tag_predicate}
            )
            SELECT {outer_selects}, {outer_value} AS value
            FROM points
            GROUP BY {outer_groups}
            ORDER BY bucket
        """),
        params,
    )
    rows = result.fetchall()

    return _rows_to_series(rows, group_by)


def _rows_to_series(rows, group_by: list[str]) -> list[dict]:
    grouped: dict[tuple, dict] = {}
    for row in rows:
        tags = _series_tags(row, group_by)
        key = tuple(sorted(tags.items()))
        series = grouped.setdefault(key, {"tags": tags, "points": []})
        series["points"].append(
            {
                "bucket": row.bucket.isoformat(),
                "value": float(row.value) if row.value is not None else 0.0,
            }
        )

    return list(grouped.values())


async def _query_histogram(
    session,
    project_id: int,
    name: str,
    tag_filters: dict[str, str],
    group_by: list[str],
    aggregation: str,
    start: datetime.datetime,
    end: datetime.datetime,
    interval: str,
) -> tuple[list[dict], list[dict], bool]:
    """Quantile time series plus a whole-window distribution, per series.

    Bucket arrays are summed element-wise in Python: the alternative is
    unnesting two JSONB arrays with ordinality and re-aggregating per bucket
    per series, which is markedly slower than the row fetch for the row counts
    this path actually sees.
    """
    group_selects, group_params = _group_by_selects(group_by)
    select_parts = [
        _bucket_expression("mp.ts", interval) + " AS bucket",
        "mp.bucket_counts AS bucket_counts",
        "mp.explicit_bounds AS explicit_bounds",
        "mp.count AS point_count",
        "mp.sum AS point_sum",
    ]
    if group_selects:
        select_parts.insert(1, group_selects)

    params: dict[str, typing.Any] = {
        "project_id": project_id,
        "name": name,
        "start": start,
        "end": end,
        "row_limit": _MAX_HISTOGRAM_ROWS + 1,
        **group_params,
    }

    tag_predicate = ""
    if tag_filters:
        # CAST(), not `:param::jsonb` - SQLAlchemy's bindparam regex refuses to
        # match a name followed by ':' and silently binds a truncated name.
        tag_predicate = "AND mp.tags @> CAST(:tag_filters AS jsonb)"
        params["tag_filters"] = json.dumps(tag_filters)

    result = await session.execute(
        sa.text(f"""
            SELECT {", ".join(select_parts)}
            FROM metric_points mp
            WHERE mp.project_id = :project_id
              AND mp.name = :name
              AND mp.ts >= :start
              AND mp.ts <= :end
              {tag_predicate}
            ORDER BY mp.ts
            LIMIT :row_limit
        """),
        params,
    )
    rows = result.fetchall()

    truncated = len(rows) > _MAX_HISTOGRAM_ROWS
    rows = rows[:_MAX_HISTOGRAM_ROWS]

    per_bucket: dict[tuple, dict] = {}
    per_series: dict[tuple, dict] = {}

    for row in rows:
        tags = _series_tags(row, group_by)
        series_key = tuple(sorted(tags.items()))
        bounds = _as_float_list(row.explicit_bounds)
        counts = _as_float_list(row.bucket_counts)
        if not counts:
            continue

        bucket_key = (series_key, row.bucket)
        bucket_state = per_bucket.setdefault(
            bucket_key, {"tags": tags, "bucket": row.bucket, "counts": [], "bounds": bounds,
                         "count": 0, "sum": 0.0}
        )
        _accumulate_counts(bucket_state, counts, bounds, row)

        series_state = per_series.setdefault(
            series_key, {"tags": tags, "counts": [], "bounds": bounds, "count": 0, "sum": 0.0}
        )
        _accumulate_counts(series_state, counts, bounds, row)

    series = _histogram_time_series(per_bucket, aggregation)
    histograms = [
        {
            "tags": state["tags"],
            "buckets": _to_buckets(state["counts"], state["bounds"]),
            "count": state["count"],
            "sum": state["sum"],
        }
        for state in per_series.values()
    ]

    return series, histograms, truncated


def _accumulate_counts(state: dict, counts: list[float], bounds: list[float], row) -> None:
    if not state["counts"]:
        state["counts"] = list(counts)
        state["bounds"] = bounds
    elif len(state["counts"]) == len(counts):
        state["counts"] = [a + b for a, b in zip(state["counts"], counts)]

    state["count"] += int(row.point_count or 0)
    state["sum"] += float(row.point_sum or 0.0)


def _histogram_time_series(per_bucket: dict, aggregation: str) -> list[dict]:
    grouped: dict[tuple, dict] = {}
    for (series_key, bucket), state in sorted(per_bucket.items(), key=lambda item: item[0][1]):
        series = grouped.setdefault(series_key, {"tags": state["tags"], "points": []})
        series["points"].append(
            {
                "bucket": bucket.isoformat(),
                "value": _histogram_value(state, aggregation),
            }
        )
    return list(grouped.values())


def _histogram_value(state: dict, aggregation: str) -> float:
    if aggregation == "count":
        return float(state["count"])
    if aggregation == "sum":
        return state["sum"]
    if aggregation == "avg":
        return state["sum"] / state["count"] if state["count"] else 0.0
    if aggregation in _QUANTILE_AGGREGATIONS:
        return _interpolate_quantile(
            state["counts"], state["bounds"], _QUANTILE_AGGREGATIONS[aggregation]
        )
    if aggregation == "min":
        return _first_populated_bound(state["counts"], state["bounds"])
    if aggregation == "max":
        return _interpolate_quantile(state["counts"], state["bounds"], 1.0)
    return state["sum"] / state["count"] if state["count"] else 0.0


def _interpolate_quantile(counts: list[float], bounds: list[float], quantile: float) -> float:
    """Linear interpolation within the bucket the quantile falls in.

    OTLP explicit-bucket histograms carry one more count than bound - the final
    count is the +Inf overflow, which has no upper edge to interpolate toward,
    so a quantile landing there reports the last finite bound.
    """
    total = sum(counts)
    if total <= 0:
        return 0.0

    target = total * quantile
    cumulative = 0.0
    lower = 0.0

    for index, count in enumerate(counts):
        if index >= len(bounds):
            return bounds[-1] if bounds else 0.0

        upper = bounds[index]
        if cumulative + count >= target:
            if count <= 0:
                return upper
            fraction = (target - cumulative) / count
            return lower + (upper - lower) * fraction

        cumulative += count
        lower = upper

    return bounds[-1] if bounds else 0.0


def _first_populated_bound(counts: list[float], bounds: list[float]) -> float:
    for index, count in enumerate(counts):
        if count > 0:
            return bounds[index] if index < len(bounds) else (bounds[-1] if bounds else 0.0)
    return 0.0


def _to_buckets(counts: list[float], bounds: list[float]) -> list[dict]:
    buckets = []
    for index, count in enumerate(counts):
        upper = bounds[index] if index < len(bounds) else float("inf")
        buckets.append({"upper_bound": upper, "count": count})
    return buckets


def _as_float_list(raw) -> list[float]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(raw, list):
        return []
    return [float(value) for value in raw]
