from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SpanKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SERVER: _ClassVar[SpanKind]
    CLIENT: _ClassVar[SpanKind]
    INTERNAL: _ClassVar[SpanKind]
    PRODUCER: _ClassVar[SpanKind]
    CONSUMER: _ClassVar[SpanKind]

class SpanStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNSET: _ClassVar[SpanStatus]
    OK: _ClassVar[SpanStatus]
    ERROR: _ClassVar[SpanStatus]

class MetricType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SUM: _ClassVar[MetricType]
    GAUGE: _ClassVar[MetricType]
    HISTOGRAM: _ClassVar[MetricType]
    EXPONENTIAL_HISTOGRAM: _ClassVar[MetricType]
    SUMMARY: _ClassVar[MetricType]

class MetricTemporality(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TEMPORALITY_UNSPECIFIED: _ClassVar[MetricTemporality]
    TEMPORALITY_DELTA: _ClassVar[MetricTemporality]
    TEMPORALITY_CUMULATIVE: _ClassVar[MetricTemporality]
SERVER: SpanKind
CLIENT: SpanKind
INTERNAL: SpanKind
PRODUCER: SpanKind
CONSUMER: SpanKind
UNSET: SpanStatus
OK: SpanStatus
ERROR: SpanStatus
SUM: MetricType
GAUGE: MetricType
HISTOGRAM: MetricType
EXPONENTIAL_HISTOGRAM: MetricType
SUMMARY: MetricType
TEMPORALITY_UNSPECIFIED: MetricTemporality
TEMPORALITY_DELTA: MetricTemporality
TEMPORALITY_CUMULATIVE: MetricTemporality

class LogEntry(_message.Message):
    __slots__ = ("timestamp", "level", "log_type", "importance", "message", "error_type", "error_message", "stack_trace", "environment", "release", "sdk_version", "platform", "platform_version", "attributes", "log_id", "client_channel", "client_country", "resource_hash", "service_name", "trace_id", "span_id")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    LOG_TYPE_FIELD_NUMBER: _ClassVar[int]
    IMPORTANCE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    ERROR_TYPE_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    STACK_TRACE_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_FIELD_NUMBER: _ClassVar[int]
    RELEASE_FIELD_NUMBER: _ClassVar[int]
    SDK_VERSION_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_VERSION_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTES_FIELD_NUMBER: _ClassVar[int]
    LOG_ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_CHANNEL_FIELD_NUMBER: _ClassVar[int]
    CLIENT_COUNTRY_FIELD_NUMBER: _ClassVar[int]
    RESOURCE_HASH_FIELD_NUMBER: _ClassVar[int]
    SERVICE_NAME_FIELD_NUMBER: _ClassVar[int]
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    timestamp: str
    level: str
    log_type: str
    importance: str
    message: str
    error_type: str
    error_message: str
    stack_trace: str
    environment: str
    release: str
    sdk_version: str
    platform: str
    platform_version: str
    attributes: str
    log_id: str
    client_channel: str
    client_country: str
    resource_hash: int
    service_name: str
    trace_id: str
    span_id: str
    def __init__(self, timestamp: _Optional[str] = ..., level: _Optional[str] = ..., log_type: _Optional[str] = ..., importance: _Optional[str] = ..., message: _Optional[str] = ..., error_type: _Optional[str] = ..., error_message: _Optional[str] = ..., stack_trace: _Optional[str] = ..., environment: _Optional[str] = ..., release: _Optional[str] = ..., sdk_version: _Optional[str] = ..., platform: _Optional[str] = ..., platform_version: _Optional[str] = ..., attributes: _Optional[str] = ..., log_id: _Optional[str] = ..., client_channel: _Optional[str] = ..., client_country: _Optional[str] = ..., resource_hash: _Optional[int] = ..., service_name: _Optional[str] = ..., trace_id: _Optional[str] = ..., span_id: _Optional[str] = ...) -> None: ...

class IngestLogRequest(_message.Message):
    __slots__ = ("project_id", "log")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    LOG_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    log: LogEntry
    def __init__(self, project_id: _Optional[int] = ..., log: _Optional[_Union[LogEntry, _Mapping]] = ...) -> None: ...

class IngestLogResponse(_message.Message):
    __slots__ = ("success", "message", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    error: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...

class IngestLogBatchRequest(_message.Message):
    __slots__ = ("project_id", "logs", "resources")
    class ResourcesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: int
        value: str
        def __init__(self, key: _Optional[int] = ..., value: _Optional[str] = ...) -> None: ...
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    LOGS_FIELD_NUMBER: _ClassVar[int]
    RESOURCES_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    logs: _containers.RepeatedCompositeFieldContainer[LogEntry]
    resources: _containers.ScalarMap[int, str]
    def __init__(self, project_id: _Optional[int] = ..., logs: _Optional[_Iterable[_Union[LogEntry, _Mapping]]] = ..., resources: _Optional[_Mapping[int, str]] = ...) -> None: ...

class IngestLogBatchResponse(_message.Message):
    __slots__ = ("success", "queued", "failed", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    QUEUED_FIELD_NUMBER: _ClassVar[int]
    FAILED_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    queued: int
    failed: int
    error: str
    def __init__(self, success: bool = ..., queued: _Optional[int] = ..., failed: _Optional[int] = ..., error: _Optional[str] = ...) -> None: ...

class SpanEvent(_message.Message):
    __slots__ = ("name", "ts_unix_nano", "attrs")
    class AttrsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    NAME_FIELD_NUMBER: _ClassVar[int]
    TS_UNIX_NANO_FIELD_NUMBER: _ClassVar[int]
    ATTRS_FIELD_NUMBER: _ClassVar[int]
    name: str
    ts_unix_nano: int
    attrs: _containers.ScalarMap[str, str]
    def __init__(self, name: _Optional[str] = ..., ts_unix_nano: _Optional[int] = ..., attrs: _Optional[_Mapping[str, str]] = ...) -> None: ...

class Span(_message.Message):
    __slots__ = ("trace_id", "span_id", "parent_span_id", "name", "kind", "start_unix_nano", "end_unix_nano", "status", "status_message", "attributes", "events", "service_name", "resource_hash")
    class AttributesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    PARENT_SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    START_UNIX_NANO_FIELD_NUMBER: _ClassVar[int]
    END_UNIX_NANO_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    STATUS_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTES_FIELD_NUMBER: _ClassVar[int]
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    SERVICE_NAME_FIELD_NUMBER: _ClassVar[int]
    RESOURCE_HASH_FIELD_NUMBER: _ClassVar[int]
    trace_id: str
    span_id: str
    parent_span_id: str
    name: str
    kind: SpanKind
    start_unix_nano: int
    end_unix_nano: int
    status: SpanStatus
    status_message: str
    attributes: _containers.ScalarMap[str, str]
    events: _containers.RepeatedCompositeFieldContainer[SpanEvent]
    service_name: str
    resource_hash: int
    def __init__(self, trace_id: _Optional[str] = ..., span_id: _Optional[str] = ..., parent_span_id: _Optional[str] = ..., name: _Optional[str] = ..., kind: _Optional[_Union[SpanKind, str]] = ..., start_unix_nano: _Optional[int] = ..., end_unix_nano: _Optional[int] = ..., status: _Optional[_Union[SpanStatus, str]] = ..., status_message: _Optional[str] = ..., attributes: _Optional[_Mapping[str, str]] = ..., events: _Optional[_Iterable[_Union[SpanEvent, _Mapping]]] = ..., service_name: _Optional[str] = ..., resource_hash: _Optional[int] = ...) -> None: ...

class IngestSpansBatchRequest(_message.Message):
    __slots__ = ("project_id", "spans", "resources")
    class ResourcesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: int
        value: str
        def __init__(self, key: _Optional[int] = ..., value: _Optional[str] = ...) -> None: ...
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    SPANS_FIELD_NUMBER: _ClassVar[int]
    RESOURCES_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    spans: _containers.RepeatedCompositeFieldContainer[Span]
    resources: _containers.ScalarMap[int, str]
    def __init__(self, project_id: _Optional[int] = ..., spans: _Optional[_Iterable[_Union[Span, _Mapping]]] = ..., resources: _Optional[_Mapping[int, str]] = ...) -> None: ...

class IngestSpansBatchResponse(_message.Message):
    __slots__ = ("success", "accepted", "rejected", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    REJECTED_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    accepted: int
    rejected: int
    error: str
    def __init__(self, success: bool = ..., accepted: _Optional[int] = ..., rejected: _Optional[int] = ..., error: _Optional[str] = ...) -> None: ...

class MetricPoint(_message.Message):
    __slots__ = ("name", "type", "timestamp", "value", "count", "sum", "bucket_counts", "explicit_bounds", "tags", "service_name", "temporality", "resource_hash", "scale", "zero_count", "positive_offset", "positive_counts", "negative_offset", "negative_counts", "quantiles", "quantile_values", "exemplars")
    class TagsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    NAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    SUM_FIELD_NUMBER: _ClassVar[int]
    BUCKET_COUNTS_FIELD_NUMBER: _ClassVar[int]
    EXPLICIT_BOUNDS_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    SERVICE_NAME_FIELD_NUMBER: _ClassVar[int]
    TEMPORALITY_FIELD_NUMBER: _ClassVar[int]
    RESOURCE_HASH_FIELD_NUMBER: _ClassVar[int]
    SCALE_FIELD_NUMBER: _ClassVar[int]
    ZERO_COUNT_FIELD_NUMBER: _ClassVar[int]
    POSITIVE_OFFSET_FIELD_NUMBER: _ClassVar[int]
    POSITIVE_COUNTS_FIELD_NUMBER: _ClassVar[int]
    NEGATIVE_OFFSET_FIELD_NUMBER: _ClassVar[int]
    NEGATIVE_COUNTS_FIELD_NUMBER: _ClassVar[int]
    QUANTILES_FIELD_NUMBER: _ClassVar[int]
    QUANTILE_VALUES_FIELD_NUMBER: _ClassVar[int]
    EXEMPLARS_FIELD_NUMBER: _ClassVar[int]
    name: str
    type: MetricType
    timestamp: str
    value: float
    count: int
    sum: float
    bucket_counts: _containers.RepeatedScalarFieldContainer[float]
    explicit_bounds: _containers.RepeatedScalarFieldContainer[float]
    tags: _containers.ScalarMap[str, str]
    service_name: str
    temporality: MetricTemporality
    resource_hash: int
    scale: int
    zero_count: int
    positive_offset: int
    positive_counts: _containers.RepeatedScalarFieldContainer[int]
    negative_offset: int
    negative_counts: _containers.RepeatedScalarFieldContainer[int]
    quantiles: _containers.RepeatedScalarFieldContainer[float]
    quantile_values: _containers.RepeatedScalarFieldContainer[float]
    exemplars: _containers.RepeatedCompositeFieldContainer[Exemplar]
    def __init__(self, name: _Optional[str] = ..., type: _Optional[_Union[MetricType, str]] = ..., timestamp: _Optional[str] = ..., value: _Optional[float] = ..., count: _Optional[int] = ..., sum: _Optional[float] = ..., bucket_counts: _Optional[_Iterable[float]] = ..., explicit_bounds: _Optional[_Iterable[float]] = ..., tags: _Optional[_Mapping[str, str]] = ..., service_name: _Optional[str] = ..., temporality: _Optional[_Union[MetricTemporality, str]] = ..., resource_hash: _Optional[int] = ..., scale: _Optional[int] = ..., zero_count: _Optional[int] = ..., positive_offset: _Optional[int] = ..., positive_counts: _Optional[_Iterable[int]] = ..., negative_offset: _Optional[int] = ..., negative_counts: _Optional[_Iterable[int]] = ..., quantiles: _Optional[_Iterable[float]] = ..., quantile_values: _Optional[_Iterable[float]] = ..., exemplars: _Optional[_Iterable[_Union[Exemplar, _Mapping]]] = ...) -> None: ...

class Exemplar(_message.Message):
    __slots__ = ("value", "timestamp", "trace_id", "span_id")
    VALUE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    value: float
    timestamp: str
    trace_id: str
    span_id: str
    def __init__(self, value: _Optional[float] = ..., timestamp: _Optional[str] = ..., trace_id: _Optional[str] = ..., span_id: _Optional[str] = ...) -> None: ...

class IngestMetricPointsBatchRequest(_message.Message):
    __slots__ = ("project_id", "points", "resources")
    class ResourcesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: int
        value: str
        def __init__(self, key: _Optional[int] = ..., value: _Optional[str] = ...) -> None: ...
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    POINTS_FIELD_NUMBER: _ClassVar[int]
    RESOURCES_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    points: _containers.RepeatedCompositeFieldContainer[MetricPoint]
    resources: _containers.ScalarMap[int, str]
    def __init__(self, project_id: _Optional[int] = ..., points: _Optional[_Iterable[_Union[MetricPoint, _Mapping]]] = ..., resources: _Optional[_Mapping[int, str]] = ...) -> None: ...

class IngestMetricPointsBatchResponse(_message.Message):
    __slots__ = ("success", "accepted", "rejected", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    REJECTED_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    accepted: int
    rejected: int
    error: str
    def __init__(self, success: bool = ..., accepted: _Optional[int] = ..., rejected: _Optional[int] = ..., error: _Optional[str] = ...) -> None: ...
