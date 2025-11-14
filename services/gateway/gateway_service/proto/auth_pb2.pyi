from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RegisterRequest(_message.Message):
    __slots__ = ("email", "password", "plan")
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    PLAN_FIELD_NUMBER: _ClassVar[int]
    email: str
    password: str
    plan: str
    def __init__(self, email: _Optional[str] = ..., password: _Optional[str] = ..., plan: _Optional[str] = ...) -> None: ...

class RegisterResponse(_message.Message):
    __slots__ = ("account_id", "email", "plan", "name")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PLAN_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    email: str
    plan: str
    name: str
    def __init__(self, account_id: _Optional[int] = ..., email: _Optional[str] = ..., plan: _Optional[str] = ..., name: _Optional[str] = ...) -> None: ...

class LoginRequest(_message.Message):
    __slots__ = ("email", "password")
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    email: str
    password: str
    def __init__(self, email: _Optional[str] = ..., password: _Optional[str] = ...) -> None: ...

class LoginResponse(_message.Message):
    __slots__ = ("account_id", "email", "plan", "access_token")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PLAN_FIELD_NUMBER: _ClassVar[int]
    ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    email: str
    plan: str
    access_token: str
    def __init__(self, account_id: _Optional[int] = ..., email: _Optional[str] = ..., plan: _Optional[str] = ..., access_token: _Optional[str] = ...) -> None: ...

class GetAccountRequest(_message.Message):
    __slots__ = ("account_id",)
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    def __init__(self, account_id: _Optional[int] = ...) -> None: ...

class GetAccountResponse(_message.Message):
    __slots__ = ("account_id", "email", "plan", "status", "name", "created_at")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PLAN_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    email: str
    plan: str
    status: str
    name: str
    created_at: str
    def __init__(self, account_id: _Optional[int] = ..., email: _Optional[str] = ..., plan: _Optional[str] = ..., status: _Optional[str] = ..., name: _Optional[str] = ..., created_at: _Optional[str] = ...) -> None: ...

class CreateProjectRequest(_message.Message):
    __slots__ = ("account_id", "name", "slug", "environment")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    name: str
    slug: str
    environment: str
    def __init__(self, account_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ..., environment: _Optional[str] = ...) -> None: ...

class CreateProjectResponse(_message.Message):
    __slots__ = ("project_id", "name", "slug", "environment", "retention_days", "daily_quota")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_FIELD_NUMBER: _ClassVar[int]
    RETENTION_DAYS_FIELD_NUMBER: _ClassVar[int]
    DAILY_QUOTA_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    name: str
    slug: str
    environment: str
    retention_days: int
    daily_quota: int
    def __init__(self, project_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ..., environment: _Optional[str] = ..., retention_days: _Optional[int] = ..., daily_quota: _Optional[int] = ...) -> None: ...

class GetProjectsRequest(_message.Message):
    __slots__ = ("account_id",)
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    def __init__(self, account_id: _Optional[int] = ...) -> None: ...

class ProjectInfo(_message.Message):
    __slots__ = ("project_id", "name", "slug", "environment", "retention_days", "daily_quota")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_FIELD_NUMBER: _ClassVar[int]
    RETENTION_DAYS_FIELD_NUMBER: _ClassVar[int]
    DAILY_QUOTA_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    name: str
    slug: str
    environment: str
    retention_days: int
    daily_quota: int
    def __init__(self, project_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ..., environment: _Optional[str] = ..., retention_days: _Optional[int] = ..., daily_quota: _Optional[int] = ...) -> None: ...

class GetProjectsResponse(_message.Message):
    __slots__ = ("projects",)
    PROJECTS_FIELD_NUMBER: _ClassVar[int]
    projects: _containers.RepeatedCompositeFieldContainer[ProjectInfo]
    def __init__(self, projects: _Optional[_Iterable[_Union[ProjectInfo, _Mapping]]] = ...) -> None: ...

class GetProjectByIdRequest(_message.Message):
    __slots__ = ("project_id",)
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    def __init__(self, project_id: _Optional[int] = ...) -> None: ...

class GetProjectByIdResponse(_message.Message):
    __slots__ = ("project_id", "name", "slug", "environment", "retention_days", "daily_quota")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_FIELD_NUMBER: _ClassVar[int]
    RETENTION_DAYS_FIELD_NUMBER: _ClassVar[int]
    DAILY_QUOTA_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    name: str
    slug: str
    environment: str
    retention_days: int
    daily_quota: int
    def __init__(self, project_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ..., environment: _Optional[str] = ..., retention_days: _Optional[int] = ..., daily_quota: _Optional[int] = ...) -> None: ...

class GetDailyUsageRequest(_message.Message):
    __slots__ = ("project_id", "date")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    DATE_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    date: str
    def __init__(self, project_id: _Optional[int] = ..., date: _Optional[str] = ...) -> None: ...

class GetDailyUsageResponse(_message.Message):
    __slots__ = ("log_count", "date")
    LOG_COUNT_FIELD_NUMBER: _ClassVar[int]
    DATE_FIELD_NUMBER: _ClassVar[int]
    log_count: int
    date: str
    def __init__(self, log_count: _Optional[int] = ..., date: _Optional[str] = ...) -> None: ...

class CreateApiKeyRequest(_message.Message):
    __slots__ = ("project_id", "name")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    name: str
    def __init__(self, project_id: _Optional[int] = ..., name: _Optional[str] = ...) -> None: ...

class CreateApiKeyResponse(_message.Message):
    __slots__ = ("key_id", "full_key", "key_prefix")
    KEY_ID_FIELD_NUMBER: _ClassVar[int]
    FULL_KEY_FIELD_NUMBER: _ClassVar[int]
    KEY_PREFIX_FIELD_NUMBER: _ClassVar[int]
    key_id: int
    full_key: str
    key_prefix: str
    def __init__(self, key_id: _Optional[int] = ..., full_key: _Optional[str] = ..., key_prefix: _Optional[str] = ...) -> None: ...

class ValidateApiKeyRequest(_message.Message):
    __slots__ = ("api_key",)
    API_KEY_FIELD_NUMBER: _ClassVar[int]
    api_key: str
    def __init__(self, api_key: _Optional[str] = ...) -> None: ...

class ValidateApiKeyResponse(_message.Message):
    __slots__ = ("valid", "project_id", "account_id", "daily_quota", "retention_days", "rate_limit_per_minute", "rate_limit_per_hour", "current_usage", "error_message")
    VALID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    DAILY_QUOTA_FIELD_NUMBER: _ClassVar[int]
    RETENTION_DAYS_FIELD_NUMBER: _ClassVar[int]
    RATE_LIMIT_PER_MINUTE_FIELD_NUMBER: _ClassVar[int]
    RATE_LIMIT_PER_HOUR_FIELD_NUMBER: _ClassVar[int]
    CURRENT_USAGE_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    valid: bool
    project_id: int
    account_id: int
    daily_quota: int
    retention_days: int
    rate_limit_per_minute: int
    rate_limit_per_hour: int
    current_usage: int
    error_message: str
    def __init__(self, valid: bool = ..., project_id: _Optional[int] = ..., account_id: _Optional[int] = ..., daily_quota: _Optional[int] = ..., retention_days: _Optional[int] = ..., rate_limit_per_minute: _Optional[int] = ..., rate_limit_per_hour: _Optional[int] = ..., current_usage: _Optional[int] = ..., error_message: _Optional[str] = ...) -> None: ...

class RevokeApiKeyRequest(_message.Message):
    __slots__ = ("key_id",)
    KEY_ID_FIELD_NUMBER: _ClassVar[int]
    key_id: int
    def __init__(self, key_id: _Optional[int] = ...) -> None: ...

class RevokeApiKeyResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...

class Panel(_message.Message):
    __slots__ = ("id", "name", "index", "project_id", "time_range_from", "time_range_to", "type")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    TIME_RANGE_FROM_FIELD_NUMBER: _ClassVar[int]
    TIME_RANGE_TO_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    index: int
    project_id: str
    time_range_from: str
    time_range_to: str
    type: str
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., index: _Optional[int] = ..., project_id: _Optional[str] = ..., time_range_from: _Optional[str] = ..., time_range_to: _Optional[str] = ..., type: _Optional[str] = ...) -> None: ...

class GetDashboardPanelsRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    def __init__(self, user_id: _Optional[int] = ...) -> None: ...

class GetDashboardPanelsResponse(_message.Message):
    __slots__ = ("panels",)
    PANELS_FIELD_NUMBER: _ClassVar[int]
    panels: _containers.RepeatedCompositeFieldContainer[Panel]
    def __init__(self, panels: _Optional[_Iterable[_Union[Panel, _Mapping]]] = ...) -> None: ...

class CreateDashboardPanelRequest(_message.Message):
    __slots__ = ("user_id", "name", "index", "project_id", "time_range_from", "time_range_to", "type")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    TIME_RANGE_FROM_FIELD_NUMBER: _ClassVar[int]
    TIME_RANGE_TO_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    name: str
    index: int
    project_id: str
    time_range_from: str
    time_range_to: str
    type: str
    def __init__(self, user_id: _Optional[int] = ..., name: _Optional[str] = ..., index: _Optional[int] = ..., project_id: _Optional[str] = ..., time_range_from: _Optional[str] = ..., time_range_to: _Optional[str] = ..., type: _Optional[str] = ...) -> None: ...

class CreateDashboardPanelResponse(_message.Message):
    __slots__ = ("panel",)
    PANEL_FIELD_NUMBER: _ClassVar[int]
    panel: Panel
    def __init__(self, panel: _Optional[_Union[Panel, _Mapping]] = ...) -> None: ...

class UpdateDashboardPanelRequest(_message.Message):
    __slots__ = ("user_id", "panel_id", "name", "index", "project_id", "time_range_from", "time_range_to", "type")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    PANEL_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    TIME_RANGE_FROM_FIELD_NUMBER: _ClassVar[int]
    TIME_RANGE_TO_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    panel_id: str
    name: str
    index: int
    project_id: str
    time_range_from: str
    time_range_to: str
    type: str
    def __init__(self, user_id: _Optional[int] = ..., panel_id: _Optional[str] = ..., name: _Optional[str] = ..., index: _Optional[int] = ..., project_id: _Optional[str] = ..., time_range_from: _Optional[str] = ..., time_range_to: _Optional[str] = ..., type: _Optional[str] = ...) -> None: ...

class UpdateDashboardPanelResponse(_message.Message):
    __slots__ = ("panel",)
    PANEL_FIELD_NUMBER: _ClassVar[int]
    panel: Panel
    def __init__(self, panel: _Optional[_Union[Panel, _Mapping]] = ...) -> None: ...

class DeleteDashboardPanelRequest(_message.Message):
    __slots__ = ("user_id", "panel_id")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    PANEL_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    panel_id: str
    def __init__(self, user_id: _Optional[int] = ..., panel_id: _Optional[str] = ...) -> None: ...

class DeleteDashboardPanelResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...
