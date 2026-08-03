import datetime
import typing

import pydantic


class LogEntryResponse(pydantic.BaseModel):
    id: int = pydantic.Field(description="Unique log ID")
    project_id: int = pydantic.Field(description="Project ID")
    timestamp: datetime.datetime = pydantic.Field(description="Log timestamp")
    ingested_at: datetime.datetime = pydantic.Field(description="Time when log was ingested")
    level: str = pydantic.Field(description="Log level (debug, info, warning, error, critical)")
    log_type: str = pydantic.Field(
        description=(
            "Log type:\n"
            "- `console`: stdout/stderr output\n"
            "- `logger`: structured logging framework output\n"
            "- `exception`: caught exceptions with stack traces\n"
            "- `database`: database queries and operations\n"
            "- `endpoint`: API endpoint monitoring metrics\n"
            "- `custom`: application-specific logs"
        )
    )
    importance: str = pydantic.Field(description="Importance level (critical, high, standard, low)")
    environment: str | None = pydantic.Field(
        default=None, description="Environment (development, staging, production)"
    )
    release: str | None = pydantic.Field(default=None, description="Release version")
    message: str | None = pydantic.Field(default=None, description="Log message")
    error_type: str | None = pydantic.Field(
        default=None, description="Error type (e.g., ValueError, TypeError)"
    )
    error_message: str | None = pydantic.Field(default=None, description="Error message")
    stack_trace: str | None = pydantic.Field(default=None, description="Stack trace")
    attributes: dict | None = pydantic.Field(
        default=None, description="Additional attributes (JSON)"
    )
    sdk_version: str | None = pydantic.Field(default=None, description="SDK version")
    platform: str | None = pydantic.Field(
        default=None, description="Platform (e.g., Python, JavaScript)"
    )
    platform_version: str | None = pydantic.Field(default=None, description="Platform version")
    processing_time_ms: int | None = pydantic.Field(
        default=None, description="Processing time in milliseconds"
    )
    error_fingerprint: str | None = pydantic.Field(
        default=None, description="Error fingerprint (SHA-256 hash)"
    )
    method: str | None = pydantic.Field(default=None, description="HTTP method (GET, POST, etc.)")
    path: str | None = pydantic.Field(default=None, description="HTTP request path")
    status_code: int | None = pydantic.Field(default=None, description="HTTP response status code")
    duration_ms: int | None = pydantic.Field(
        default=None, description="Request duration in milliseconds"
    )
    client_channel: str | None = pydantic.Field(
        default=None,
        description=(
            "Caller classification: browser_navigation, browser_xhr, api_client, bot, unknown"
        ),
    )
    client_country: str | None = pydantic.Field(
        default=None, description="ISO 3166-1 alpha-2 country code resolved from the client IP"
    )

    model_config = pydantic.ConfigDict(from_attributes=True)


class AggregatedMetricDataResponse(pydantic.BaseModel):
    date: str = pydantic.Field(description="Date in YYYYMMDD format")
    hour: int | None = pydantic.Field(
        default=None, description="Hour (0-23) for hourly granularity"
    )
    endpoint_method: str | None = pydantic.Field(
        default=None, description="HTTP method (GET, POST, etc.)"
    )
    endpoint_path: str | None = pydantic.Field(default=None, description="Endpoint path")
    log_level: str | None = pydantic.Field(
        default=None, description="Log level (debug, info, warning, error, critical)"
    )
    log_type: str | None = pydantic.Field(
        default=None, description="Log type (console, logger, exception, etc.)"
    )
    log_count: int = pydantic.Field(description="Total number of logs")
    error_count: int = pydantic.Field(description="Number of errors")
    avg_duration_ms: float | None = pydantic.Field(
        default=None, description="Average duration in milliseconds"
    )
    min_duration_ms: int | None = pydantic.Field(
        default=None, description="Minimum duration in milliseconds"
    )
    max_duration_ms: int | None = pydantic.Field(
        default=None, description="Maximum duration in milliseconds"
    )
    p95_duration_ms: int | None = pydantic.Field(
        default=None, description="95th percentile duration in milliseconds"
    )
    p99_duration_ms: int | None = pydantic.Field(
        default=None, description="99th percentile duration in milliseconds"
    )


class AggregatedMetricsResponse(pydantic.BaseModel):
    project_id: int = pydantic.Field(description="Project ID")
    metric_type: str = pydantic.Field(description="Metric type (exception, endpoint, log_volume)")
    granularity: typing.Literal["hourly", "daily"] = pydantic.Field(description="Data granularity")
    start_date: str = pydantic.Field(description="Start date in YYYYMMDD format")
    end_date: str = pydantic.Field(description="End date in YYYYMMDD format")
    data: list[AggregatedMetricDataResponse] = pydantic.Field(description="Aggregated metrics data")


class ErrorListEntryResponse(pydantic.BaseModel):
    log_id: int = pydantic.Field(description="Log entry ID")
    project_id: int = pydantic.Field(description="Project ID")
    level: str = pydantic.Field(description="Log level (error, critical)")
    log_type: str = pydantic.Field(description="Log type (console, logger, exception, etc.)")
    message: str = pydantic.Field(description="Error message")
    error_type: str | None = pydantic.Field(
        default=None, description="Error type (e.g., ValueError)"
    )
    timestamp: datetime.datetime = pydantic.Field(description="Error timestamp")
    error_fingerprint: str | None = pydantic.Field(
        default=None, description="Error fingerprint for grouping"
    )
    attributes: dict | None = pydantic.Field(default=None, description="Additional attributes")
    sdk_version: str | None = pydantic.Field(default=None, description="SDK version")
    platform: str | None = pydantic.Field(default=None, description="Platform (e.g., Python)")
    group_key: str | None = pydantic.Field(
        default=None, description="Grouping key (fingerprint or hash)"
    )
    occurrence_count: int = pydantic.Field(
        default=1, description="Number of occurrences in time period"
    )
    first_seen: datetime.datetime | None = pydantic.Field(
        default=None, description="First occurrence timestamp"
    )
    last_seen: datetime.datetime | None = pydantic.Field(
        default=None, description="Most recent occurrence timestamp"
    )
    status_code: int | None = pydantic.Field(
        default=None, description="HTTP status code (if HTTP error)"
    )
    path: str | None = pydantic.Field(default=None, description="Request path (if HTTP error)")
    stack_trace: str | None = pydantic.Field(default=None, description="Stack trace")

    model_config = pydantic.ConfigDict(from_attributes=True)


class ErrorListResponse(pydantic.BaseModel):
    project_id: int = pydantic.Field(description="Project ID")
    errors: list[ErrorListEntryResponse] = pydantic.Field(description="List of errors")
    total: int = pydantic.Field(description="Total number of errors matching filters")
    has_more: bool = pydantic.Field(description="Whether there are more errors to fetch")


class LogsListResponse(pydantic.BaseModel):
    project_id: int = pydantic.Field(description="Project ID")
    logs: list[LogEntryResponse] = pydantic.Field(description="List of log entries")
    total: int | None = pydantic.Field(
        default=None, description="Total count — omitted when using limit+1 pagination"
    )
    has_more: bool = pydantic.Field(description="Whether there are more logs to fetch")
    next_cursor: str | None = pydantic.Field(
        default=None,
        description="Opaque cursor for the next page; pass back as ?cursor= to keep paging. "
        "Preferred over offset for deep pagination.",
    )


class LogFacetValueResponse(pydantic.BaseModel):
    value: str = pydantic.Field(description="Facet value (e.g. 'error', 'console', '4xx')")
    count: int = pydantic.Field(
        description="Number of logs matching this value under the current filters"
    )


class LogFacetsResponse(pydantic.BaseModel):
    project_id: int = pydantic.Field(description="Project ID")
    level: list[LogFacetValueResponse] = pydantic.Field(description="Counts by log level")
    log_type: list[LogFacetValueResponse] = pydantic.Field(description="Counts by log type")
    status_class: list[LogFacetValueResponse] = pydantic.Field(
        description="Counts by HTTP status class (2xx/3xx/4xx/5xx)"
    )
    environment: list[LogFacetValueResponse] = pydantic.Field(description="Counts by environment")
    client_channel: list[LogFacetValueResponse] = pydantic.Field(
        description="Counts by caller channel (browser_navigation, browser_xhr, api_client, bot)"
    )


class CountryBreakdownEntryResponse(pydantic.BaseModel):
    country: str = pydantic.Field(description="ISO 3166-1 alpha-2 country code")
    count: int = pydantic.Field(
        description="Number of logs from this country under the current filters"
    )


class CountryBreakdownResponse(pydantic.BaseModel):
    project_id: int = pydantic.Field(description="Project ID")
    countries: list[CountryBreakdownEntryResponse] = pydantic.Field(
        description="Top countries by log count, under the current filters"
    )


class BottleneckListEntryResponse(pydantic.BaseModel):
    route: str = pydantic.Field(description="Route as 'METHOD PATH' (e.g., 'GET /api/users')")
    value: float = pydantic.Field(description="Value of the selected statistic in ms")
    request_count: int = pydantic.Field(description="Total request count in the period")
    min_value: float | None = pydantic.Field(default=None, description="Min duration ms")
    max_value: float | None = pydantic.Field(default=None, description="Max duration ms")
    avg_value: float | None = pydantic.Field(default=None, description="Avg duration ms")
    median_value: float | None = pydantic.Field(default=None, description="Median duration ms")


class BottleneckListResponse(pydantic.BaseModel):
    project_id: int = pydantic.Field(description="Project ID")
    statistic: typing.Literal["min", "max", "avg", "median", "count"] = pydantic.Field(
        description="Statistic used for sorting and the value field"
    )
    sort: typing.Literal["asc", "desc"] = pydantic.Field(description="Sort direction")
    start_date: str = pydantic.Field(description="Start date in YYYYMMDD format")
    end_date: str = pydantic.Field(description="End date in YYYYMMDD format")
    max_value: float = pydantic.Field(
        description="Max stat value across all routes (for progress bar scaling)"
    )
    entries: list[BottleneckListEntryResponse] = pydantic.Field(
        description="Paginated route entries"
    )
    total: int = pydantic.Field(description="Total number of routes with data")
    has_more: bool = pydantic.Field(description="Whether there are more pages")
