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

    access_token: str = pydantic.Field(
        ..., description="JWT access token for immediate use"
    )
    refresh_token: str = pydantic.Field(
        ..., description="Refresh token for obtaining new access tokens"
    )
    token_type: str = pydantic.Field(
        default="bearer", description="Token type (always 'bearer')"
    )
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
    """Response from successful login."""

    access_token: str = pydantic.Field(..., description="JWT access token")
    refresh_token: str = pydantic.Field(
        ..., description="Refresh token for obtaining new access tokens"
    )
    token_type: str = pydantic.Field(
        default="bearer", description="Token type (always 'bearer')"
    )
    account_id: int = pydantic.Field(..., description="Account identifier")
    email: str = pydantic.Field(..., description="Logged in email address")
    expires_in: int = pydantic.Field(
        default=900, description="Access token expiration time in seconds (15 minutes)"
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
                }
            ]
        }
    )


class AccountInfoResponse(pydantic.BaseModel):
    """Response with account information."""

    account_id: int = pydantic.Field(..., description="Account identifier")
    email: str = pydantic.Field(..., description="Email address")
    name: str = pydantic.Field(..., description="User's full name")
    created_at: str = pydantic.Field(
        ..., description="Account creation timestamp (ISO 8601)"
    )

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
    """Request body for refreshing access token."""

    refresh_token: str = pydantic.Field(
        ...,
        description="Valid refresh token from login",
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
    refresh_token: str = pydantic.Field(
        ..., description="New refresh token (token rotation)"
    )
    token_type: str = pydantic.Field(
        default="bearer", description="Token type (always 'bearer')"
    )
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
