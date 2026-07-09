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
    __slots__ = ("account_id", "email", "plan", "name", "email_verification_token")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PLAN_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    EMAIL_VERIFICATION_TOKEN_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    email: str
    plan: str
    name: str
    email_verification_token: str
    def __init__(self, account_id: _Optional[int] = ..., email: _Optional[str] = ..., plan: _Optional[str] = ..., name: _Optional[str] = ..., email_verification_token: _Optional[str] = ...) -> None: ...

class LoginRequest(_message.Message):
    __slots__ = ("email", "password")
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    email: str
    password: str
    def __init__(self, email: _Optional[str] = ..., password: _Optional[str] = ...) -> None: ...

class LoginResponse(_message.Message):
    __slots__ = ("account_id", "email", "plan", "access_token", "refresh_token", "expires_in", "requires_2fa")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PLAN_FIELD_NUMBER: _ClassVar[int]
    ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    REFRESH_TOKEN_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_IN_FIELD_NUMBER: _ClassVar[int]
    REQUIRES_2FA_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    email: str
    plan: str
    access_token: str
    refresh_token: str
    expires_in: int
    requires_2fa: bool
    def __init__(self, account_id: _Optional[int] = ..., email: _Optional[str] = ..., plan: _Optional[str] = ..., access_token: _Optional[str] = ..., refresh_token: _Optional[str] = ..., expires_in: _Optional[int] = ..., requires_2fa: bool = ...) -> None: ...

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
    __slots__ = ("account_id", "email", "plan", "status", "name", "created_at", "email_verified", "totp_enabled")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PLAN_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    EMAIL_VERIFIED_FIELD_NUMBER: _ClassVar[int]
    TOTP_ENABLED_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    email: str
    plan: str
    status: str
    name: str
    created_at: str
    email_verified: bool
    totp_enabled: bool
    def __init__(self, account_id: _Optional[int] = ..., email: _Optional[str] = ..., plan: _Optional[str] = ..., status: _Optional[str] = ..., name: _Optional[str] = ..., created_at: _Optional[str] = ..., email_verified: bool = ..., totp_enabled: bool = ...) -> None: ...

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

class VerifyEmailRequest(_message.Message):
    __slots__ = ("token",)
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    token: str
    def __init__(self, token: _Optional[str] = ...) -> None: ...

class VerifyEmailResponse(_message.Message):
    __slots__ = ("success", "error_message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error_message: str
    def __init__(self, success: bool = ..., error_message: _Optional[str] = ...) -> None: ...

class ResendVerificationEmailRequest(_message.Message):
    __slots__ = ("account_id",)
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    def __init__(self, account_id: _Optional[int] = ...) -> None: ...

class ResendVerificationEmailResponse(_message.Message):
    __slots__ = ("success", "already_verified", "email", "verification_token", "error_message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ALREADY_VERIFIED_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    VERIFICATION_TOKEN_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    already_verified: bool
    email: str
    verification_token: str
    error_message: str
    def __init__(self, success: bool = ..., already_verified: bool = ..., email: _Optional[str] = ..., verification_token: _Optional[str] = ..., error_message: _Optional[str] = ...) -> None: ...

class Setup2FARequest(_message.Message):
    __slots__ = ("account_id",)
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    def __init__(self, account_id: _Optional[int] = ...) -> None: ...

class Setup2FAResponse(_message.Message):
    __slots__ = ("secret", "provisioning_uri")
    SECRET_FIELD_NUMBER: _ClassVar[int]
    PROVISIONING_URI_FIELD_NUMBER: _ClassVar[int]
    secret: str
    provisioning_uri: str
    def __init__(self, secret: _Optional[str] = ..., provisioning_uri: _Optional[str] = ...) -> None: ...

class Verify2FASetupRequest(_message.Message):
    __slots__ = ("account_id", "code")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    code: str
    def __init__(self, account_id: _Optional[int] = ..., code: _Optional[str] = ...) -> None: ...

class Verify2FASetupResponse(_message.Message):
    __slots__ = ("success", "backup_codes", "error_message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    BACKUP_CODES_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    backup_codes: _containers.RepeatedScalarFieldContainer[str]
    error_message: str
    def __init__(self, success: bool = ..., backup_codes: _Optional[_Iterable[str]] = ..., error_message: _Optional[str] = ...) -> None: ...

class Disable2FARequest(_message.Message):
    __slots__ = ("account_id", "password")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    password: str
    def __init__(self, account_id: _Optional[int] = ..., password: _Optional[str] = ...) -> None: ...

class Disable2FAResponse(_message.Message):
    __slots__ = ("success", "error_message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error_message: str
    def __init__(self, success: bool = ..., error_message: _Optional[str] = ...) -> None: ...

class VerifyTOTPLoginRequest(_message.Message):
    __slots__ = ("account_id", "code", "device_info")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    DEVICE_INFO_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    code: str
    device_info: str
    def __init__(self, account_id: _Optional[int] = ..., code: _Optional[str] = ..., device_info: _Optional[str] = ...) -> None: ...

class VerifyTOTPLoginResponse(_message.Message):
    __slots__ = ("success", "access_token", "refresh_token", "expires_in", "account_id", "email", "error_message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    REFRESH_TOKEN_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_IN_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    access_token: str
    refresh_token: str
    expires_in: int
    account_id: int
    email: str
    error_message: str
    def __init__(self, success: bool = ..., access_token: _Optional[str] = ..., refresh_token: _Optional[str] = ..., expires_in: _Optional[int] = ..., account_id: _Optional[int] = ..., email: _Optional[str] = ..., error_message: _Optional[str] = ...) -> None: ...

class SessionInfo(_message.Message):
    __slots__ = ("id", "device_info", "created_at", "last_used_at", "expires_at", "is_current")
    ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_INFO_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_USED_AT_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    IS_CURRENT_FIELD_NUMBER: _ClassVar[int]
    id: int
    device_info: str
    created_at: str
    last_used_at: str
    expires_at: str
    is_current: bool
    def __init__(self, id: _Optional[int] = ..., device_info: _Optional[str] = ..., created_at: _Optional[str] = ..., last_used_at: _Optional[str] = ..., expires_at: _Optional[str] = ..., is_current: bool = ...) -> None: ...

class ListSessionsRequest(_message.Message):
    __slots__ = ("account_id", "current_refresh_token")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    CURRENT_REFRESH_TOKEN_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    current_refresh_token: str
    def __init__(self, account_id: _Optional[int] = ..., current_refresh_token: _Optional[str] = ...) -> None: ...

class ListSessionsResponse(_message.Message):
    __slots__ = ("sessions",)
    SESSIONS_FIELD_NUMBER: _ClassVar[int]
    sessions: _containers.RepeatedCompositeFieldContainer[SessionInfo]
    def __init__(self, sessions: _Optional[_Iterable[_Union[SessionInfo, _Mapping]]] = ...) -> None: ...

class RevokeSessionRequest(_message.Message):
    __slots__ = ("account_id", "session_id")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    session_id: int
    def __init__(self, account_id: _Optional[int] = ..., session_id: _Optional[int] = ...) -> None: ...

class RevokeSessionResponse(_message.Message):
    __slots__ = ("success", "error_message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error_message: str
    def __init__(self, success: bool = ..., error_message: _Optional[str] = ...) -> None: ...

class RevokeAllSessionsRequest(_message.Message):
    __slots__ = ("account_id", "current_refresh_token", "include_current")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    CURRENT_REFRESH_TOKEN_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_CURRENT_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    current_refresh_token: str
    include_current: bool
    def __init__(self, account_id: _Optional[int] = ..., current_refresh_token: _Optional[str] = ..., include_current: bool = ...) -> None: ...

class RevokeAllSessionsResponse(_message.Message):
    __slots__ = ("revoked_count",)
    REVOKED_COUNT_FIELD_NUMBER: _ClassVar[int]
    revoked_count: int
    def __init__(self, revoked_count: _Optional[int] = ...) -> None: ...

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

class UpdateProjectRequest(_message.Message):
    __slots__ = ("project_id", "requester_account_id", "retention_days", "daily_quota")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    REQUESTER_ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    RETENTION_DAYS_FIELD_NUMBER: _ClassVar[int]
    DAILY_QUOTA_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    requester_account_id: int
    retention_days: int
    daily_quota: int
    def __init__(self, project_id: _Optional[int] = ..., requester_account_id: _Optional[int] = ..., retention_days: _Optional[int] = ..., daily_quota: _Optional[int] = ...) -> None: ...

class UpdateProjectResponse(_message.Message):
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
    __slots__ = ("key_id", "requester_account_id")
    KEY_ID_FIELD_NUMBER: _ClassVar[int]
    REQUESTER_ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    key_id: int
    requester_account_id: int
    def __init__(self, key_id: _Optional[int] = ..., requester_account_id: _Optional[int] = ...) -> None: ...

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
    __slots__ = ("id", "name", "index", "project_id", "period", "periodFrom", "periodTo", "type", "endpoint", "routes", "statistic", "layout", "trace_id", "service_filter", "operation_filter", "min_duration_ms", "has_error", "limit", "status_class", "logs_search")
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
    STATUS_CLASS_FIELD_NUMBER: _ClassVar[int]
    LOGS_SEARCH_FIELD_NUMBER: _ClassVar[int]
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
    status_class: str
    logs_search: str
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., index: _Optional[int] = ..., project_id: _Optional[str] = ..., period: _Optional[str] = ..., periodFrom: _Optional[str] = ..., periodTo: _Optional[str] = ..., type: _Optional[str] = ..., endpoint: _Optional[str] = ..., routes: _Optional[_Iterable[str]] = ..., statistic: _Optional[str] = ..., layout: _Optional[_Union[PanelLayout, _Mapping]] = ..., trace_id: _Optional[str] = ..., service_filter: _Optional[str] = ..., operation_filter: _Optional[str] = ..., min_duration_ms: _Optional[int] = ..., has_error: bool = ..., limit: _Optional[int] = ..., status_class: _Optional[str] = ..., logs_search: _Optional[str] = ...) -> None: ...

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
    __slots__ = ("user_id", "name", "index", "project_id", "period", "periodFrom", "periodTo", "type", "endpoint", "routes", "statistic", "layout", "trace_id", "service_filter", "operation_filter", "min_duration_ms", "has_error", "limit", "status_class", "logs_search")
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
    STATUS_CLASS_FIELD_NUMBER: _ClassVar[int]
    LOGS_SEARCH_FIELD_NUMBER: _ClassVar[int]
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
    status_class: str
    logs_search: str
    def __init__(self, user_id: _Optional[int] = ..., name: _Optional[str] = ..., index: _Optional[int] = ..., project_id: _Optional[str] = ..., period: _Optional[str] = ..., periodFrom: _Optional[str] = ..., periodTo: _Optional[str] = ..., type: _Optional[str] = ..., endpoint: _Optional[str] = ..., routes: _Optional[_Iterable[str]] = ..., statistic: _Optional[str] = ..., layout: _Optional[_Union[PanelLayout, _Mapping]] = ..., trace_id: _Optional[str] = ..., service_filter: _Optional[str] = ..., operation_filter: _Optional[str] = ..., min_duration_ms: _Optional[int] = ..., has_error: bool = ..., limit: _Optional[int] = ..., status_class: _Optional[str] = ..., logs_search: _Optional[str] = ...) -> None: ...

class CreateDashboardPanelResponse(_message.Message):
    __slots__ = ("panel",)
    PANEL_FIELD_NUMBER: _ClassVar[int]
    panel: Panel
    def __init__(self, panel: _Optional[_Union[Panel, _Mapping]] = ...) -> None: ...

class UpdateDashboardPanelRequest(_message.Message):
    __slots__ = ("user_id", "panel_id", "name", "index", "project_id", "period", "periodFrom", "periodTo", "type", "endpoint", "routes", "statistic", "layout", "trace_id", "service_filter", "operation_filter", "min_duration_ms", "has_error", "limit", "status_class", "logs_search")
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
    STATUS_CLASS_FIELD_NUMBER: _ClassVar[int]
    LOGS_SEARCH_FIELD_NUMBER: _ClassVar[int]
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
    status_class: str
    logs_search: str
    def __init__(self, user_id: _Optional[int] = ..., panel_id: _Optional[str] = ..., name: _Optional[str] = ..., index: _Optional[int] = ..., project_id: _Optional[str] = ..., period: _Optional[str] = ..., periodFrom: _Optional[str] = ..., periodTo: _Optional[str] = ..., type: _Optional[str] = ..., endpoint: _Optional[str] = ..., routes: _Optional[_Iterable[str]] = ..., statistic: _Optional[str] = ..., layout: _Optional[_Union[PanelLayout, _Mapping]] = ..., trace_id: _Optional[str] = ..., service_filter: _Optional[str] = ..., operation_filter: _Optional[str] = ..., min_duration_ms: _Optional[int] = ..., has_error: bool = ..., limit: _Optional[int] = ..., status_class: _Optional[str] = ..., logs_search: _Optional[str] = ...) -> None: ...

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

class DashboardTab(_message.Message):
    __slots__ = ("id", "name", "template_id", "panel_ids", "project_id")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    TEMPLATE_ID_FIELD_NUMBER: _ClassVar[int]
    PANEL_IDS_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    template_id: str
    panel_ids: _containers.RepeatedScalarFieldContainer[str]
    project_id: str
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., template_id: _Optional[str] = ..., panel_ids: _Optional[_Iterable[str]] = ..., project_id: _Optional[str] = ...) -> None: ...

class GetDashboardTabsRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    def __init__(self, user_id: _Optional[int] = ...) -> None: ...

class GetDashboardTabsResponse(_message.Message):
    __slots__ = ("tabs", "active_tab_id")
    TABS_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_TAB_ID_FIELD_NUMBER: _ClassVar[int]
    tabs: _containers.RepeatedCompositeFieldContainer[DashboardTab]
    active_tab_id: str
    def __init__(self, tabs: _Optional[_Iterable[_Union[DashboardTab, _Mapping]]] = ..., active_tab_id: _Optional[str] = ...) -> None: ...

class SaveDashboardTabsRequest(_message.Message):
    __slots__ = ("user_id", "tabs", "active_tab_id")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    TABS_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_TAB_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    tabs: _containers.RepeatedCompositeFieldContainer[DashboardTab]
    active_tab_id: str
    def __init__(self, user_id: _Optional[int] = ..., tabs: _Optional[_Iterable[_Union[DashboardTab, _Mapping]]] = ..., active_tab_id: _Optional[str] = ...) -> None: ...

class SaveDashboardTabsResponse(_message.Message):
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
    __slots__ = ("id", "project_id", "name", "enabled", "metric", "comparator", "threshold", "unit", "severity", "connector_ids", "last_fired_at", "created_at", "updated_at", "escalation_after_minutes", "escalate_connector_id")
    ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    METRIC_FIELD_NUMBER: _ClassVar[int]
    COMPARATOR_FIELD_NUMBER: _ClassVar[int]
    THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    UNIT_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    CONNECTOR_IDS_FIELD_NUMBER: _ClassVar[int]
    LAST_FIRED_AT_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    ESCALATION_AFTER_MINUTES_FIELD_NUMBER: _ClassVar[int]
    ESCALATE_CONNECTOR_ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    project_id: int
    name: str
    enabled: bool
    metric: str
    comparator: str
    threshold: float
    unit: str
    severity: int
    connector_ids: _containers.RepeatedScalarFieldContainer[int]
    last_fired_at: str
    created_at: str
    updated_at: str
    escalation_after_minutes: int
    escalate_connector_id: int
    def __init__(self, id: _Optional[int] = ..., project_id: _Optional[int] = ..., name: _Optional[str] = ..., enabled: bool = ..., metric: _Optional[str] = ..., comparator: _Optional[str] = ..., threshold: _Optional[float] = ..., unit: _Optional[str] = ..., severity: _Optional[int] = ..., connector_ids: _Optional[_Iterable[int]] = ..., last_fired_at: _Optional[str] = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ..., escalation_after_minutes: _Optional[int] = ..., escalate_connector_id: _Optional[int] = ...) -> None: ...

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
    __slots__ = ("project_id", "name", "metric", "comparator", "threshold", "unit", "severity", "connector_ids", "escalation_after_minutes", "escalate_connector_id")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    METRIC_FIELD_NUMBER: _ClassVar[int]
    COMPARATOR_FIELD_NUMBER: _ClassVar[int]
    THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    UNIT_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    CONNECTOR_IDS_FIELD_NUMBER: _ClassVar[int]
    ESCALATION_AFTER_MINUTES_FIELD_NUMBER: _ClassVar[int]
    ESCALATE_CONNECTOR_ID_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    name: str
    metric: str
    comparator: str
    threshold: float
    unit: str
    severity: int
    connector_ids: _containers.RepeatedScalarFieldContainer[int]
    escalation_after_minutes: int
    escalate_connector_id: int
    def __init__(self, project_id: _Optional[int] = ..., name: _Optional[str] = ..., metric: _Optional[str] = ..., comparator: _Optional[str] = ..., threshold: _Optional[float] = ..., unit: _Optional[str] = ..., severity: _Optional[int] = ..., connector_ids: _Optional[_Iterable[int]] = ..., escalation_after_minutes: _Optional[int] = ..., escalate_connector_id: _Optional[int] = ...) -> None: ...

class CreateAlertRuleResponse(_message.Message):
    __slots__ = ("rule",)
    RULE_FIELD_NUMBER: _ClassVar[int]
    rule: AlertRule
    def __init__(self, rule: _Optional[_Union[AlertRule, _Mapping]] = ...) -> None: ...

class UpdateAlertRuleRequest(_message.Message):
    __slots__ = ("rule_id", "project_id", "name", "enabled", "threshold", "unit", "severity", "comparator", "metric", "connector_ids", "update_connectors", "escalation_after_minutes", "escalate_connector_id", "clear_escalate_connector_id")
    RULE_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    UNIT_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    COMPARATOR_FIELD_NUMBER: _ClassVar[int]
    METRIC_FIELD_NUMBER: _ClassVar[int]
    CONNECTOR_IDS_FIELD_NUMBER: _ClassVar[int]
    UPDATE_CONNECTORS_FIELD_NUMBER: _ClassVar[int]
    ESCALATION_AFTER_MINUTES_FIELD_NUMBER: _ClassVar[int]
    ESCALATE_CONNECTOR_ID_FIELD_NUMBER: _ClassVar[int]
    CLEAR_ESCALATE_CONNECTOR_ID_FIELD_NUMBER: _ClassVar[int]
    rule_id: int
    project_id: int
    name: str
    enabled: bool
    threshold: float
    unit: str
    severity: int
    comparator: str
    metric: str
    connector_ids: _containers.RepeatedScalarFieldContainer[int]
    update_connectors: bool
    escalation_after_minutes: int
    escalate_connector_id: int
    clear_escalate_connector_id: bool
    def __init__(self, rule_id: _Optional[int] = ..., project_id: _Optional[int] = ..., name: _Optional[str] = ..., enabled: bool = ..., threshold: _Optional[float] = ..., unit: _Optional[str] = ..., severity: _Optional[int] = ..., comparator: _Optional[str] = ..., metric: _Optional[str] = ..., connector_ids: _Optional[_Iterable[int]] = ..., update_connectors: bool = ..., escalation_after_minutes: _Optional[int] = ..., escalate_connector_id: _Optional[int] = ..., clear_escalate_connector_id: bool = ...) -> None: ...

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

class Connector(_message.Message):
    __slots__ = ("id", "account_id", "kind", "name", "config", "enabled", "created_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: int
    account_id: int
    kind: str
    name: str
    config: str
    enabled: bool
    created_at: str
    def __init__(self, id: _Optional[int] = ..., account_id: _Optional[int] = ..., kind: _Optional[str] = ..., name: _Optional[str] = ..., config: _Optional[str] = ..., enabled: bool = ..., created_at: _Optional[str] = ...) -> None: ...

class ListConnectorsRequest(_message.Message):
    __slots__ = ("account_id",)
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    def __init__(self, account_id: _Optional[int] = ...) -> None: ...

class ListConnectorsResponse(_message.Message):
    __slots__ = ("connectors",)
    CONNECTORS_FIELD_NUMBER: _ClassVar[int]
    connectors: _containers.RepeatedCompositeFieldContainer[Connector]
    def __init__(self, connectors: _Optional[_Iterable[_Union[Connector, _Mapping]]] = ...) -> None: ...

class GetConnectorRequest(_message.Message):
    __slots__ = ("connector_id", "account_id")
    CONNECTOR_ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    connector_id: int
    account_id: int
    def __init__(self, connector_id: _Optional[int] = ..., account_id: _Optional[int] = ...) -> None: ...

class GetConnectorResponse(_message.Message):
    __slots__ = ("connector", "found")
    CONNECTOR_FIELD_NUMBER: _ClassVar[int]
    FOUND_FIELD_NUMBER: _ClassVar[int]
    connector: Connector
    found: bool
    def __init__(self, connector: _Optional[_Union[Connector, _Mapping]] = ..., found: bool = ...) -> None: ...

class CreateConnectorRequest(_message.Message):
    __slots__ = ("account_id", "kind", "name", "config")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    kind: str
    name: str
    config: str
    def __init__(self, account_id: _Optional[int] = ..., kind: _Optional[str] = ..., name: _Optional[str] = ..., config: _Optional[str] = ...) -> None: ...

class CreateConnectorResponse(_message.Message):
    __slots__ = ("connector",)
    CONNECTOR_FIELD_NUMBER: _ClassVar[int]
    connector: Connector
    def __init__(self, connector: _Optional[_Union[Connector, _Mapping]] = ...) -> None: ...

class UpdateConnectorRequest(_message.Message):
    __slots__ = ("connector_id", "account_id", "name", "enabled", "config")
    CONNECTOR_ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    connector_id: int
    account_id: int
    name: str
    enabled: bool
    config: str
    def __init__(self, connector_id: _Optional[int] = ..., account_id: _Optional[int] = ..., name: _Optional[str] = ..., enabled: bool = ..., config: _Optional[str] = ...) -> None: ...

class UpdateConnectorResponse(_message.Message):
    __slots__ = ("connector",)
    CONNECTOR_FIELD_NUMBER: _ClassVar[int]
    connector: Connector
    def __init__(self, connector: _Optional[_Union[Connector, _Mapping]] = ...) -> None: ...

class DeleteConnectorRequest(_message.Message):
    __slots__ = ("connector_id", "account_id")
    CONNECTOR_ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    connector_id: int
    account_id: int
    def __init__(self, connector_id: _Optional[int] = ..., account_id: _Optional[int] = ...) -> None: ...

class DeleteConnectorResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...

class AlertEvent(_message.Message):
    __slots__ = ("id", "rule_id", "project_id", "rule_name", "metric", "comparator", "threshold", "unit", "value", "severity", "connectors_sent", "fired_at", "acked_by", "acked_at", "snoozed_until")
    ID_FIELD_NUMBER: _ClassVar[int]
    RULE_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    RULE_NAME_FIELD_NUMBER: _ClassVar[int]
    METRIC_FIELD_NUMBER: _ClassVar[int]
    COMPARATOR_FIELD_NUMBER: _ClassVar[int]
    THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    UNIT_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    CONNECTORS_SENT_FIELD_NUMBER: _ClassVar[int]
    FIRED_AT_FIELD_NUMBER: _ClassVar[int]
    ACKED_BY_FIELD_NUMBER: _ClassVar[int]
    ACKED_AT_FIELD_NUMBER: _ClassVar[int]
    SNOOZED_UNTIL_FIELD_NUMBER: _ClassVar[int]
    id: int
    rule_id: int
    project_id: int
    rule_name: str
    metric: str
    comparator: str
    threshold: float
    unit: str
    value: float
    severity: int
    connectors_sent: str
    fired_at: str
    acked_by: int
    acked_at: str
    snoozed_until: str
    def __init__(self, id: _Optional[int] = ..., rule_id: _Optional[int] = ..., project_id: _Optional[int] = ..., rule_name: _Optional[str] = ..., metric: _Optional[str] = ..., comparator: _Optional[str] = ..., threshold: _Optional[float] = ..., unit: _Optional[str] = ..., value: _Optional[float] = ..., severity: _Optional[int] = ..., connectors_sent: _Optional[str] = ..., fired_at: _Optional[str] = ..., acked_by: _Optional[int] = ..., acked_at: _Optional[str] = ..., snoozed_until: _Optional[str] = ...) -> None: ...

class ListAlertEventsRequest(_message.Message):
    __slots__ = ("project_id", "limit", "before_id")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    BEFORE_ID_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    limit: int
    before_id: int
    def __init__(self, project_id: _Optional[int] = ..., limit: _Optional[int] = ..., before_id: _Optional[int] = ...) -> None: ...

class ListAlertEventsResponse(_message.Message):
    __slots__ = ("events", "has_more")
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    HAS_MORE_FIELD_NUMBER: _ClassVar[int]
    events: _containers.RepeatedCompositeFieldContainer[AlertEvent]
    has_more: bool
    def __init__(self, events: _Optional[_Iterable[_Union[AlertEvent, _Mapping]]] = ..., has_more: bool = ...) -> None: ...

class AckAlertEventRequest(_message.Message):
    __slots__ = ("event_id", "project_id", "account_id")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    event_id: int
    project_id: int
    account_id: int
    def __init__(self, event_id: _Optional[int] = ..., project_id: _Optional[int] = ..., account_id: _Optional[int] = ...) -> None: ...

class AckAlertEventResponse(_message.Message):
    __slots__ = ("success", "error_message", "event")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    EVENT_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error_message: str
    event: AlertEvent
    def __init__(self, success: bool = ..., error_message: _Optional[str] = ..., event: _Optional[_Union[AlertEvent, _Mapping]] = ...) -> None: ...

class SnoozeAlertEventRequest(_message.Message):
    __slots__ = ("event_id", "project_id", "minutes")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    MINUTES_FIELD_NUMBER: _ClassVar[int]
    event_id: int
    project_id: int
    minutes: int
    def __init__(self, event_id: _Optional[int] = ..., project_id: _Optional[int] = ..., minutes: _Optional[int] = ...) -> None: ...

class SnoozeAlertEventResponse(_message.Message):
    __slots__ = ("success", "error_message", "event")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    EVENT_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error_message: str
    event: AlertEvent
    def __init__(self, success: bool = ..., error_message: _Optional[str] = ..., event: _Optional[_Union[AlertEvent, _Mapping]] = ...) -> None: ...

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

class Monitor(_message.Message):
    __slots__ = ("id", "project_id", "kind", "name", "target_url", "token", "interval_s", "timeout_s", "expected_status", "grace_s", "enabled", "state", "created_at", "updated_at", "last_checked_at", "last_ok", "last_latency_ms", "uptime_pct_24h")
    ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    TARGET_URL_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_S_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_S_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_STATUS_FIELD_NUMBER: _ClassVar[int]
    GRACE_S_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_CHECKED_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_OK_FIELD_NUMBER: _ClassVar[int]
    LAST_LATENCY_MS_FIELD_NUMBER: _ClassVar[int]
    UPTIME_PCT_24H_FIELD_NUMBER: _ClassVar[int]
    id: int
    project_id: int
    kind: str
    name: str
    target_url: str
    token: str
    interval_s: int
    timeout_s: int
    expected_status: int
    grace_s: int
    enabled: bool
    state: str
    created_at: str
    updated_at: str
    last_checked_at: str
    last_ok: bool
    last_latency_ms: int
    uptime_pct_24h: float
    def __init__(self, id: _Optional[int] = ..., project_id: _Optional[int] = ..., kind: _Optional[str] = ..., name: _Optional[str] = ..., target_url: _Optional[str] = ..., token: _Optional[str] = ..., interval_s: _Optional[int] = ..., timeout_s: _Optional[int] = ..., expected_status: _Optional[int] = ..., grace_s: _Optional[int] = ..., enabled: bool = ..., state: _Optional[str] = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ..., last_checked_at: _Optional[str] = ..., last_ok: bool = ..., last_latency_ms: _Optional[int] = ..., uptime_pct_24h: _Optional[float] = ...) -> None: ...

class CreateMonitorRequest(_message.Message):
    __slots__ = ("project_id", "kind", "name", "target_url", "interval_s", "timeout_s", "expected_status", "grace_s")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    TARGET_URL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_S_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_S_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_STATUS_FIELD_NUMBER: _ClassVar[int]
    GRACE_S_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    kind: str
    name: str
    target_url: str
    interval_s: int
    timeout_s: int
    expected_status: int
    grace_s: int
    def __init__(self, project_id: _Optional[int] = ..., kind: _Optional[str] = ..., name: _Optional[str] = ..., target_url: _Optional[str] = ..., interval_s: _Optional[int] = ..., timeout_s: _Optional[int] = ..., expected_status: _Optional[int] = ..., grace_s: _Optional[int] = ...) -> None: ...

class CreateMonitorResponse(_message.Message):
    __slots__ = ("monitor",)
    MONITOR_FIELD_NUMBER: _ClassVar[int]
    monitor: Monitor
    def __init__(self, monitor: _Optional[_Union[Monitor, _Mapping]] = ...) -> None: ...

class ListMonitorsRequest(_message.Message):
    __slots__ = ("project_id",)
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    def __init__(self, project_id: _Optional[int] = ...) -> None: ...

class ListMonitorsResponse(_message.Message):
    __slots__ = ("monitors",)
    MONITORS_FIELD_NUMBER: _ClassVar[int]
    monitors: _containers.RepeatedCompositeFieldContainer[Monitor]
    def __init__(self, monitors: _Optional[_Iterable[_Union[Monitor, _Mapping]]] = ...) -> None: ...

class UpdateMonitorRequest(_message.Message):
    __slots__ = ("monitor_id", "project_id", "name", "target_url", "interval_s", "timeout_s", "expected_status", "grace_s", "enabled")
    MONITOR_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    TARGET_URL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_S_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_S_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_STATUS_FIELD_NUMBER: _ClassVar[int]
    GRACE_S_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    monitor_id: int
    project_id: int
    name: str
    target_url: str
    interval_s: int
    timeout_s: int
    expected_status: int
    grace_s: int
    enabled: bool
    def __init__(self, monitor_id: _Optional[int] = ..., project_id: _Optional[int] = ..., name: _Optional[str] = ..., target_url: _Optional[str] = ..., interval_s: _Optional[int] = ..., timeout_s: _Optional[int] = ..., expected_status: _Optional[int] = ..., grace_s: _Optional[int] = ..., enabled: bool = ...) -> None: ...

class UpdateMonitorResponse(_message.Message):
    __slots__ = ("monitor",)
    MONITOR_FIELD_NUMBER: _ClassVar[int]
    monitor: Monitor
    def __init__(self, monitor: _Optional[_Union[Monitor, _Mapping]] = ...) -> None: ...

class DeleteMonitorRequest(_message.Message):
    __slots__ = ("monitor_id", "project_id")
    MONITOR_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    monitor_id: int
    project_id: int
    def __init__(self, monitor_id: _Optional[int] = ..., project_id: _Optional[int] = ...) -> None: ...

class DeleteMonitorResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...

class GetMonitorByTokenRequest(_message.Message):
    __slots__ = ("token",)
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    token: str
    def __init__(self, token: _Optional[str] = ...) -> None: ...

class GetMonitorByTokenResponse(_message.Message):
    __slots__ = ("found", "monitor")
    FOUND_FIELD_NUMBER: _ClassVar[int]
    MONITOR_FIELD_NUMBER: _ClassVar[int]
    found: bool
    monitor: Monitor
    def __init__(self, found: bool = ..., monitor: _Optional[_Union[Monitor, _Mapping]] = ...) -> None: ...

class RecordHeartbeatPingRequest(_message.Message):
    __slots__ = ("token",)
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    token: str
    def __init__(self, token: _Optional[str] = ...) -> None: ...

class RecordHeartbeatPingResponse(_message.Message):
    __slots__ = ("success", "error_message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error_message: str
    def __init__(self, success: bool = ..., error_message: _Optional[str] = ...) -> None: ...

class MaintenanceWindow(_message.Message):
    __slots__ = ("id", "project_id", "name", "starts_at", "ends_at", "recurrence", "created_at", "updated_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    STARTS_AT_FIELD_NUMBER: _ClassVar[int]
    ENDS_AT_FIELD_NUMBER: _ClassVar[int]
    RECURRENCE_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: int
    project_id: int
    name: str
    starts_at: str
    ends_at: str
    recurrence: str
    created_at: str
    updated_at: str
    def __init__(self, id: _Optional[int] = ..., project_id: _Optional[int] = ..., name: _Optional[str] = ..., starts_at: _Optional[str] = ..., ends_at: _Optional[str] = ..., recurrence: _Optional[str] = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ...) -> None: ...

class ListMaintenanceWindowsRequest(_message.Message):
    __slots__ = ("project_id",)
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    def __init__(self, project_id: _Optional[int] = ...) -> None: ...

class ListMaintenanceWindowsResponse(_message.Message):
    __slots__ = ("windows",)
    WINDOWS_FIELD_NUMBER: _ClassVar[int]
    windows: _containers.RepeatedCompositeFieldContainer[MaintenanceWindow]
    def __init__(self, windows: _Optional[_Iterable[_Union[MaintenanceWindow, _Mapping]]] = ...) -> None: ...

class CreateMaintenanceWindowRequest(_message.Message):
    __slots__ = ("project_id", "name", "starts_at", "ends_at", "recurrence")
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    STARTS_AT_FIELD_NUMBER: _ClassVar[int]
    ENDS_AT_FIELD_NUMBER: _ClassVar[int]
    RECURRENCE_FIELD_NUMBER: _ClassVar[int]
    project_id: int
    name: str
    starts_at: str
    ends_at: str
    recurrence: str
    def __init__(self, project_id: _Optional[int] = ..., name: _Optional[str] = ..., starts_at: _Optional[str] = ..., ends_at: _Optional[str] = ..., recurrence: _Optional[str] = ...) -> None: ...

class CreateMaintenanceWindowResponse(_message.Message):
    __slots__ = ("window",)
    WINDOW_FIELD_NUMBER: _ClassVar[int]
    window: MaintenanceWindow
    def __init__(self, window: _Optional[_Union[MaintenanceWindow, _Mapping]] = ...) -> None: ...

class DeleteMaintenanceWindowRequest(_message.Message):
    __slots__ = ("window_id", "project_id")
    WINDOW_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    window_id: int
    project_id: int
    def __init__(self, window_id: _Optional[int] = ..., project_id: _Optional[int] = ...) -> None: ...

class DeleteMaintenanceWindowResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...
