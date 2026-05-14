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
    __slots__ = ("account_id", "email", "plan", "access_token", "refresh_token", "expires_in")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PLAN_FIELD_NUMBER: _ClassVar[int]
    ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    REFRESH_TOKEN_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_IN_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    email: str
    plan: str
    access_token: str
    refresh_token: str
    expires_in: int
    def __init__(self, account_id: _Optional[int] = ..., email: _Optional[str] = ..., plan: _Optional[str] = ..., access_token: _Optional[str] = ..., refresh_token: _Optional[str] = ..., expires_in: _Optional[int] = ...) -> None: ...

class RefreshTokenRequest(_message.Message):
    __slots__ = ("refresh_token",)
    REFRESH_TOKEN_FIELD_NUMBER: _ClassVar[int]
    refresh_token: str
    def __init__(self, refresh_token: _Optional[str] = ...) -> None: ...

class RefreshTokenResponse(_message.Message):
    __slots__ = ("access_token", "refresh_token", "expires_in", "account_id", "email")
    ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    REFRESH_TOKEN_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_IN_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    access_token: str
    refresh_token: str
    expires_in: int
    account_id: int
    email: str
    def __init__(self, access_token: _Optional[str] = ..., refresh_token: _Optional[str] = ..., expires_in: _Optional[int] = ..., account_id: _Optional[int] = ..., email: _Optional[str] = ...) -> None: ...

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

class UpdateAccountNameRequest(_message.Message):
    __slots__ = ("account_id", "name")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    name: str
    def __init__(self, account_id: _Optional[int] = ..., name: _Optional[str] = ...) -> None: ...

class UpdateAccountNameResponse(_message.Message):
    __slots__ = ("success", "name")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    success: bool
    name: str
    def __init__(self, success: bool = ..., name: _Optional[str] = ...) -> None: ...

class ChangePasswordRequest(_message.Message):
    __slots__ = ("account_id", "old_password", "new_password")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    OLD_PASSWORD_FIELD_NUMBER: _ClassVar[int]
    NEW_PASSWORD_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    old_password: str
    new_password: str
    def __init__(self, account_id: _Optional[int] = ..., old_password: _Optional[str] = ..., new_password: _Optional[str] = ...) -> None: ...

class ChangePasswordResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...

class GetNotificationPreferencesRequest(_message.Message):
    __slots__ = ("account_id",)
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    def __init__(self, account_id: _Optional[int] = ...) -> None: ...

class NotificationPreferences(_message.Message):
    __slots__ = ("enabled", "projects")
    class ProjectsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: int
        value: ProjectNotificationSettings
        def __init__(self, key: _Optional[int] = ..., value: _Optional[_Union[ProjectNotificationSettings, _Mapping]] = ...) -> None: ...
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    PROJECTS_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    projects: _containers.MessageMap[int, ProjectNotificationSettings]
    def __init__(self, enabled: bool = ..., projects: _Optional[_Mapping[int, ProjectNotificationSettings]] = ...) -> None: ...

class ProjectNotificationSettings(_message.Message):
    __slots__ = ("enabled", "levels", "types")
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    LEVELS_FIELD_NUMBER: _ClassVar[int]
    TYPES_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    levels: _containers.RepeatedScalarFieldContainer[str]
    types: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, enabled: bool = ..., levels: _Optional[_Iterable[str]] = ..., types: _Optional[_Iterable[str]] = ...) -> None: ...

class GetNotificationPreferencesResponse(_message.Message):
    __slots__ = ("preferences",)
    PREFERENCES_FIELD_NUMBER: _ClassVar[int]
    preferences: NotificationPreferences
    def __init__(self, preferences: _Optional[_Union[NotificationPreferences, _Mapping]] = ...) -> None: ...

class UpdateNotificationPreferencesRequest(_message.Message):
    __slots__ = ("account_id", "preferences")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    PREFERENCES_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    preferences: NotificationPreferences
    def __init__(self, account_id: _Optional[int] = ..., preferences: _Optional[_Union[NotificationPreferences, _Mapping]] = ...) -> None: ...

class UpdateNotificationPreferencesResponse(_message.Message):
    __slots__ = ("success", "preferences")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    PREFERENCES_FIELD_NUMBER: _ClassVar[int]
    success: bool
    preferences: NotificationPreferences
    def __init__(self, success: bool = ..., preferences: _Optional[_Union[NotificationPreferences, _Mapping]] = ...) -> None: ...

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
    __slots__ = ("project_id", "name", "slug", "environment", "retention_days", "daily_quota", "available_routes", "role")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_FIELD_NUMBER: _ClassVar[int]
    RETENTION_DAYS_FIELD_NUMBER: _ClassVar[int]
    DAILY_QUOTA_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_ROUTES_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    name: str
    slug: str
    environment: str
    retention_days: int
    daily_quota: int
    available_routes: _containers.RepeatedScalarFieldContainer[str]
    role: str
    def __init__(self, project_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ..., environment: _Optional[str] = ..., retention_days: _Optional[int] = ..., daily_quota: _Optional[int] = ..., available_routes: _Optional[_Iterable[str]] = ..., role: _Optional[str] = ...) -> None: ...

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
    __slots__ = ("project_id", "name", "slug", "environment", "retention_days", "daily_quota", "available_routes")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_FIELD_NUMBER: _ClassVar[int]
    RETENTION_DAYS_FIELD_NUMBER: _ClassVar[int]
    DAILY_QUOTA_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_ROUTES_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    name: str
    slug: str
    environment: str
    retention_days: int
    daily_quota: int
    available_routes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, project_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ..., environment: _Optional[str] = ..., retention_days: _Optional[int] = ..., daily_quota: _Optional[int] = ..., available_routes: _Optional[_Iterable[str]] = ...) -> None: ...

class GenerateInviteCodeRequest(_message.Message):
    __slots__ = ("project_id", "requester_account_id")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    REQUESTER_ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    requester_account_id: int
    def __init__(self, project_id: _Optional[int] = ..., requester_account_id: _Optional[int] = ...) -> None: ...

class GenerateInviteCodeResponse(_message.Message):
    __slots__ = ("code", "expires_at")
    CODE_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    code: str
    expires_at: str
    def __init__(self, code: _Optional[str] = ..., expires_at: _Optional[str] = ...) -> None: ...

class AcceptInviteCodeRequest(_message.Message):
    __slots__ = ("code", "account_id")
    CODE_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    code: str
    account_id: int
    def __init__(self, code: _Optional[str] = ..., account_id: _Optional[int] = ...) -> None: ...

class AcceptInviteCodeResponse(_message.Message):
    __slots__ = ("project_id", "role", "project_name", "project_slug")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    PROJECT_NAME_FIELD_NUMBER: _ClassVar[int]
    PROJECT_SLUG_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    role: str
    project_name: str
    project_slug: str
    def __init__(self, project_id: _Optional[int] = ..., role: _Optional[str] = ..., project_name: _Optional[str] = ..., project_slug: _Optional[str] = ...) -> None: ...

class MemberInfo(_message.Message):
    __slots__ = ("account_id", "email", "name", "role", "joined_at")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    JOINED_AT_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    email: str
    name: str
    role: str
    joined_at: str
    def __init__(self, account_id: _Optional[int] = ..., email: _Optional[str] = ..., name: _Optional[str] = ..., role: _Optional[str] = ..., joined_at: _Optional[str] = ...) -> None: ...

class ListProjectMembersRequest(_message.Message):
    __slots__ = ("project_id", "requester_account_id")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    REQUESTER_ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    requester_account_id: int
    def __init__(self, project_id: _Optional[int] = ..., requester_account_id: _Optional[int] = ...) -> None: ...

class ListProjectMembersResponse(_message.Message):
    __slots__ = ("members",)
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    members: _containers.RepeatedCompositeFieldContainer[MemberInfo]
    def __init__(self, members: _Optional[_Iterable[_Union[MemberInfo, _Mapping]]] = ...) -> None: ...

class RemoveProjectMemberRequest(_message.Message):
    __slots__ = ("project_id", "account_id", "requester_account_id")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    REQUESTER_ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    account_id: int
    requester_account_id: int
    def __init__(self, project_id: _Optional[int] = ..., account_id: _Optional[int] = ..., requester_account_id: _Optional[int] = ...) -> None: ...

class RemoveProjectMemberResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...

class LeaveProjectRequest(_message.Message):
    __slots__ = ("project_id", "account_id")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    account_id: int
    def __init__(self, project_id: _Optional[int] = ..., account_id: _Optional[int] = ...) -> None: ...

class LeaveProjectResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...

class GetProjectRoleRequest(_message.Message):
    __slots__ = ("project_id", "account_id")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    account_id: int
    def __init__(self, project_id: _Optional[int] = ..., account_id: _Optional[int] = ...) -> None: ...

class GetProjectRoleResponse(_message.Message):
    __slots__ = ("is_member", "role")
    IS_MEMBER_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    is_member: bool
    role: str
    def __init__(self, is_member: bool = ..., role: _Optional[str] = ...) -> None: ...

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

class ListApiKeysRequest(_message.Message):
    __slots__ = ("project_id",)
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    def __init__(self, project_id: _Optional[int] = ...) -> None: ...

class ApiKeyInfo(_message.Message):
    __slots__ = ("key_id", "project_id", "name", "key_prefix", "status", "created_at", "last_used_at")
    KEY_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    KEY_PREFIX_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_USED_AT_FIELD_NUMBER: _ClassVar[int]
    key_id: int
    project_id: int
    name: str
    key_prefix: str
    status: str
    created_at: str
    last_used_at: str
    def __init__(self, key_id: _Optional[int] = ..., project_id: _Optional[int] = ..., name: _Optional[str] = ..., key_prefix: _Optional[str] = ..., status: _Optional[str] = ..., created_at: _Optional[str] = ..., last_used_at: _Optional[str] = ...) -> None: ...

class ListApiKeysResponse(_message.Message):
    __slots__ = ("api_keys",)
    API_KEYS_FIELD_NUMBER: _ClassVar[int]
    api_keys: _containers.RepeatedCompositeFieldContainer[ApiKeyInfo]
    def __init__(self, api_keys: _Optional[_Iterable[_Union[ApiKeyInfo, _Mapping]]] = ...) -> None: ...

class PanelLayout(_message.Message):
    __slots__ = ("x", "y", "w", "h")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    W_FIELD_NUMBER: _ClassVar[int]
    H_FIELD_NUMBER: _ClassVar[int]
    x: int
    y: int
    w: int
    h: int
    def __init__(self, x: _Optional[int] = ..., y: _Optional[int] = ..., w: _Optional[int] = ..., h: _Optional[int] = ...) -> None: ...

class Panel(_message.Message):
    __slots__ = ("id", "name", "index", "project_id", "period", "periodFrom", "periodTo", "type", "endpoint", "routes", "statistic", "layout", "trace_id", "service_filter", "operation_filter", "min_duration_ms", "has_error", "limit", "metric_name", "tag_filter_json", "agg", "viz", "step")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    PERIODFROM_FIELD_NUMBER: _ClassVar[int]
    PERIODTO_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ENDPOINT_FIELD_NUMBER: _ClassVar[int]
    ROUTES_FIELD_NUMBER: _ClassVar[int]
    STATISTIC_FIELD_NUMBER: _ClassVar[int]
    LAYOUT_FIELD_NUMBER: _ClassVar[int]
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SERVICE_FILTER_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FILTER_FIELD_NUMBER: _ClassVar[int]
    MIN_DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    HAS_ERROR_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    METRIC_NAME_FIELD_NUMBER: _ClassVar[int]
    TAG_FILTER_JSON_FIELD_NUMBER: _ClassVar[int]
    AGG_FIELD_NUMBER: _ClassVar[int]
    VIZ_FIELD_NUMBER: _ClassVar[int]
    STEP_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    index: int
    project_id: str
    period: str
    periodFrom: str
    periodTo: str
    type: str
    endpoint: str
    routes: _containers.RepeatedScalarFieldContainer[str]
    statistic: str
    layout: PanelLayout
    trace_id: str
    service_filter: str
    operation_filter: str
    min_duration_ms: int
    has_error: bool
    limit: int
    metric_name: str
    tag_filter_json: str
    agg: str
    viz: str
    step: str
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., index: _Optional[int] = ..., project_id: _Optional[str] = ..., period: _Optional[str] = ..., periodFrom: _Optional[str] = ..., periodTo: _Optional[str] = ..., type: _Optional[str] = ..., endpoint: _Optional[str] = ..., routes: _Optional[_Iterable[str]] = ..., statistic: _Optional[str] = ..., layout: _Optional[_Union[PanelLayout, _Mapping]] = ..., trace_id: _Optional[str] = ..., service_filter: _Optional[str] = ..., operation_filter: _Optional[str] = ..., min_duration_ms: _Optional[int] = ..., has_error: bool = ..., limit: _Optional[int] = ..., metric_name: _Optional[str] = ..., tag_filter_json: _Optional[str] = ..., agg: _Optional[str] = ..., viz: _Optional[str] = ..., step: _Optional[str] = ...) -> None: ...

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
    __slots__ = ("user_id", "name", "index", "project_id", "period", "periodFrom", "periodTo", "type", "endpoint", "routes", "statistic", "layout", "trace_id", "service_filter", "operation_filter", "min_duration_ms", "has_error", "limit", "metric_name", "tag_filter_json", "agg", "viz", "step")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    PERIODFROM_FIELD_NUMBER: _ClassVar[int]
    PERIODTO_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ENDPOINT_FIELD_NUMBER: _ClassVar[int]
    ROUTES_FIELD_NUMBER: _ClassVar[int]
    STATISTIC_FIELD_NUMBER: _ClassVar[int]
    LAYOUT_FIELD_NUMBER: _ClassVar[int]
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SERVICE_FILTER_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FILTER_FIELD_NUMBER: _ClassVar[int]
    MIN_DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    HAS_ERROR_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    METRIC_NAME_FIELD_NUMBER: _ClassVar[int]
    TAG_FILTER_JSON_FIELD_NUMBER: _ClassVar[int]
    AGG_FIELD_NUMBER: _ClassVar[int]
    VIZ_FIELD_NUMBER: _ClassVar[int]
    STEP_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    name: str
    index: int
    project_id: str
    period: str
    periodFrom: str
    periodTo: str
    type: str
    endpoint: str
    routes: _containers.RepeatedScalarFieldContainer[str]
    statistic: str
    layout: PanelLayout
    trace_id: str
    service_filter: str
    operation_filter: str
    min_duration_ms: int
    has_error: bool
    limit: int
    metric_name: str
    tag_filter_json: str
    agg: str
    viz: str
    step: str
    def __init__(self, user_id: _Optional[int] = ..., name: _Optional[str] = ..., index: _Optional[int] = ..., project_id: _Optional[str] = ..., period: _Optional[str] = ..., periodFrom: _Optional[str] = ..., periodTo: _Optional[str] = ..., type: _Optional[str] = ..., endpoint: _Optional[str] = ..., routes: _Optional[_Iterable[str]] = ..., statistic: _Optional[str] = ..., layout: _Optional[_Union[PanelLayout, _Mapping]] = ..., trace_id: _Optional[str] = ..., service_filter: _Optional[str] = ..., operation_filter: _Optional[str] = ..., min_duration_ms: _Optional[int] = ..., has_error: bool = ..., limit: _Optional[int] = ..., metric_name: _Optional[str] = ..., tag_filter_json: _Optional[str] = ..., agg: _Optional[str] = ..., viz: _Optional[str] = ..., step: _Optional[str] = ...) -> None: ...

class CreateDashboardPanelResponse(_message.Message):
    __slots__ = ("panel",)
    PANEL_FIELD_NUMBER: _ClassVar[int]
    panel: Panel
    def __init__(self, panel: _Optional[_Union[Panel, _Mapping]] = ...) -> None: ...

class UpdateDashboardPanelRequest(_message.Message):
    __slots__ = ("user_id", "panel_id", "name", "index", "project_id", "period", "periodFrom", "periodTo", "type", "endpoint", "routes", "statistic", "layout", "trace_id", "service_filter", "operation_filter", "min_duration_ms", "has_error", "limit", "metric_name", "tag_filter_json", "agg", "viz", "step")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    PANEL_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    PERIODFROM_FIELD_NUMBER: _ClassVar[int]
    PERIODTO_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ENDPOINT_FIELD_NUMBER: _ClassVar[int]
    ROUTES_FIELD_NUMBER: _ClassVar[int]
    STATISTIC_FIELD_NUMBER: _ClassVar[int]
    LAYOUT_FIELD_NUMBER: _ClassVar[int]
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SERVICE_FILTER_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FILTER_FIELD_NUMBER: _ClassVar[int]
    MIN_DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    HAS_ERROR_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    METRIC_NAME_FIELD_NUMBER: _ClassVar[int]
    TAG_FILTER_JSON_FIELD_NUMBER: _ClassVar[int]
    AGG_FIELD_NUMBER: _ClassVar[int]
    VIZ_FIELD_NUMBER: _ClassVar[int]
    STEP_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    panel_id: str
    name: str
    index: int
    project_id: str
    period: str
    periodFrom: str
    periodTo: str
    type: str
    endpoint: str
    routes: _containers.RepeatedScalarFieldContainer[str]
    statistic: str
    layout: PanelLayout
    trace_id: str
    service_filter: str
    operation_filter: str
    min_duration_ms: int
    has_error: bool
    limit: int
    metric_name: str
    tag_filter_json: str
    agg: str
    viz: str
    step: str
    def __init__(self, user_id: _Optional[int] = ..., panel_id: _Optional[str] = ..., name: _Optional[str] = ..., index: _Optional[int] = ..., project_id: _Optional[str] = ..., period: _Optional[str] = ..., periodFrom: _Optional[str] = ..., periodTo: _Optional[str] = ..., type: _Optional[str] = ..., endpoint: _Optional[str] = ..., routes: _Optional[_Iterable[str]] = ..., statistic: _Optional[str] = ..., layout: _Optional[_Union[PanelLayout, _Mapping]] = ..., trace_id: _Optional[str] = ..., service_filter: _Optional[str] = ..., operation_filter: _Optional[str] = ..., min_duration_ms: _Optional[int] = ..., has_error: bool = ..., limit: _Optional[int] = ..., metric_name: _Optional[str] = ..., tag_filter_json: _Optional[str] = ..., agg: _Optional[str] = ..., viz: _Optional[str] = ..., step: _Optional[str] = ...) -> None: ...

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

class NotificationItem(_message.Message):
    __slots__ = ("id", "user_id", "project_id", "kind", "severity", "payload", "created_at", "read_at", "expires_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    READ_AT_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    id: int
    user_id: int
    project_id: int
    kind: str
    severity: int
    payload: str
    created_at: str
    read_at: str
    expires_at: str
    def __init__(self, id: _Optional[int] = ..., user_id: _Optional[int] = ..., project_id: _Optional[int] = ..., kind: _Optional[str] = ..., severity: _Optional[int] = ..., payload: _Optional[str] = ..., created_at: _Optional[str] = ..., read_at: _Optional[str] = ..., expires_at: _Optional[str] = ...) -> None: ...

class ListNotificationsRequest(_message.Message):
    __slots__ = ("user_id", "unread_only", "limit", "before_id")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    UNREAD_ONLY_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    BEFORE_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    unread_only: bool
    limit: int
    before_id: int
    def __init__(self, user_id: _Optional[int] = ..., unread_only: bool = ..., limit: _Optional[int] = ..., before_id: _Optional[int] = ...) -> None: ...

class ListNotificationsResponse(_message.Message):
    __slots__ = ("notifications", "has_more")
    NOTIFICATIONS_FIELD_NUMBER: _ClassVar[int]
    HAS_MORE_FIELD_NUMBER: _ClassVar[int]
    notifications: _containers.RepeatedCompositeFieldContainer[NotificationItem]
    has_more: bool
    def __init__(self, notifications: _Optional[_Iterable[_Union[NotificationItem, _Mapping]]] = ..., has_more: bool = ...) -> None: ...

class GetUnreadNotificationCountRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    def __init__(self, user_id: _Optional[int] = ...) -> None: ...

class GetUnreadNotificationCountResponse(_message.Message):
    __slots__ = ("count",)
    COUNT_FIELD_NUMBER: _ClassVar[int]
    count: int
    def __init__(self, count: _Optional[int] = ...) -> None: ...

class MarkNotificationReadRequest(_message.Message):
    __slots__ = ("notification_id", "user_id")
    NOTIFICATION_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    notification_id: int
    user_id: int
    def __init__(self, notification_id: _Optional[int] = ..., user_id: _Optional[int] = ...) -> None: ...

class MarkNotificationReadResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...

class MarkAllNotificationsReadRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    def __init__(self, user_id: _Optional[int] = ...) -> None: ...

class MarkAllNotificationsReadResponse(_message.Message):
    __slots__ = ("updated_count",)
    UPDATED_COUNT_FIELD_NUMBER: _ClassVar[int]
    updated_count: int
    def __init__(self, updated_count: _Optional[int] = ...) -> None: ...

class DeleteNotificationRequest(_message.Message):
    __slots__ = ("notification_id", "user_id")
    NOTIFICATION_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    notification_id: int
    user_id: int
    def __init__(self, notification_id: _Optional[int] = ..., user_id: _Optional[int] = ...) -> None: ...

class DeleteNotificationResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...

class CreateNotificationRequest(_message.Message):
    __slots__ = ("user_id", "project_id", "kind", "severity", "payload")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    project_id: int
    kind: str
    severity: int
    payload: str
    def __init__(self, user_id: _Optional[int] = ..., project_id: _Optional[int] = ..., kind: _Optional[str] = ..., severity: _Optional[int] = ..., payload: _Optional[str] = ...) -> None: ...

class CreateNotificationResponse(_message.Message):
    __slots__ = ("notification",)
    NOTIFICATION_FIELD_NUMBER: _ClassVar[int]
    notification: NotificationItem
    def __init__(self, notification: _Optional[_Union[NotificationItem, _Mapping]] = ...) -> None: ...

class AlertRule(_message.Message):
    __slots__ = ("id", "project_id", "name", "enabled", "metric", "tag_filter", "comparator", "threshold", "window_seconds", "cooldown_seconds", "severity", "channels", "last_fired_at", "last_state", "created_at", "updated_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    METRIC_FIELD_NUMBER: _ClassVar[int]
    TAG_FILTER_FIELD_NUMBER: _ClassVar[int]
    COMPARATOR_FIELD_NUMBER: _ClassVar[int]
    THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    WINDOW_SECONDS_FIELD_NUMBER: _ClassVar[int]
    COOLDOWN_SECONDS_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    CHANNELS_FIELD_NUMBER: _ClassVar[int]
    LAST_FIRED_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_STATE_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: int
    project_id: int
    name: str
    enabled: bool
    metric: str
    tag_filter: str
    comparator: str
    threshold: float
    window_seconds: int
    cooldown_seconds: int
    severity: int
    channels: str
    last_fired_at: str
    last_state: str
    created_at: str
    updated_at: str
    def __init__(self, id: _Optional[int] = ..., project_id: _Optional[int] = ..., name: _Optional[str] = ..., enabled: bool = ..., metric: _Optional[str] = ..., tag_filter: _Optional[str] = ..., comparator: _Optional[str] = ..., threshold: _Optional[float] = ..., window_seconds: _Optional[int] = ..., cooldown_seconds: _Optional[int] = ..., severity: _Optional[int] = ..., channels: _Optional[str] = ..., last_fired_at: _Optional[str] = ..., last_state: _Optional[str] = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ...) -> None: ...

class ListAlertRulesRequest(_message.Message):
    __slots__ = ("project_id",)
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    def __init__(self, project_id: _Optional[int] = ...) -> None: ...

class ListAlertRulesResponse(_message.Message):
    __slots__ = ("rules",)
    RULES_FIELD_NUMBER: _ClassVar[int]
    rules: _containers.RepeatedCompositeFieldContainer[AlertRule]
    def __init__(self, rules: _Optional[_Iterable[_Union[AlertRule, _Mapping]]] = ...) -> None: ...

class GetAlertRuleRequest(_message.Message):
    __slots__ = ("rule_id", "project_id")
    RULE_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    rule_id: int
    project_id: int
    def __init__(self, rule_id: _Optional[int] = ..., project_id: _Optional[int] = ...) -> None: ...

class GetAlertRuleResponse(_message.Message):
    __slots__ = ("rule", "found")
    RULE_FIELD_NUMBER: _ClassVar[int]
    FOUND_FIELD_NUMBER: _ClassVar[int]
    rule: AlertRule
    found: bool
    def __init__(self, rule: _Optional[_Union[AlertRule, _Mapping]] = ..., found: bool = ...) -> None: ...

class CreateAlertRuleRequest(_message.Message):
    __slots__ = ("project_id", "name", "metric", "tag_filter", "comparator", "threshold", "window_seconds", "cooldown_seconds", "severity")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    METRIC_FIELD_NUMBER: _ClassVar[int]
    TAG_FILTER_FIELD_NUMBER: _ClassVar[int]
    COMPARATOR_FIELD_NUMBER: _ClassVar[int]
    THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    WINDOW_SECONDS_FIELD_NUMBER: _ClassVar[int]
    COOLDOWN_SECONDS_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    name: str
    metric: str
    tag_filter: str
    comparator: str
    threshold: float
    window_seconds: int
    cooldown_seconds: int
    severity: int
    def __init__(self, project_id: _Optional[int] = ..., name: _Optional[str] = ..., metric: _Optional[str] = ..., tag_filter: _Optional[str] = ..., comparator: _Optional[str] = ..., threshold: _Optional[float] = ..., window_seconds: _Optional[int] = ..., cooldown_seconds: _Optional[int] = ..., severity: _Optional[int] = ...) -> None: ...

class CreateAlertRuleResponse(_message.Message):
    __slots__ = ("rule",)
    RULE_FIELD_NUMBER: _ClassVar[int]
    rule: AlertRule
    def __init__(self, rule: _Optional[_Union[AlertRule, _Mapping]] = ...) -> None: ...

class UpdateAlertRuleRequest(_message.Message):
    __slots__ = ("rule_id", "project_id", "name", "enabled", "threshold", "cooldown_seconds", "channels")
    RULE_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    COOLDOWN_SECONDS_FIELD_NUMBER: _ClassVar[int]
    CHANNELS_FIELD_NUMBER: _ClassVar[int]
    rule_id: int
    project_id: int
    name: str
    enabled: bool
    threshold: float
    cooldown_seconds: int
    channels: str
    def __init__(self, rule_id: _Optional[int] = ..., project_id: _Optional[int] = ..., name: _Optional[str] = ..., enabled: bool = ..., threshold: _Optional[float] = ..., cooldown_seconds: _Optional[int] = ..., channels: _Optional[str] = ...) -> None: ...

class UpdateAlertRuleResponse(_message.Message):
    __slots__ = ("rule",)
    RULE_FIELD_NUMBER: _ClassVar[int]
    rule: AlertRule
    def __init__(self, rule: _Optional[_Union[AlertRule, _Mapping]] = ...) -> None: ...

class DeleteAlertRuleRequest(_message.Message):
    __slots__ = ("rule_id", "project_id")
    RULE_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    rule_id: int
    project_id: int
    def __init__(self, rule_id: _Optional[int] = ..., project_id: _Optional[int] = ...) -> None: ...

class DeleteAlertRuleResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...

class AlertChannel(_message.Message):
    __slots__ = ("id", "project_id", "user_id", "kind", "name", "config", "enabled", "created_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: int
    project_id: int
    user_id: int
    kind: str
    name: str
    config: str
    enabled: bool
    created_at: str
    def __init__(self, id: _Optional[int] = ..., project_id: _Optional[int] = ..., user_id: _Optional[int] = ..., kind: _Optional[str] = ..., name: _Optional[str] = ..., config: _Optional[str] = ..., enabled: bool = ..., created_at: _Optional[str] = ...) -> None: ...

class ListAlertChannelsRequest(_message.Message):
    __slots__ = ("project_id",)
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    def __init__(self, project_id: _Optional[int] = ...) -> None: ...

class ListAlertChannelsResponse(_message.Message):
    __slots__ = ("channels",)
    CHANNELS_FIELD_NUMBER: _ClassVar[int]
    channels: _containers.RepeatedCompositeFieldContainer[AlertChannel]
    def __init__(self, channels: _Optional[_Iterable[_Union[AlertChannel, _Mapping]]] = ...) -> None: ...

class GetAlertChannelRequest(_message.Message):
    __slots__ = ("channel_id", "project_id")
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    channel_id: int
    project_id: int
    def __init__(self, channel_id: _Optional[int] = ..., project_id: _Optional[int] = ...) -> None: ...

class GetAlertChannelResponse(_message.Message):
    __slots__ = ("channel", "found")
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    FOUND_FIELD_NUMBER: _ClassVar[int]
    channel: AlertChannel
    found: bool
    def __init__(self, channel: _Optional[_Union[AlertChannel, _Mapping]] = ..., found: bool = ...) -> None: ...

class CreateAlertChannelRequest(_message.Message):
    __slots__ = ("project_id", "user_id", "kind", "name", "config")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    user_id: int
    kind: str
    name: str
    config: str
    def __init__(self, project_id: _Optional[int] = ..., user_id: _Optional[int] = ..., kind: _Optional[str] = ..., name: _Optional[str] = ..., config: _Optional[str] = ...) -> None: ...

class CreateAlertChannelResponse(_message.Message):
    __slots__ = ("channel",)
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    channel: AlertChannel
    def __init__(self, channel: _Optional[_Union[AlertChannel, _Mapping]] = ...) -> None: ...

class UpdateAlertChannelRequest(_message.Message):
    __slots__ = ("channel_id", "project_id", "name", "enabled", "config")
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    channel_id: int
    project_id: int
    name: str
    enabled: bool
    config: str
    def __init__(self, channel_id: _Optional[int] = ..., project_id: _Optional[int] = ..., name: _Optional[str] = ..., enabled: bool = ..., config: _Optional[str] = ...) -> None: ...

class UpdateAlertChannelResponse(_message.Message):
    __slots__ = ("channel",)
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    channel: AlertChannel
    def __init__(self, channel: _Optional[_Union[AlertChannel, _Mapping]] = ...) -> None: ...

class DeleteAlertChannelRequest(_message.Message):
    __slots__ = ("channel_id", "project_id")
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    channel_id: int
    project_id: int
    def __init__(self, channel_id: _Optional[int] = ..., project_id: _Optional[int] = ...) -> None: ...

class DeleteAlertChannelResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...

class AlertNotificationPreference(_message.Message):
    __slots__ = ("user_id", "project_id", "rule_id", "severity", "muted", "channels")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    RULE_ID_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    MUTED_FIELD_NUMBER: _ClassVar[int]
    CHANNELS_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    project_id: int
    rule_id: int
    severity: int
    muted: bool
    channels: str
    def __init__(self, user_id: _Optional[int] = ..., project_id: _Optional[int] = ..., rule_id: _Optional[int] = ..., severity: _Optional[int] = ..., muted: bool = ..., channels: _Optional[str] = ...) -> None: ...

class GetAlertNotificationPreferencesRequest(_message.Message):
    __slots__ = ("user_id", "project_id")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    project_id: int
    def __init__(self, user_id: _Optional[int] = ..., project_id: _Optional[int] = ...) -> None: ...

class GetAlertNotificationPreferencesResponse(_message.Message):
    __slots__ = ("preferences",)
    PREFERENCES_FIELD_NUMBER: _ClassVar[int]
    preferences: _containers.RepeatedCompositeFieldContainer[AlertNotificationPreference]
    def __init__(self, preferences: _Optional[_Iterable[_Union[AlertNotificationPreference, _Mapping]]] = ...) -> None: ...

class UpsertAlertNotificationPreferenceRequest(_message.Message):
    __slots__ = ("user_id", "project_id", "rule_id", "severity", "muted", "channels")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    RULE_ID_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    MUTED_FIELD_NUMBER: _ClassVar[int]
    CHANNELS_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    project_id: int
    rule_id: int
    severity: int
    muted: bool
    channels: str
    def __init__(self, user_id: _Optional[int] = ..., project_id: _Optional[int] = ..., rule_id: _Optional[int] = ..., severity: _Optional[int] = ..., muted: bool = ..., channels: _Optional[str] = ...) -> None: ...

class UpsertAlertNotificationPreferenceResponse(_message.Message):
    __slots__ = ("preference",)
    PREFERENCE_FIELD_NUMBER: _ClassVar[int]
    preference: AlertNotificationPreference
    def __init__(self, preference: _Optional[_Union[AlertNotificationPreference, _Mapping]] = ...) -> None: ...
