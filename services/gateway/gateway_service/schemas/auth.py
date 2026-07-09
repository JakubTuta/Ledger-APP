import pydantic


class RegisterRequest(pydantic.BaseModel):
    """Request body for account registration."""

    email: str = pydantic.Field(
        ...,
        max_length=255,
        description="Valid email address for account creation",
        examples=["user@example.com"],
    )
    password: str = pydantic.Field(
        ...,
        min_length=8,
        max_length=64,
        description="Secure password (min 8 chars, must include uppercase, lowercase, and digit)",
        examples=["SecurePass123"],
    )
    name: str = pydantic.Field(
        ...,
        min_length=1,
        max_length=255,
        description="User's full name",
        examples=["John Doe"],
    )

    @pydantic.field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        import re

        pattern = r"^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]@[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]\.[a-zA-Z]{2,}$"

        if ".." in v:
            raise ValueError("Invalid email format: consecutive dots not allowed")
        if not re.match(pattern, v):
            raise ValueError("Invalid email format")

        return v.lower()

    @pydantic.field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")

        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain uppercase letter")

        if not any(c.islower() for c in v):
            raise ValueError("Password must contain lowercase letter")

        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain digit")

        return v

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "user@example.com",
                    "password": "SecurePass123",
                    "name": "John Doe",
                }
            ]
        }
    )


class RegisterResponse(pydantic.BaseModel):
    """Response from successful registration."""

    access_token: str = pydantic.Field(..., description="JWT access token for immediate use")
    refresh_token: str = pydantic.Field(
        ..., description="Refresh token for obtaining new access tokens"
    )
    token_type: str = pydantic.Field(default="bearer", description="Token type (always 'bearer')")
    account_id: int = pydantic.Field(..., description="Unique account identifier")
    email: str = pydantic.Field(..., description="Registered email address")
    name: str = pydantic.Field(..., description="User's full name")
    expires_in: int = pydantic.Field(
        default=900, description="Access token expiration time in seconds (15 minutes)"
    )
    message: str = pydantic.Field(
        default="Account created successfully", description="Success message"
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "refresh_token": "AbCdEf123456...",
                    "token_type": "bearer",
                    "account_id": 123,
                    "email": "user@example.com",
                    "name": "John Doe",
                    "expires_in": 900,
                    "message": "Account created successfully",
                }
            ]
        }
    )


class LoginRequest(pydantic.BaseModel):
    """Request body for account login."""

    email: str = pydantic.Field(
        ...,
        max_length=255,
        description="Registered email address",
        examples=["user@example.com"],
    )
    password: str = pydantic.Field(
        ...,
        min_length=8,
        max_length=64,
        description="Account password",
        examples=["SecurePass123"],
    )

    @pydantic.field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return v.lower()

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "user@example.com",
                    "password": "SecurePass123",
                }
            ]
        }
    )


class LoginResponse(pydantic.BaseModel):
    """
    Response from a login attempt.

    Two shapes:
    - Normal login (no 2FA / 2FA already satisfied): access_token,
      refresh_token, account_id, email are populated, requires_2fa is False.
    - 2FA required: requires_2fa is True and totp_session_token is set;
      access_token/refresh_token/account_id/email are omitted. The client
      must call POST /accounts/2fa/login with the totp_session_token and a
      TOTP/backup code to obtain real tokens.
    """

    access_token: str | None = pydantic.Field(
        default=None, description="JWT access token (omitted when requires_2fa is true)"
    )
    refresh_token: str | None = pydantic.Field(
        default=None,
        description="Refresh token for obtaining new access tokens (omitted when requires_2fa is true)",
    )
    token_type: str = pydantic.Field(default="bearer", description="Token type (always 'bearer')")
    account_id: int | None = pydantic.Field(default=None, description="Account identifier")
    email: str | None = pydantic.Field(default=None, description="Logged in email address")
    expires_in: int | None = pydantic.Field(
        default=None, description="Access token expiration time in seconds"
    )
    requires_2fa: bool = pydantic.Field(
        default=False,
        description="True when a TOTP/backup code is still required to complete login",
    )
    totp_session_token: str | None = pydantic.Field(
        default=None,
        description="Short-lived opaque token (~5 min TTL) to present to /accounts/2fa/login, only set when requires_2fa is true",
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "refresh_token": "AbCdEf123456...",
                    "token_type": "bearer",
                    "account_id": 123,
                    "email": "user@example.com",
                    "expires_in": 900,
                    "requires_2fa": False,
                }
            ]
        }
    )


class TOTPLoginRequest(pydantic.BaseModel):
    """Request body for completing a login pending 2FA."""

    totp_session_token: str = pydantic.Field(
        ..., description="Opaque session token returned by /accounts/login"
    )
    code: str = pydantic.Field(
        ...,
        min_length=6,
        max_length=17,
        description="6-digit TOTP code, or an XXXX-XXXX backup code",
    )


class AccountInfoResponse(pydantic.BaseModel):
    """Response with account information."""

    account_id: int = pydantic.Field(..., description="Account identifier")
    email: str = pydantic.Field(..., description="Email address")
    name: str = pydantic.Field(..., description="User's full name")
    created_at: str = pydantic.Field(..., description="Account creation timestamp (ISO 8601)")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "account_id": 123,
                    "email": "user@example.com",
                    "name": "John Doe",
                    "created_at": "2024-01-15T10:30:00Z",
                }
            ]
        }
    )


class UpdateAccountNameRequest(pydantic.BaseModel):
    """Request body for updating account name."""

    name: str = pydantic.Field(
        ...,
        min_length=1,
        max_length=255,
        description="New account name",
        examples=["Jane Smith"],
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Jane Smith",
                }
            ]
        }
    )


class UpdateAccountNameResponse(pydantic.BaseModel):
    """Response from successful name update."""

    name: str = pydantic.Field(..., description="Updated account name")
    message: str = pydantic.Field(
        default="Account name updated successfully", description="Success message"
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Jane Smith",
                    "message": "Account name updated successfully",
                }
            ]
        }
    )


class ChangePasswordRequest(pydantic.BaseModel):
    """Request body for changing account password."""

    old_password: str = pydantic.Field(
        ...,
        min_length=8,
        max_length=64,
        description="Current password for verification",
        examples=["OldPassword123"],
    )
    new_password: str = pydantic.Field(
        ...,
        min_length=8,
        max_length=64,
        description="New secure password (min 8 chars, must include uppercase, lowercase, and digit)",
        examples=["NewSecurePass456"],
    )

    @pydantic.field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")

        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain uppercase letter")

        if not any(c.islower() for c in v):
            raise ValueError("Password must contain lowercase letter")

        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain digit")

        return v

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "old_password": "OldPassword123",
                    "new_password": "NewSecurePass456",
                }
            ]
        }
    )


class ChangePasswordResponse(pydantic.BaseModel):
    """Response from successful password change."""

    message: str = pydantic.Field(
        default="Password changed successfully", description="Success message"
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "message": "Password changed successfully",
                }
            ]
        }
    )


class RefreshTokenRequest(pydantic.BaseModel):
    """
    Request body for refreshing access token.

    refresh_token is optional: when omitted (or the body itself is omitted),
    the gateway falls back to the httpOnly `refresh_token` cookie set by
    /accounts/login, /accounts/register, and /accounts/refresh.
    """

    refresh_token: str | None = pydantic.Field(
        default=None,
        description="Refresh token from login. Optional — falls back to the httpOnly cookie.",
        examples=["AbCdEf123456..."],
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "refresh_token": "AbCdEf123456...",
                }
            ]
        }
    )


class RefreshTokenResponse(pydantic.BaseModel):
    """Response from successful token refresh."""

    access_token: str = pydantic.Field(..., description="New JWT access token")
    refresh_token: str = pydantic.Field(..., description="New refresh token (token rotation)")
    token_type: str = pydantic.Field(default="bearer", description="Token type (always 'bearer')")
    account_id: int = pydantic.Field(..., description="Account identifier")
    email: str = pydantic.Field(..., description="Email address")
    expires_in: int = pydantic.Field(
        default=900, description="Access token expiration time in seconds (15 minutes)"
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "refresh_token": "XyZ789...",
                    "token_type": "bearer",
                    "account_id": 123,
                    "email": "user@example.com",
                    "expires_in": 900,
                }
            ]
        }
    )


class VerifyEmailRequest(pydantic.BaseModel):
    """Request body for verifying an account's email address."""

    token: str = pydantic.Field(..., min_length=1, description="Email verification token")


class VerifyEmailResponse(pydantic.BaseModel):
    """Response from a successful (or already-verified) email verification."""

    success: bool = pydantic.Field(default=True)
    message: str = pydantic.Field(default="Email verified successfully")


class ResendVerificationResponse(pydantic.BaseModel):
    """Response from a resend-verification request."""

    success: bool = pydantic.Field(default=True)
    already_verified: bool = pydantic.Field(default=False)
    message: str = pydantic.Field(default="Verification email sent")


class Setup2FAResponse(pydantic.BaseModel):
    """Response from initiating TOTP 2FA setup. 2FA is NOT yet enabled."""

    secret: str = pydantic.Field(..., description="Base32 TOTP secret")
    provisioning_uri: str = pydantic.Field(
        ..., description="otpauth:// URI — render as a QR code in an authenticator app"
    )


class Verify2FARequest(pydantic.BaseModel):
    """Request body for confirming TOTP 2FA setup."""

    code: str = pydantic.Field(..., min_length=6, max_length=6, description="6-digit TOTP code")


class Verify2FAResponse(pydantic.BaseModel):
    """Response from successfully enabling 2FA. Backup codes are shown ONCE."""

    success: bool = pydantic.Field(default=True)
    backup_codes: list[str] = pydantic.Field(
        default_factory=list,
        description="One-time backup codes, shown only in this response — save them now",
    )
    message: str = pydantic.Field(
        default="Two-factor authentication enabled. Save your backup codes now — they will not be shown again."
    )


class Disable2FARequest(pydantic.BaseModel):
    """Request body for disabling 2FA. Requires current password re-entry."""

    password: str = pydantic.Field(..., min_length=1, description="Current account password")


class Disable2FAResponse(pydantic.BaseModel):
    """Response from disabling 2FA."""

    success: bool = pydantic.Field(default=True)
    message: str = pydantic.Field(default="Two-factor authentication disabled")


class SessionInfo(pydantic.BaseModel):
    """A single active refresh-token session."""

    id: int
    device_info: str | None = None
    created_at: str
    last_used_at: str | None = None
    expires_at: str
    is_current: bool = False


class ListSessionsResponse(pydantic.BaseModel):
    """Response listing the caller's active sessions."""

    sessions: list[SessionInfo] = pydantic.Field(default_factory=list)
    total: int = 0


class RevokeSessionResponse(pydantic.BaseModel):
    """Response from revoking a single session."""

    success: bool = pydantic.Field(default=True)
    message: str = pydantic.Field(default="Session revoked")


class RevokeAllSessionsResponse(pydantic.BaseModel):
    """Response from revoking all (or all-but-current) sessions."""

    revoked_count: int = 0
    message: str = pydantic.Field(default="Sessions revoked")
