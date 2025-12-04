import datetime
import typing

import pydantic


class LogEntryResponse(pydantic.BaseModel):
    id: int = pydantic.Field(description="Unique log ID")
    project_id: int = pydantic.Field(description="Project ID")
    timestamp: datetime.datetime = pydantic.Field(description="Log timestamp")
    ingested_at: datetime.datetime = pydantic.Field(
        description="Time when log was ingested"
    )
    level: str = pydantic.Field(
        description="Log level (debug, info, warning, error, critical)"
    )
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
    importance: str = pydantic.Field(
        description="Importance level (critical, high, standard, low)"
    )
    environment: typing.Optional[str] = pydantic.Field(
        default=None, description="Environment (development, staging, production)"
    )
    release: typing.Optional[str] = pydantic.Field(
        default=None, description="Release version"
    )
    message: typing.Optional[str] = pydantic.Field(
        default=None, description="Log message"
    )
    error_type: typing.Optional[str] = pydantic.Field(
        default=None, description="Error type (e.g., ValueError, TypeError)"
    )
    error_message: typing.Optional[str] = pydantic.Field(
        default=None, description="Error message"
    )
    stack_trace: typing.Optional[str] = pydantic.Field(
        default=None, description="Stack trace"
    )
    attributes: typing.Optional[dict] = pydantic.Field(
        default=None, description="Additional attributes (JSON)"
    )
    sdk_version: typing.Optional[str] = pydantic.Field(
        default=None, description="SDK version"
    )
    platform: typing.Optional[str] = pydantic.Field(
        default=None, description="Platform (e.g., Python, JavaScript)"
    )
    platform_version: typing.Optional[str] = pydantic.Field(
        default=None, description="Platform version"
    )
    processing_time_ms: typing.Optional[int] = pydantic.Field(
        default=None, description="Processing time in milliseconds"
    )
    error_fingerprint: typing.Optional[str] = pydantic.Field(
        default=None, description="Error fingerprint (SHA-256 hash)"
    )

    model_config = pydantic.ConfigDict(from_attributes=True)


class AggregatedMetricDataResponse(pydantic.BaseModel):
    date: str = pydantic.Field(description="Date in YYYYMMDD format")
    hour: typing.Optional[int] = pydantic.Field(
        default=None, description="Hour (0-23) for hourly granularity"
    )
    endpoint_method: typing.Optional[str] = pydantic.Field(
        default=None, description="HTTP method (GET, POST, etc.)"
    )
    endpoint_path: typing.Optional[str] = pydantic.Field(
        default=None, description="Endpoint path"
    )
    log_level: typing.Optional[str] = pydantic.Field(
        default=None, description="Log level (debug, info, warning, error, critical)"
    )
    log_type: typing.Optional[str] = pydantic.Field(
        default=None, description="Log type (console, logger, exception, etc.)"
    )
    log_count: int = pydantic.Field(description="Total number of logs")
    error_count: int = pydantic.Field(description="Number of errors")
    avg_duration_ms: typing.Optional[float] = pydantic.Field(
        default=None, description="Average duration in milliseconds"
    )
    min_duration_ms: typing.Optional[int] = pydantic.Field(
        default=None, description="Minimum duration in milliseconds"
    )
    max_duration_ms: typing.Optional[int] = pydantic.Field(
        default=None, description="Maximum duration in milliseconds"
    )
    p95_duration_ms: typing.Optional[int] = pydantic.Field(
        default=None, description="95th percentile duration in milliseconds"
    )
    p99_duration_ms: typing.Optional[int] = pydantic.Field(
        default=None, description="99th percentile duration in milliseconds"
    )


class AggregatedMetricsResponse(pydantic.BaseModel):
    project_id: int = pydantic.Field(description="Project ID")
    metric_type: str = pydantic.Field(description="Metric type (exception, endpoint, log_volume)")
    granularity: typing.Literal["hourly", "daily"] = pydantic.Field(
        description="Data granularity"
    )
    start_date: str = pydantic.Field(description="Start date in YYYYMMDD format")
    end_date: str = pydantic.Field(description="End date in YYYYMMDD format")
    data: list[AggregatedMetricDataResponse] = pydantic.Field(
        description="Aggregated metrics data"
    )


class ErrorListEntryResponse(pydantic.BaseModel):
    log_id: int = pydantic.Field(description="Log entry ID")
    project_id: int = pydantic.Field(description="Project ID")
    level: str = pydantic.Field(description="Log level (error, critical)")
    log_type: str = pydantic.Field(description="Log type (console, logger, exception, etc.)")
    message: str = pydantic.Field(description="Error message")
    error_type: typing.Optional[str] = pydantic.Field(default=None, description="Error type (e.g., ValueError)")
    timestamp: datetime.datetime = pydantic.Field(description="Error timestamp")
    error_fingerprint: typing.Optional[str] = pydantic.Field(default=None, description="Error fingerprint for grouping")
    attributes: typing.Optional[dict] = pydantic.Field(default=None, description="Additional attributes")
    sdk_version: typing.Optional[str] = pydantic.Field(default=None, description="SDK version")
    platform: typing.Optional[str] = pydantic.Field(default=None, description="Platform (e.g., Python)")

    model_config = pydantic.ConfigDict(from_attributes=True)


class ErrorListResponse(pydantic.BaseModel):
    project_id: int = pydantic.Field(description="Project ID")
    errors: list[ErrorListEntryResponse] = pydantic.Field(description="List of errors")
    total: int = pydantic.Field(description="Total number of errors matching filters")
    has_more: bool = pydantic.Field(description="Whether there are more errors to fetch")


class LogsListResponse(pydantic.BaseModel):
    project_id: int = pydantic.Field(description="Project ID")
    logs: list[LogEntryResponse] = pydantic.Field(description="List of log entries")
    total: int = pydantic.Field(description="Total number of logs matching filters")
    has_more: bool = pydantic.Field(description="Whether there are more logs to fetch")
