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
SERVER: SpanKind
CLIENT: SpanKind
INTERNAL: SpanKind
PRODUCER: SpanKind
CONSUMER: SpanKind
UNSET: SpanStatus
OK: SpanStatus
ERROR: SpanStatus

class LogEntry(_message.Message):
    __slots__ = ("timestamp", "level", "log_type", "importance", "message", "error_type", "error_message", "stack_trace", "environment", "release", "sdk_version", "platform", "platform_version", "attributes")
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
    def __init__(self, timestamp: _Optional[str] = ..., level: _Optional[str] = ..., log_type: _Optional[str] = ..., importance: _Optional[str] = ..., message: _Optional[str] = ..., error_type: _Optional[str] = ..., error_message: _Optional[str] = ..., stack_trace: _Optional[str] = ..., environment: _Optional[str] = ..., release: _Optional[str] = ..., sdk_version: _Optional[str] = ..., platform: _Optional[str] = ..., platform_version: _Optional[str] = ..., attributes: _Optional[str] = ...) -> None: ...

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
    __slots__ = ("project_id", "logs")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    LOGS_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    logs: _containers.RepeatedCompositeFieldContainer[LogEntry]
    def __init__(self, project_id: _Optional[int] = ..., logs: _Optional[_Iterable[_Union[LogEntry, _Mapping]]] = ...) -> None: ...

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

class QueueDepthRequest(_message.Message):
    __slots__ = ("project_id",)
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    def __init__(self, project_id: _Optional[int] = ...) -> None: ...

class QueueDepthResponse(_message.Message):
    __slots__ = ("depth",)
    DEPTH_FIELD_NUMBER: _ClassVar[int]
    depth: int
    def __init__(self, depth: _Optional[int] = ...) -> None: ...

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
    __slots__ = ("trace_id", "span_id", "parent_span_id", "name", "kind", "start_unix_nano", "end_unix_nano", "status", "status_message", "attributes", "events", "service_name")
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
    def __init__(self, trace_id: _Optional[str] = ..., span_id: _Optional[str] = ..., parent_span_id: _Optional[str] = ..., name: _Optional[str] = ..., kind: _Optional[_Union[SpanKind, str]] = ..., start_unix_nano: _Optional[int] = ..., end_unix_nano: _Optional[int] = ..., status: _Optional[_Union[SpanStatus, str]] = ..., status_message: _Optional[str] = ..., attributes: _Optional[_Mapping[str, str]] = ..., events: _Optional[_Iterable[_Union[SpanEvent, _Mapping]]] = ..., service_name: _Optional[str] = ...) -> None: ...

class IngestSpansBatchRequest(_message.Message):
    __slots__ = ("project_id", "spans")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    SPANS_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    spans: _containers.RepeatedCompositeFieldContainer[Span]
    def __init__(self, project_id: _Optional[int] = ..., spans: _Optional[_Iterable[_Union[Span, _Mapping]]] = ...) -> None: ...

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

class MetricDataPoint(_message.Message):
    __slots__ = ("name", "tags", "ts_unix_nano", "type", "count", "sum", "min_v", "max_v", "buckets")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    TS_UNIX_NANO_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    SUM_FIELD_NUMBER: _ClassVar[int]
    MIN_V_FIELD_NUMBER: _ClassVar[int]
    MAX_V_FIELD_NUMBER: _ClassVar[int]
    BUCKETS_FIELD_NUMBER: _ClassVar[int]
    name: str
    tags: str
    ts_unix_nano: int
    type: int
    count: int
    sum: float
    min_v: float
    max_v: float
    buckets: str
    def __init__(self, name: _Optional[str] = ..., tags: _Optional[str] = ..., ts_unix_nano: _Optional[int] = ..., type: _Optional[int] = ..., count: _Optional[int] = ..., sum: _Optional[float] = ..., min_v: _Optional[float] = ..., max_v: _Optional[float] = ..., buckets: _Optional[str] = ...) -> None: ...

class IngestMetricsBatchRequest(_message.Message):
    __slots__ = ("project_id", "metrics")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    METRICS_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    metrics: _containers.RepeatedCompositeFieldContainer[MetricDataPoint]
    def __init__(self, project_id: _Optional[int] = ..., metrics: _Optional[_Iterable[_Union[MetricDataPoint, _Mapping]]] = ...) -> None: ...

class IngestMetricsBatchResponse(_message.Message):
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
