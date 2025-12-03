import datetime
import typing

import pydantic


class LogFilters(pydantic.BaseModel):
    start_time: datetime.datetime | None = None
    end_time: datetime.datetime | None = None
    level: typing.Literal["debug", "info", "warning", "error", "critical"] | None = None
    log_type: typing.Literal[
        "console", "logger", "exception", "network", "database", "endpoint", "custom"
    ] | None = None
    environment: str | None = None
    error_fingerprint: str | None = None


class Pagination(pydantic.BaseModel):
    limit: int = pydantic.Field(default=100, ge=1, le=1000)
    offset: int = pydantic.Field(default=0, ge=0)


class LogResponse(pydantic.BaseModel):
    id: int
    project_id: int
    timestamp: datetime.datetime
    ingested_at: datetime.datetime
    level: str
    log_type: str
    importance: str
    environment: str | None
    release: str | None
    message: str | None
    error_type: str | None
    error_message: str | None
    stack_trace: str | None
    attributes: dict | None
    sdk_version: str | None
    platform: str | None
    platform_version: str | None
    processing_time_ms: int | None
    error_fingerprint: str | None

    model_config = pydantic.ConfigDict(from_attributes=True)

    @pydantic.field_validator("error_fingerprint", mode="before")
    @classmethod
    def strip_error_fingerprint(cls, v: str | None) -> str | None:
        if v is not None and isinstance(v, str):
            return v.strip()
        return v


class LogsQueryResponse(pydantic.BaseModel):
    logs: list[LogResponse]
    total: int
    has_more: bool


class ErrorGroupResponse(pydantic.BaseModel):
    id: int
    project_id: int
    fingerprint: str
    error_type: str
    error_message: str | None
    first_seen: datetime.datetime
    last_seen: datetime.datetime
    occurrence_count: int
    status: str
    sample_log_id: int | None

    model_config = pydantic.ConfigDict(from_attributes=True)

    @pydantic.field_validator("fingerprint", mode="before")
    @classmethod
    def strip_fingerprint(cls, v: str | None) -> str | None:
        if v is not None and isinstance(v, str):
            return v.strip()
        return v


class ErrorRateData(pydantic.BaseModel):
    timestamp: datetime.datetime
    error_count: int
    critical_count: int


class ErrorRateResponse(pydantic.BaseModel):
    project_id: int
    interval: str
    data: list[ErrorRateData]


class LogVolumeData(pydantic.BaseModel):
    timestamp: datetime.datetime
    debug: int
    info: int
    warning: int
    error: int
    critical: int


class LogVolumeResponse(pydantic.BaseModel):
    project_id: int
    interval: str
    data: list[LogVolumeData]


class TopErrorData(pydantic.BaseModel):
    fingerprint: str
    error_type: str
    error_message: str | None
    occurrence_count: int
    first_seen: datetime.datetime
    last_seen: datetime.datetime
    status: str
    sample_log_id: int | None

    @pydantic.field_validator("fingerprint", mode="before")
    @classmethod
    def strip_fingerprint(cls, v: str | None) -> str | None:
        if v is not None and isinstance(v, str):
            return v.strip()
        return v


class TopErrorsResponse(pydantic.BaseModel):
    project_id: int
    errors: list[TopErrorData]


class UsageStatsData(pydantic.BaseModel):
    date: datetime.date
    log_count: int
    daily_quota: int
    quota_used_percent: float


class UsageStatsResponse(pydantic.BaseModel):
    project_id: int
    usage: list[UsageStatsData]


class AggregatedMetricData(pydantic.BaseModel):
    date: str
    hour: int | None = None
    endpoint_method: str | None = None
    endpoint_path: str | None = None
    log_level: str | None = None
    log_type: str | None = None
    log_count: int
    error_count: int
    avg_duration_ms: float | None = None
    min_duration_ms: int | None = None
    max_duration_ms: int | None = None
    p95_duration_ms: int | None = None
    p99_duration_ms: int | None = None


class AggregatedMetricsResponse(pydantic.BaseModel):
    project_id: int
    metric_type: str
    granularity: typing.Literal["hourly", "daily"]
    start_date: str
    end_date: str
    data: list[AggregatedMetricData]


class ErrorListEntry(pydantic.BaseModel):
    log_id: int
    project_id: int
    level: str
    log_type: str
    message: str
    error_type: str | None
    timestamp: datetime.datetime
    error_fingerprint: str | None
    attributes: dict | None
    sdk_version: str | None
    platform: str | None

    model_config = pydantic.ConfigDict(from_attributes=True)

    @pydantic.field_validator("error_fingerprint", mode="before")
    @classmethod
    def strip_error_fingerprint(cls, v: str | None) -> str | None:
        if v is not None and isinstance(v, str):
            return v.strip()
        return v


class ErrorListResponse(pydantic.BaseModel):
    project_id: int
    errors: list[ErrorListEntry]
    total: int
    has_more: bool
