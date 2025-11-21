from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class QueryLogsRequest(_message.Message):
    __slots__ = ("project_id", "start_time", "end_time", "level", "log_type", "environment", "error_fingerprint", "limit", "offset")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    END_TIME_FIELD_NUMBER: _ClassVar[int]
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    LOG_TYPE_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_FIELD_NUMBER: _ClassVar[int]
    ERROR_FINGERPRINT_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    start_time: str
    end_time: str
    level: str
    log_type: str
    environment: str
    error_fingerprint: str
    limit: int
    offset: int
    def __init__(self, project_id: _Optional[int] = ..., start_time: _Optional[str] = ..., end_time: _Optional[str] = ..., level: _Optional[str] = ..., log_type: _Optional[str] = ..., environment: _Optional[str] = ..., error_fingerprint: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class SearchLogsRequest(_message.Message):
    __slots__ = ("project_id", "query", "start_time", "end_time", "limit", "offset")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    END_TIME_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    query: str
    start_time: str
    end_time: str
    limit: int
    offset: int
    def __init__(self, project_id: _Optional[int] = ..., query: _Optional[str] = ..., start_time: _Optional[str] = ..., end_time: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class GetLogRequest(_message.Message):
    __slots__ = ("log_id", "project_id")
    LOG_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    log_id: int
    project_id: int
    def __init__(self, log_id: _Optional[int] = ..., project_id: _Optional[int] = ...) -> None: ...

class LogEntry(_message.Message):
    __slots__ = ("id", "project_id", "timestamp", "ingested_at", "level", "log_type", "importance", "environment", "release", "message", "error_type", "error_message", "stack_trace", "attributes", "sdk_version", "platform", "platform_version", "processing_time_ms", "error_fingerprint")
    ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    INGESTED_AT_FIELD_NUMBER: _ClassVar[int]
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    LOG_TYPE_FIELD_NUMBER: _ClassVar[int]
    IMPORTANCE_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_FIELD_NUMBER: _ClassVar[int]
    RELEASE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    ERROR_TYPE_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    STACK_TRACE_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTES_FIELD_NUMBER: _ClassVar[int]
    SDK_VERSION_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_VERSION_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FINGERPRINT_FIELD_NUMBER: _ClassVar[int]
    id: int
    project_id: int
    timestamp: str
    ingested_at: str
    level: str
    log_type: str
    importance: str
    environment: str
    release: str
    message: str
    error_type: str
    error_message: str
    stack_trace: str
    attributes: str
    sdk_version: str
    platform: str
    platform_version: str
    processing_time_ms: int
    error_fingerprint: str
    def __init__(self, id: _Optional[int] = ..., project_id: _Optional[int] = ..., timestamp: _Optional[str] = ..., ingested_at: _Optional[str] = ..., level: _Optional[str] = ..., log_type: _Optional[str] = ..., importance: _Optional[str] = ..., environment: _Optional[str] = ..., release: _Optional[str] = ..., message: _Optional[str] = ..., error_type: _Optional[str] = ..., error_message: _Optional[str] = ..., stack_trace: _Optional[str] = ..., attributes: _Optional[str] = ..., sdk_version: _Optional[str] = ..., platform: _Optional[str] = ..., platform_version: _Optional[str] = ..., processing_time_ms: _Optional[int] = ..., error_fingerprint: _Optional[str] = ...) -> None: ...

class QueryLogsResponse(_message.Message):
    __slots__ = ("logs", "total", "has_more")
    LOGS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    HAS_MORE_FIELD_NUMBER: _ClassVar[int]
    logs: _containers.RepeatedCompositeFieldContainer[LogEntry]
    total: int
    has_more: bool
    def __init__(self, logs: _Optional[_Iterable[_Union[LogEntry, _Mapping]]] = ..., total: _Optional[int] = ..., has_more: bool = ...) -> None: ...

class SearchLogsResponse(_message.Message):
    __slots__ = ("logs", "total", "has_more")
    LOGS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    HAS_MORE_FIELD_NUMBER: _ClassVar[int]
    logs: _containers.RepeatedCompositeFieldContainer[LogEntry]
    total: int
    has_more: bool
    def __init__(self, logs: _Optional[_Iterable[_Union[LogEntry, _Mapping]]] = ..., total: _Optional[int] = ..., has_more: bool = ...) -> None: ...

class GetLogResponse(_message.Message):
    __slots__ = ("log", "found")
    LOG_FIELD_NUMBER: _ClassVar[int]
    FOUND_FIELD_NUMBER: _ClassVar[int]
    log: LogEntry
    found: bool
    def __init__(self, log: _Optional[_Union[LogEntry, _Mapping]] = ..., found: bool = ...) -> None: ...

class GetErrorRateRequest(_message.Message):
    __slots__ = ("project_id", "interval", "start_time", "end_time")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    END_TIME_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    interval: str
    start_time: str
    end_time: str
    def __init__(self, project_id: _Optional[int] = ..., interval: _Optional[str] = ..., start_time: _Optional[str] = ..., end_time: _Optional[str] = ...) -> None: ...

class ErrorRateData(_message.Message):
    __slots__ = ("timestamp", "error_count", "critical_count")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    ERROR_COUNT_FIELD_NUMBER: _ClassVar[int]
    CRITICAL_COUNT_FIELD_NUMBER: _ClassVar[int]
    timestamp: str
    error_count: int
    critical_count: int
    def __init__(self, timestamp: _Optional[str] = ..., error_count: _Optional[int] = ..., critical_count: _Optional[int] = ...) -> None: ...

class GetErrorRateResponse(_message.Message):
    __slots__ = ("project_id", "interval", "data")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    interval: str
    data: _containers.RepeatedCompositeFieldContainer[ErrorRateData]
    def __init__(self, project_id: _Optional[int] = ..., interval: _Optional[str] = ..., data: _Optional[_Iterable[_Union[ErrorRateData, _Mapping]]] = ...) -> None: ...

class GetLogVolumeRequest(_message.Message):
    __slots__ = ("project_id", "interval", "start_time", "end_time")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    END_TIME_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    interval: str
    start_time: str
    end_time: str
    def __init__(self, project_id: _Optional[int] = ..., interval: _Optional[str] = ..., start_time: _Optional[str] = ..., end_time: _Optional[str] = ...) -> None: ...

class LogVolumeData(_message.Message):
    __slots__ = ("timestamp", "debug", "info", "warning", "error", "critical")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    DEBUG_FIELD_NUMBER: _ClassVar[int]
    INFO_FIELD_NUMBER: _ClassVar[int]
    WARNING_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    CRITICAL_FIELD_NUMBER: _ClassVar[int]
    timestamp: str
    debug: int
    info: int
    warning: int
    error: int
    critical: int
    def __init__(self, timestamp: _Optional[str] = ..., debug: _Optional[int] = ..., info: _Optional[int] = ..., warning: _Optional[int] = ..., error: _Optional[int] = ..., critical: _Optional[int] = ...) -> None: ...

class GetLogVolumeResponse(_message.Message):
    __slots__ = ("project_id", "interval", "data")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    interval: str
    data: _containers.RepeatedCompositeFieldContainer[LogVolumeData]
    def __init__(self, project_id: _Optional[int] = ..., interval: _Optional[str] = ..., data: _Optional[_Iterable[_Union[LogVolumeData, _Mapping]]] = ...) -> None: ...

class GetTopErrorsRequest(_message.Message):
    __slots__ = ("project_id", "limit", "start_time", "end_time", "status")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    END_TIME_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    limit: int
    start_time: str
    end_time: str
    status: str
    def __init__(self, project_id: _Optional[int] = ..., limit: _Optional[int] = ..., start_time: _Optional[str] = ..., end_time: _Optional[str] = ..., status: _Optional[str] = ...) -> None: ...

class TopErrorData(_message.Message):
    __slots__ = ("fingerprint", "error_type", "error_message", "occurrence_count", "first_seen", "last_seen", "status", "sample_log_id")
    FINGERPRINT_FIELD_NUMBER: _ClassVar[int]
    ERROR_TYPE_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    OCCURRENCE_COUNT_FIELD_NUMBER: _ClassVar[int]
    FIRST_SEEN_FIELD_NUMBER: _ClassVar[int]
    LAST_SEEN_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_LOG_ID_FIELD_NUMBER: _ClassVar[int]
    fingerprint: str
    error_type: str
    error_message: str
    occurrence_count: int
    first_seen: str
    last_seen: str
    status: str
    sample_log_id: int
    def __init__(self, fingerprint: _Optional[str] = ..., error_type: _Optional[str] = ..., error_message: _Optional[str] = ..., occurrence_count: _Optional[int] = ..., first_seen: _Optional[str] = ..., last_seen: _Optional[str] = ..., status: _Optional[str] = ..., sample_log_id: _Optional[int] = ...) -> None: ...

class GetTopErrorsResponse(_message.Message):
    __slots__ = ("project_id", "errors")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    errors: _containers.RepeatedCompositeFieldContainer[TopErrorData]
    def __init__(self, project_id: _Optional[int] = ..., errors: _Optional[_Iterable[_Union[TopErrorData, _Mapping]]] = ...) -> None: ...

class GetUsageStatsRequest(_message.Message):
    __slots__ = ("project_id", "start_date", "end_date")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    START_DATE_FIELD_NUMBER: _ClassVar[int]
    END_DATE_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    start_date: str
    end_date: str
    def __init__(self, project_id: _Optional[int] = ..., start_date: _Optional[str] = ..., end_date: _Optional[str] = ...) -> None: ...

class UsageStatsData(_message.Message):
    __slots__ = ("date", "log_count", "daily_quota", "quota_used_percent")
    DATE_FIELD_NUMBER: _ClassVar[int]
    LOG_COUNT_FIELD_NUMBER: _ClassVar[int]
    DAILY_QUOTA_FIELD_NUMBER: _ClassVar[int]
    QUOTA_USED_PERCENT_FIELD_NUMBER: _ClassVar[int]
    date: str
    log_count: int
    daily_quota: int
    quota_used_percent: float
    def __init__(self, date: _Optional[str] = ..., log_count: _Optional[int] = ..., daily_quota: _Optional[int] = ..., quota_used_percent: _Optional[float] = ...) -> None: ...

class GetUsageStatsResponse(_message.Message):
    __slots__ = ("project_id", "usage")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    USAGE_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    usage: _containers.RepeatedCompositeFieldContainer[UsageStatsData]
    def __init__(self, project_id: _Optional[int] = ..., usage: _Optional[_Iterable[_Union[UsageStatsData, _Mapping]]] = ...) -> None: ...

class GetAggregatedMetricsRequest(_message.Message):
    __slots__ = ("project_id", "metric_type", "period", "period_from", "period_to")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    METRIC_TYPE_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FROM_FIELD_NUMBER: _ClassVar[int]
    PERIOD_TO_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    metric_type: str
    period: str
    period_from: str
    period_to: str
    def __init__(self, project_id: _Optional[int] = ..., metric_type: _Optional[str] = ..., period: _Optional[str] = ..., period_from: _Optional[str] = ..., period_to: _Optional[str] = ...) -> None: ...

class AggregatedMetricData(_message.Message):
    __slots__ = ("date", "hour", "endpoint_method", "endpoint_path", "log_count", "error_count", "avg_duration_ms", "min_duration_ms", "max_duration_ms", "p95_duration_ms", "p99_duration_ms")
    DATE_FIELD_NUMBER: _ClassVar[int]
    HOUR_FIELD_NUMBER: _ClassVar[int]
    ENDPOINT_METHOD_FIELD_NUMBER: _ClassVar[int]
    ENDPOINT_PATH_FIELD_NUMBER: _ClassVar[int]
    LOG_COUNT_FIELD_NUMBER: _ClassVar[int]
    ERROR_COUNT_FIELD_NUMBER: _ClassVar[int]
    AVG_DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    MIN_DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    MAX_DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    P95_DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    P99_DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    date: str
    hour: int
    endpoint_method: str
    endpoint_path: str
    log_count: int
    error_count: int
    avg_duration_ms: float
    min_duration_ms: int
    max_duration_ms: int
    p95_duration_ms: int
    p99_duration_ms: int
    def __init__(self, date: _Optional[str] = ..., hour: _Optional[int] = ..., endpoint_method: _Optional[str] = ..., endpoint_path: _Optional[str] = ..., log_count: _Optional[int] = ..., error_count: _Optional[int] = ..., avg_duration_ms: _Optional[float] = ..., min_duration_ms: _Optional[int] = ..., max_duration_ms: _Optional[int] = ..., p95_duration_ms: _Optional[int] = ..., p99_duration_ms: _Optional[int] = ...) -> None: ...

class GetAggregatedMetricsResponse(_message.Message):
    __slots__ = ("project_id", "metric_type", "granularity", "start_date", "end_date", "data")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    METRIC_TYPE_FIELD_NUMBER: _ClassVar[int]
    GRANULARITY_FIELD_NUMBER: _ClassVar[int]
    START_DATE_FIELD_NUMBER: _ClassVar[int]
    END_DATE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    metric_type: str
    granularity: str
    start_date: str
    end_date: str
    data: _containers.RepeatedCompositeFieldContainer[AggregatedMetricData]
    def __init__(self, project_id: _Optional[int] = ..., metric_type: _Optional[str] = ..., granularity: _Optional[str] = ..., start_date: _Optional[str] = ..., end_date: _Optional[str] = ..., data: _Optional[_Iterable[_Union[AggregatedMetricData, _Mapping]]] = ...) -> None: ...
