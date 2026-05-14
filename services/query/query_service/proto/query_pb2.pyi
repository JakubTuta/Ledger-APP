from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class QueryLogsRequest(_message.Message):
    __slots__ = ("project_id", "start_time", "end_time", "level", "log_type", "environment", "error_fingerprint", "limit", "offset", "status_class", "search")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    END_TIME_FIELD_NUMBER: _ClassVar[int]
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    LOG_TYPE_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_FIELD_NUMBER: _ClassVar[int]
    ERROR_FINGERPRINT_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    STATUS_CLASS_FIELD_NUMBER: _ClassVar[int]
    SEARCH_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    start_time: str
    end_time: str
    level: str
    log_type: str
    environment: str
    error_fingerprint: str
    limit: int
    offset: int
    status_class: _containers.RepeatedScalarFieldContainer[str]
    search: str
    def __init__(self, project_id: _Optional[int] = ..., start_time: _Optional[str] = ..., end_time: _Optional[str] = ..., level: _Optional[str] = ..., log_type: _Optional[str] = ..., environment: _Optional[str] = ..., error_fingerprint: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., status_class: _Optional[_Iterable[str]] = ..., search: _Optional[str] = ...) -> None: ...

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
    __slots__ = ("id", "project_id", "timestamp", "ingested_at", "level", "log_type", "importance", "environment", "release", "message", "error_type", "error_message", "stack_trace", "attributes", "sdk_version", "platform", "platform_version", "processing_time_ms", "error_fingerprint", "method", "path", "status_code", "duration_ms")
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
    METHOD_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    STATUS_CODE_FIELD_NUMBER: _ClassVar[int]
    DURATION_MS_FIELD_NUMBER: _ClassVar[int]
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
    method: str
    path: str
    status_code: int
    duration_ms: int
    def __init__(self, id: _Optional[int] = ..., project_id: _Optional[int] = ..., timestamp: _Optional[str] = ..., ingested_at: _Optional[str] = ..., level: _Optional[str] = ..., log_type: _Optional[str] = ..., importance: _Optional[str] = ..., environment: _Optional[str] = ..., release: _Optional[str] = ..., message: _Optional[str] = ..., error_type: _Optional[str] = ..., error_message: _Optional[str] = ..., stack_trace: _Optional[str] = ..., attributes: _Optional[str] = ..., sdk_version: _Optional[str] = ..., platform: _Optional[str] = ..., platform_version: _Optional[str] = ..., processing_time_ms: _Optional[int] = ..., error_fingerprint: _Optional[str] = ..., method: _Optional[str] = ..., path: _Optional[str] = ..., status_code: _Optional[int] = ..., duration_ms: _Optional[int] = ...) -> None: ...

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
    __slots__ = ("project_id", "metric_type", "period", "period_from", "period_to", "endpoint_path", "granularity")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    METRIC_TYPE_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FROM_FIELD_NUMBER: _ClassVar[int]
    PERIOD_TO_FIELD_NUMBER: _ClassVar[int]
    ENDPOINT_PATH_FIELD_NUMBER: _ClassVar[int]
    GRANULARITY_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    metric_type: str
    period: str
    period_from: str
    period_to: str
    endpoint_path: str
    granularity: str
    def __init__(self, project_id: _Optional[int] = ..., metric_type: _Optional[str] = ..., period: _Optional[str] = ..., period_from: _Optional[str] = ..., period_to: _Optional[str] = ..., endpoint_path: _Optional[str] = ..., granularity: _Optional[str] = ...) -> None: ...

class AggregatedMetricData(_message.Message):
    __slots__ = ("date", "hour", "endpoint_method", "endpoint_path", "log_count", "error_count", "avg_duration_ms", "min_duration_ms", "max_duration_ms", "p95_duration_ms", "p99_duration_ms", "log_level", "log_type")
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
    LOG_LEVEL_FIELD_NUMBER: _ClassVar[int]
    LOG_TYPE_FIELD_NUMBER: _ClassVar[int]
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
    log_level: str
    log_type: str
    def __init__(self, date: _Optional[str] = ..., hour: _Optional[int] = ..., endpoint_method: _Optional[str] = ..., endpoint_path: _Optional[str] = ..., log_count: _Optional[int] = ..., error_count: _Optional[int] = ..., avg_duration_ms: _Optional[float] = ..., min_duration_ms: _Optional[int] = ..., max_duration_ms: _Optional[int] = ..., p95_duration_ms: _Optional[int] = ..., p99_duration_ms: _Optional[int] = ..., log_level: _Optional[str] = ..., log_type: _Optional[str] = ...) -> None: ...

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

class GetErrorListRequest(_message.Message):
    __slots__ = ("project_id", "period", "period_from", "period_to", "limit", "offset")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FROM_FIELD_NUMBER: _ClassVar[int]
    PERIOD_TO_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    period: str
    period_from: str
    period_to: str
    limit: int
    offset: int
    def __init__(self, project_id: _Optional[int] = ..., period: _Optional[str] = ..., period_from: _Optional[str] = ..., period_to: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ErrorListEntry(_message.Message):
    __slots__ = ("log_id", "project_id", "level", "log_type", "message", "error_type", "timestamp", "error_fingerprint", "attributes", "sdk_version", "platform")
    LOG_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    LOG_TYPE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    ERROR_TYPE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    ERROR_FINGERPRINT_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTES_FIELD_NUMBER: _ClassVar[int]
    SDK_VERSION_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    log_id: int
    project_id: int
    level: str
    log_type: str
    message: str
    error_type: str
    timestamp: str
    error_fingerprint: str
    attributes: str
    sdk_version: str
    platform: str
    def __init__(self, log_id: _Optional[int] = ..., project_id: _Optional[int] = ..., level: _Optional[str] = ..., log_type: _Optional[str] = ..., message: _Optional[str] = ..., error_type: _Optional[str] = ..., timestamp: _Optional[str] = ..., error_fingerprint: _Optional[str] = ..., attributes: _Optional[str] = ..., sdk_version: _Optional[str] = ..., platform: _Optional[str] = ...) -> None: ...

class GetErrorListResponse(_message.Message):
    __slots__ = ("project_id", "errors", "total", "has_more")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    HAS_MORE_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    errors: _containers.RepeatedCompositeFieldContainer[ErrorListEntry]
    total: int
    has_more: bool
    def __init__(self, project_id: _Optional[int] = ..., errors: _Optional[_Iterable[_Union[ErrorListEntry, _Mapping]]] = ..., total: _Optional[int] = ..., has_more: bool = ...) -> None: ...

class GetBottleneckMetricsRequest(_message.Message):
    __slots__ = ("project_id", "routes", "statistic", "period", "period_from", "period_to", "granularity")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    ROUTES_FIELD_NUMBER: _ClassVar[int]
    STATISTIC_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FROM_FIELD_NUMBER: _ClassVar[int]
    PERIOD_TO_FIELD_NUMBER: _ClassVar[int]
    GRANULARITY_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    routes: _containers.RepeatedScalarFieldContainer[str]
    statistic: str
    period: str
    period_from: str
    period_to: str
    granularity: str
    def __init__(self, project_id: _Optional[int] = ..., routes: _Optional[_Iterable[str]] = ..., statistic: _Optional[str] = ..., period: _Optional[str] = ..., period_from: _Optional[str] = ..., period_to: _Optional[str] = ..., granularity: _Optional[str] = ...) -> None: ...

class BottleneckMetricDataPoint(_message.Message):
    __slots__ = ("date", "hour", "route", "value")
    DATE_FIELD_NUMBER: _ClassVar[int]
    HOUR_FIELD_NUMBER: _ClassVar[int]
    ROUTE_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    date: str
    hour: int
    route: str
    value: float
    def __init__(self, date: _Optional[str] = ..., hour: _Optional[int] = ..., route: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...

class GetBottleneckMetricsResponse(_message.Message):
    __slots__ = ("project_id", "statistic", "granularity", "start_date", "end_date", "data")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    STATISTIC_FIELD_NUMBER: _ClassVar[int]
    GRANULARITY_FIELD_NUMBER: _ClassVar[int]
    START_DATE_FIELD_NUMBER: _ClassVar[int]
    END_DATE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    statistic: str
    granularity: str
    start_date: str
    end_date: str
    data: _containers.RepeatedCompositeFieldContainer[BottleneckMetricDataPoint]
    def __init__(self, project_id: _Optional[int] = ..., statistic: _Optional[str] = ..., granularity: _Optional[str] = ..., start_date: _Optional[str] = ..., end_date: _Optional[str] = ..., data: _Optional[_Iterable[_Union[BottleneckMetricDataPoint, _Mapping]]] = ...) -> None: ...

class GetHealthSummaryRequest(_message.Message):
    __slots__ = ("project_ids", "period")
    PROJECT_IDS_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    project_ids: _containers.RepeatedScalarFieldContainer[str]
    period: str
    def __init__(self, project_ids: _Optional[_Iterable[str]] = ..., period: _Optional[str] = ...) -> None: ...

class HealthThresholds(_message.Message):
    __slots__ = ("error_rate_warn", "error_rate_crit", "p95_warn_ms", "p95_crit_ms")
    ERROR_RATE_WARN_FIELD_NUMBER: _ClassVar[int]
    ERROR_RATE_CRIT_FIELD_NUMBER: _ClassVar[int]
    P95_WARN_MS_FIELD_NUMBER: _ClassVar[int]
    P95_CRIT_MS_FIELD_NUMBER: _ClassVar[int]
    error_rate_warn: float
    error_rate_crit: float
    p95_warn_ms: int
    p95_crit_ms: int
    def __init__(self, error_rate_warn: _Optional[float] = ..., error_rate_crit: _Optional[float] = ..., p95_warn_ms: _Optional[int] = ..., p95_crit_ms: _Optional[int] = ...) -> None: ...

class HealthSummary(_message.Message):
    __slots__ = ("project_id", "error_rate", "p95_ms", "rps", "status", "sparkline", "thresholds", "generated_at")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_RATE_FIELD_NUMBER: _ClassVar[int]
    P95_MS_FIELD_NUMBER: _ClassVar[int]
    RPS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    SPARKLINE_FIELD_NUMBER: _ClassVar[int]
    THRESHOLDS_FIELD_NUMBER: _ClassVar[int]
    GENERATED_AT_FIELD_NUMBER: _ClassVar[int]
    project_id: str
    error_rate: float
    p95_ms: float
    rps: float
    status: str
    sparkline: _containers.RepeatedScalarFieldContainer[int]
    thresholds: HealthThresholds
    generated_at: str
    def __init__(self, project_id: _Optional[str] = ..., error_rate: _Optional[float] = ..., p95_ms: _Optional[float] = ..., rps: _Optional[float] = ..., status: _Optional[str] = ..., sparkline: _Optional[_Iterable[int]] = ..., thresholds: _Optional[_Union[HealthThresholds, _Mapping]] = ..., generated_at: _Optional[str] = ...) -> None: ...

class GetHealthSummaryResponse(_message.Message):
    __slots__ = ("summaries",)
    SUMMARIES_FIELD_NUMBER: _ClassVar[int]
    summaries: _containers.RepeatedCompositeFieldContainer[HealthSummary]
    def __init__(self, summaries: _Optional[_Iterable[_Union[HealthSummary, _Mapping]]] = ...) -> None: ...

class SpanData(_message.Message):
    __slots__ = ("span_id", "trace_id", "parent_span_id", "project_id", "service_name", "name", "kind", "start_time", "duration_ns", "status_code", "status_message", "attributes", "events", "error_fingerprint")
    SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    PARENT_SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    SERVICE_NAME_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    DURATION_NS_FIELD_NUMBER: _ClassVar[int]
    STATUS_CODE_FIELD_NUMBER: _ClassVar[int]
    STATUS_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTES_FIELD_NUMBER: _ClassVar[int]
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FINGERPRINT_FIELD_NUMBER: _ClassVar[int]
    span_id: str
    trace_id: str
    parent_span_id: str
    project_id: int
    service_name: str
    name: str
    kind: int
    start_time: str
    duration_ns: int
    status_code: int
    status_message: str
    attributes: str
    events: str
    error_fingerprint: str
    def __init__(self, span_id: _Optional[str] = ..., trace_id: _Optional[str] = ..., parent_span_id: _Optional[str] = ..., project_id: _Optional[int] = ..., service_name: _Optional[str] = ..., name: _Optional[str] = ..., kind: _Optional[int] = ..., start_time: _Optional[str] = ..., duration_ns: _Optional[int] = ..., status_code: _Optional[int] = ..., status_message: _Optional[str] = ..., attributes: _Optional[str] = ..., events: _Optional[str] = ..., error_fingerprint: _Optional[str] = ...) -> None: ...

class GetTraceRequest(_message.Message):
    __slots__ = ("trace_id", "project_id")
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    trace_id: str
    project_id: int
    def __init__(self, trace_id: _Optional[str] = ..., project_id: _Optional[int] = ...) -> None: ...

class GetTraceResponse(_message.Message):
    __slots__ = ("trace_id", "spans", "duration_ms", "services", "root_span_id", "found")
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SPANS_FIELD_NUMBER: _ClassVar[int]
    DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    SERVICES_FIELD_NUMBER: _ClassVar[int]
    ROOT_SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    FOUND_FIELD_NUMBER: _ClassVar[int]
    trace_id: str
    spans: _containers.RepeatedCompositeFieldContainer[SpanData]
    duration_ms: int
    services: _containers.RepeatedScalarFieldContainer[str]
    root_span_id: str
    found: bool
    def __init__(self, trace_id: _Optional[str] = ..., spans: _Optional[_Iterable[_Union[SpanData, _Mapping]]] = ..., duration_ms: _Optional[int] = ..., services: _Optional[_Iterable[str]] = ..., root_span_id: _Optional[str] = ..., found: bool = ...) -> None: ...

class ListTracesRequest(_message.Message):
    __slots__ = ("project_id", "service", "name", "min_duration_ms", "has_error", "from_time", "to_time", "limit", "offset")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    MIN_DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    HAS_ERROR_FIELD_NUMBER: _ClassVar[int]
    FROM_TIME_FIELD_NUMBER: _ClassVar[int]
    TO_TIME_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    service: str
    name: str
    min_duration_ms: int
    has_error: bool
    from_time: str
    to_time: str
    limit: int
    offset: int
    def __init__(self, project_id: _Optional[int] = ..., service: _Optional[str] = ..., name: _Optional[str] = ..., min_duration_ms: _Optional[int] = ..., has_error: bool = ..., from_time: _Optional[str] = ..., to_time: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class TraceSummary(_message.Message):
    __slots__ = ("trace_id", "root_span_id", "root_name", "service_name", "start_time", "duration_ms", "span_count", "has_error")
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    ROOT_SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    ROOT_NAME_FIELD_NUMBER: _ClassVar[int]
    SERVICE_NAME_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    SPAN_COUNT_FIELD_NUMBER: _ClassVar[int]
    HAS_ERROR_FIELD_NUMBER: _ClassVar[int]
    trace_id: str
    root_span_id: str
    root_name: str
    service_name: str
    start_time: str
    duration_ms: int
    span_count: int
    has_error: bool
    def __init__(self, trace_id: _Optional[str] = ..., root_span_id: _Optional[str] = ..., root_name: _Optional[str] = ..., service_name: _Optional[str] = ..., start_time: _Optional[str] = ..., duration_ms: _Optional[int] = ..., span_count: _Optional[int] = ..., has_error: bool = ...) -> None: ...

class ListTracesResponse(_message.Message):
    __slots__ = ("traces", "total", "has_more")
    TRACES_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    HAS_MORE_FIELD_NUMBER: _ClassVar[int]
    traces: _containers.RepeatedCompositeFieldContainer[TraceSummary]
    total: int
    has_more: bool
    def __init__(self, traces: _Optional[_Iterable[_Union[TraceSummary, _Mapping]]] = ..., total: _Optional[int] = ..., has_more: bool = ...) -> None: ...

class GetSpanLatencyRequest(_message.Message):
    __slots__ = ("project_id", "service", "name", "from_time", "to_time")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    FROM_TIME_FIELD_NUMBER: _ClassVar[int]
    TO_TIME_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    service: str
    name: str
    from_time: str
    to_time: str
    def __init__(self, project_id: _Optional[int] = ..., service: _Optional[str] = ..., name: _Optional[str] = ..., from_time: _Optional[str] = ..., to_time: _Optional[str] = ...) -> None: ...

class SpanLatencyBucket(_message.Message):
    __slots__ = ("service_name", "name", "bucket", "calls", "p50_ns", "p95_ns", "p99_ns", "errors")
    SERVICE_NAME_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    BUCKET_FIELD_NUMBER: _ClassVar[int]
    CALLS_FIELD_NUMBER: _ClassVar[int]
    P50_NS_FIELD_NUMBER: _ClassVar[int]
    P95_NS_FIELD_NUMBER: _ClassVar[int]
    P99_NS_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    service_name: str
    name: str
    bucket: str
    calls: int
    p50_ns: int
    p95_ns: int
    p99_ns: int
    errors: int
    def __init__(self, service_name: _Optional[str] = ..., name: _Optional[str] = ..., bucket: _Optional[str] = ..., calls: _Optional[int] = ..., p50_ns: _Optional[int] = ..., p95_ns: _Optional[int] = ..., p99_ns: _Optional[int] = ..., errors: _Optional[int] = ...) -> None: ...

class GetSpanLatencyResponse(_message.Message):
    __slots__ = ("project_id", "data")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    data: _containers.RepeatedCompositeFieldContainer[SpanLatencyBucket]
    def __init__(self, project_id: _Optional[int] = ..., data: _Optional[_Iterable[_Union[SpanLatencyBucket, _Mapping]]] = ...) -> None: ...

class QueryCustomMetricsRequest(_message.Message):
    __slots__ = ("project_id", "name", "tags", "from_time", "to_time", "agg", "step_seconds")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    FROM_TIME_FIELD_NUMBER: _ClassVar[int]
    TO_TIME_FIELD_NUMBER: _ClassVar[int]
    AGG_FIELD_NUMBER: _ClassVar[int]
    STEP_SECONDS_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    name: str
    tags: str
    from_time: str
    to_time: str
    agg: str
    step_seconds: int
    def __init__(self, project_id: _Optional[int] = ..., name: _Optional[str] = ..., tags: _Optional[str] = ..., from_time: _Optional[str] = ..., to_time: _Optional[str] = ..., agg: _Optional[str] = ..., step_seconds: _Optional[int] = ...) -> None: ...

class CustomMetricDataPoint(_message.Message):
    __slots__ = ("bucket", "value")
    BUCKET_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    bucket: str
    value: float
    def __init__(self, bucket: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...

class QueryCustomMetricsResponse(_message.Message):
    __slots__ = ("project_id", "name", "agg", "data")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    AGG_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    name: str
    agg: str
    data: _containers.RepeatedCompositeFieldContainer[CustomMetricDataPoint]
    def __init__(self, project_id: _Optional[int] = ..., name: _Optional[str] = ..., agg: _Optional[str] = ..., data: _Optional[_Iterable[_Union[CustomMetricDataPoint, _Mapping]]] = ...) -> None: ...

class ListCustomMetricNamesRequest(_message.Message):
    __slots__ = ("project_id", "prefix")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    PREFIX_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    prefix: str
    def __init__(self, project_id: _Optional[int] = ..., prefix: _Optional[str] = ...) -> None: ...

class ListCustomMetricNamesResponse(_message.Message):
    __slots__ = ("names",)
    NAMES_FIELD_NUMBER: _ClassVar[int]
    names: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, names: _Optional[_Iterable[str]] = ...) -> None: ...

class ListCustomMetricTagsRequest(_message.Message):
    __slots__ = ("project_id", "name")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    name: str
    def __init__(self, project_id: _Optional[int] = ..., name: _Optional[str] = ...) -> None: ...

class CustomMetricTagEntry(_message.Message):
    __slots__ = ("key", "values")
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    key: str
    values: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, key: _Optional[str] = ..., values: _Optional[_Iterable[str]] = ...) -> None: ...

class ListCustomMetricTagsResponse(_message.Message):
    __slots__ = ("tags",)
    TAGS_FIELD_NUMBER: _ClassVar[int]
    tags: _containers.RepeatedCompositeFieldContainer[CustomMetricTagEntry]
    def __init__(self, tags: _Optional[_Iterable[_Union[CustomMetricTagEntry, _Mapping]]] = ...) -> None: ...
