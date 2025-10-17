from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

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
