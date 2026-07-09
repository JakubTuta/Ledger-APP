import email.message
import logging
import secrets
import typing

import aiosmtplib
import fastapi
import gateway_service.schemas as schemas
import grpc
from gateway_service import config, dependencies
from gateway_service.proto import auth_pb2, auth_pb2_grpc
from gateway_service.services import grpc_pool, redis_client

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(tags=["Authentication"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/accounts"


# The refresh token is set as an httpOnly cookie so client-side JS (and by
# extension XSS) can never read it — only the browser can send it back,
# scoped to /api/v1/accounts. It is ALSO still returned in the response body
# for now so existing consumers (older SDK/frontend builds, tests) keep
# working during rollout; the frontend is being updated in this same phase
# to stop reading refresh_token from the body and rely on the cookie alone.


def _set_refresh_cookie(response: fastapi.Response, refresh_token: str) -> None:
    settings = config.get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        # Secure cookies require HTTPS; relax only in local dev so cookie
        # auth still works over plain http://localhost.
        secure=not settings.is_development,
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: fastapi.Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


def _get_refresh_token_from_request(
    request: fastapi.Request, body_token: typing.Optional[str]
) -> typing.Optional[str]:
    """Prefer an explicit body token (back-compat); fall back to the httpOnly cookie."""
    if body_token:
        return body_token
    return request.cookies.get(REFRESH_COOKIE_NAME)


# The auth service itself never sends email — it only generates/stores
# verification tokens. The gateway owns the small amount of SMTP boilerplate
# needed to actually deliver it, matching the EMAIL_ENABLED graceful
# degradation pattern already used for alert emails in analytics_workers.


async def _send_verification_email(to_email: str, token: str) -> None:
    settings = config.settings

    if not settings.EMAIL_ENABLED:
        logger.info(
            "Email disabled (EMAIL_ENABLED=false); skipped verification email to %s",
            to_email,
        )
        return

    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured; cannot send verification email")
        return

    verify_url = f"{settings.FRONTEND_URL.rstrip('/')}/verify-email?token={token}"

    message = email.message.EmailMessage()
    message["From"] = settings.SMTP_FROM or settings.SMTP_USER
    message["To"] = to_email
    message["Subject"] = "Verify your Ledger email address"
    message.set_content(
        "Welcome to Ledger!\n\n"
        f"Please verify your email address by visiting:\n{verify_url}\n\n"
        "This link expires in 24 hours.\n\n"
        "—\nIf you didn't create this account, you can safely ignore this email.\n"
    )

    tls_kwargs: dict = {}
    if settings.SMTP_PORT == 465:
        tls_kwargs["use_tls"] = True
    else:
        tls_kwargs["start_tls"] = settings.SMTP_USE_TLS

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            timeout=15,
            **tls_kwargs,
        )
        logger.info(f"Sent verification email to {to_email}")
    except Exception as e:
        # Never fail the calling request (registration / resend) just
        # because outbound mail is flaky or misconfigured.
        logger.warning(f"Verification email delivery failed to {to_email}: {e}")


# Note: Request/Response models moved to gateway_service/schemas/auth.py


@router.post(
    "/accounts/register",
    response_model=schemas.RegisterResponse,
    status_code=fastapi.status.HTTP_201_CREATED,
    summary="Register new account",
    description="Create a new account with email, password, and name. Password must be at least 8 characters with uppercase, lowercase, and digit.",
    response_description="Created account details",
    responses={
        201: {
            "description": "Account created successfully with access token",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                        "account_id": 123,
                        "email": "user@example.com",
                        "name": "John Doe",
                        "expires_in": 3600,
                        "message": "Account created successfully",
                    }
                }
            },
        },
        400: {
            "description": "Invalid input (email format, password requirements)",
            "content": {
                "application/json": {
                    "example": {"detail": "Password must contain uppercase letter"}
                }
            },
        },
        409: {
            "description": "Email already registered",
            "content": {"application/json": {"example": {"detail": "Email already registered"}}},
        },
        503: {
            "description": "Service temporarily unavailable",
            "content": {
                "application/json": {
                    "example": {"detail": "Registration service timeout, please try again"}
                }
            },
        },
    },
)
async def register_account(
    request: schemas.RegisterRequest,
    response: fastapi.Response,
    background_tasks: fastapi.BackgroundTasks,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
    redis: redis_client.RedisClient = fastapi.Depends(dependencies.get_redis_client),
):
    """
    Register a new account with email, password, and name.

    The password must meet the following requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit

    Returns the created account details including an access token for immediate use.
    This eliminates the need for a separate login call after registration.
    """

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        register_request = auth_pb2.RegisterRequest(email=request.email, password=request.password)

        register_response = await stub.Register(
            register_request, timeout=config.settings.GRPC_TIMEOUT
        )

        login_request = auth_pb2.LoginRequest(email=request.email, password=request.password)

        login_response = await stub.Login(login_request, timeout=config.settings.GRPC_TIMEOUT)

        _set_refresh_cookie(response, login_response.refresh_token)

        if register_response.email_verification_token:
            background_tasks.add_task(
                _send_verification_email,
                register_response.email,
                register_response.email_verification_token,
            )

        return schemas.RegisterResponse(
            access_token=login_response.access_token,
            refresh_token=login_response.refresh_token,
            account_id=register_response.account_id,
            email=register_response.email,
            name=register_response.name,
            expires_in=login_response.expires_in,
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error during registration: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Registration service timeout, please try again",
            )

        elif e.code() == grpc.StatusCode.ALREADY_EXISTS:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        elif e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail=e.details()
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed",
        )


@router.post(
    "/accounts/login",
    response_model=schemas.LoginResponse,
    summary="Login to account",
    description="Authenticate with email and password to receive a JWT token for accessing protected endpoints",
    response_description="JWT token and account information",
    responses={
        200: {
            "description": "Login successful",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                        "account_id": 123,
                        "email": "user@example.com",
                        "expires_in": 3600,
                    }
                }
            },
        },
        401: {
            "description": "Invalid email or password",
            "content": {"application/json": {"example": {"detail": "Invalid email or password"}}},
        },
        503: {
            "description": "Service temporarily unavailable",
            "content": {
                "application/json": {
                    "example": {"detail": "Login service timeout, please try again"}
                }
            },
        },
    },
)
async def login_account(
    request: schemas.LoginRequest,
    response: fastapi.Response,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
    redis: redis_client.RedisClient = fastapi.Depends(dependencies.get_redis_client),
):
    """
    Authenticate with email and password to receive a JWT access token.

    The JWT token is valid for 3600 seconds (1 hour) and should be included
    in the Authorization header for subsequent requests:
    `Authorization: Bearer <token>`

    The token is also cached in Redis for fast validation.
    """

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.LoginRequest(email=request.email, password=request.password)

        grpc_response = await stub.Login(grpc_request, timeout=config.settings.GRPC_TIMEOUT)

        if grpc_response.requires_2fa:
            # Password was correct, but the account has TOTP 2FA enabled.
            # Track the pending login server-side (gateway's Redis) so the
            # follow-up /accounts/2fa/login call can't be spoofed with an
            # arbitrary account_id — no tokens are issued yet, and no
            # refresh cookie is set.
            totp_session_token = secrets.token_urlsafe(32)
            await redis.set_totp_session(totp_session_token, grpc_response.account_id)

            return schemas.LoginResponse(
                requires_2fa=True,
                totp_session_token=totp_session_token,
                account_id=grpc_response.account_id,
                email=grpc_response.email,
            )

        _set_refresh_cookie(response, grpc_response.refresh_token)

        return schemas.LoginResponse(
            access_token=grpc_response.access_token,
            refresh_token=grpc_response.refresh_token,
            account_id=grpc_response.account_id,
            email=grpc_response.email,
            expires_in=grpc_response.expires_in,
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error during login: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Login service timeout, please try again",
            )

        elif e.code() == grpc.StatusCode.UNAUTHENTICATED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        elif e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed",
        )


@router.post(
    "/accounts/refresh",
    response_model=schemas.RefreshTokenResponse,
    summary="Refresh access token",
    description="Exchange a refresh token for new access and refresh tokens",
    response_description="New JWT access token and refresh token",
    responses={
        200: {
            "description": "Token refreshed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "refresh_token": "XyZ789...",
                        "token_type": "bearer",
                        "account_id": 123,
                        "email": "user@example.com",
                        "expires_in": 900,
                    }
                }
            },
        },
        401: {
            "description": "Invalid or expired refresh token",
            "content": {
                "application/json": {"example": {"detail": "Invalid or expired refresh token"}}
            },
        },
        503: {
            "description": "Service temporarily unavailable",
            "content": {
                "application/json": {"example": {"detail": "Token refresh service timeout"}}
            },
        },
    },
)
async def refresh_token(
    request: fastapi.Request,
    response: fastapi.Response,
    body: typing.Optional[schemas.RefreshTokenRequest] = fastapi.Body(default=None),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Refresh access token using a valid refresh token.

    This endpoint implements token rotation: a new access token AND a new
    refresh token are issued, and the old refresh token is revoked.

    Refresh tokens are long-lived (7 days by default) while access tokens
    are short-lived (15 minutes by default).

    The refresh token can be supplied in the request body (legacy) or, now,
    via the httpOnly `refresh_token` cookie set at login/register — the
    cookie is used when the body is omitted or empty, so a client can call
    this endpoint with no body at all to silently re-establish a session.

    This enables users to stay logged in without re-entering credentials.
    """

    raw_refresh_token = _get_refresh_token_from_request(
        request, body.refresh_token if body else None
    )

    if not raw_refresh_token:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.RefreshTokenRequest(refresh_token=raw_refresh_token)

        grpc_response = await stub.RefreshToken(grpc_request, timeout=config.settings.GRPC_TIMEOUT)

        _set_refresh_cookie(response, grpc_response.refresh_token)

        return schemas.RefreshTokenResponse(
            access_token=grpc_response.access_token,
            refresh_token=grpc_response.refresh_token,
            account_id=grpc_response.account_id,
            email=grpc_response.email,
            expires_in=grpc_response.expires_in,
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error during token refresh: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Token refresh service timeout",
            )

        elif e.code() == grpc.StatusCode.UNAUTHENTICATED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed",
        )


@router.post(
    "/accounts/logout",
    status_code=fastapi.status.HTTP_204_NO_CONTENT,
    summary="Logout from account",
    description="Revoke all refresh tokens for the current account, logging out from all devices",
    responses={
        204: {"description": "Logout successful, all refresh tokens revoked"},
        401: {
            "description": "Not authenticated",
            "content": {"application/json": {"example": {"detail": "Authentication required"}}},
        },
    },
)
async def logout_account(
    request: fastapi.Request,
    response: fastapi.Response,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Logout from account and revoke all refresh tokens.

    This will invalidate all refresh tokens for the account, effectively
    logging out the user from all devices, and clears the httpOnly
    refresh_token cookie.

    Access tokens will continue to work until they expire (15 minutes).

    Requires a valid JWT token in the Authorization header.
    """

    if not hasattr(request.state, "account_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)
        await stub.RevokeAllSessions(
            auth_pb2.RevokeAllSessionsRequest(
                account_id=request.state.account_id,
                include_current=True,
            ),
            timeout=config.settings.GRPC_TIMEOUT,
        )
    except grpc.RpcError as e:
        # Don't fail the logout over this — the client is discarding its
        # access token either way, and the refresh cookie is cleared below.
        logger.warning(f"gRPC error revoking sessions during logout: {e.code()} - {e.details()}")

    _clear_refresh_cookie(response)

    # Must mutate and return the injected `response` (not a fresh
    # fastapi.Response(...)) - the Set-Cookie header from
    # _clear_refresh_cookie above lives on this exact object, and returning
    # a different Response instance would silently drop it.
    response.status_code = fastapi.status.HTTP_204_NO_CONTENT
    return response


@router.get(
    "/accounts/me",
    summary="Get current account info",
    description="Retrieve account details for the currently authenticated user",
    response_description="Account information",
    responses={
        200: {
            "description": "Account details retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "account_id": 123,
                        "email": "user@example.com",
                        "name": "John Doe",
                        "created_at": "2024-01-15T10:30:00Z",
                    }
                }
            },
        },
        401: {
            "description": "Not authenticated",
            "content": {"application/json": {"example": {"detail": "Authentication required"}}},
        },
        404: {
            "description": "Account not found",
            "content": {"application/json": {"example": {"detail": "Account not found"}}},
        },
        503: {
            "description": "Service timeout",
            "content": {"application/json": {"example": {"detail": "Service timeout"}}},
        },
    },
)
async def get_current_account(
    request: fastapi.Request,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Get current authenticated account information.

    Returns the account details including account_id, email, name, and
    creation timestamp. Requires a valid JWT token in the Authorization header.
    """

    if not hasattr(request.state, "account_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    account_id = request.state.account_id

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.GetAccountRequest(account_id=account_id)

        response = await stub.GetAccount(grpc_request, timeout=config.settings.GRPC_TIMEOUT)

        return {
            "account_id": response.account_id,
            "email": response.email,
            "name": response.name,
            "created_at": response.created_at,
            "email_verified": response.email_verified,
            "totp_enabled": response.totp_enabled,
        }

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service timeout",
            )

        elif e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail="Account not found",
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch account",
        )


@router.patch(
    "/accounts/me/name",
    response_model=schemas.UpdateAccountNameResponse,
    summary="Update account name",
    description="Update the name for the currently authenticated user",
    response_description="Updated account information",
    responses={
        200: {
            "description": "Account name updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "name": "Jane Smith",
                        "message": "Account name updated successfully",
                    }
                }
            },
        },
        400: {
            "description": "Invalid input (empty name or too long)",
            "content": {"application/json": {"example": {"detail": "Name cannot be empty"}}},
        },
        401: {
            "description": "Not authenticated",
            "content": {"application/json": {"example": {"detail": "Authentication required"}}},
        },
        503: {
            "description": "Service timeout",
            "content": {"application/json": {"example": {"detail": "Service timeout"}}},
        },
    },
)
async def update_account_name(
    request: fastapi.Request,
    body: schemas.UpdateAccountNameRequest,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Update the name for the currently authenticated account.

    The name must be:
    - Non-empty (after trimming whitespace)
    - Maximum 255 characters

    Requires a valid JWT token in the Authorization header.
    """

    if not hasattr(request.state, "account_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    account_id = request.state.account_id

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.UpdateAccountNameRequest(
            account_id=account_id,
            name=body.name,
        )

        response = await stub.UpdateAccountName(grpc_request, timeout=config.settings.GRPC_TIMEOUT)

        if not response.success:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail="Failed to update account name",
            )

        return schemas.UpdateAccountNameResponse(name=response.name)

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service timeout",
            )

        elif e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail=e.details(),
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update account name",
        )


@router.post(
    "/accounts/me/password",
    response_model=schemas.ChangePasswordResponse,
    summary="Change account password",
    description="Change password for the currently authenticated user",
    response_description="Password change confirmation",
    responses={
        200: {
            "description": "Password changed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Password changed successfully",
                    }
                }
            },
        },
        400: {
            "description": "Invalid input (wrong old password or weak new password)",
            "content": {
                "application/json": {"example": {"detail": "Current password is incorrect"}}
            },
        },
        401: {
            "description": "Not authenticated",
            "content": {"application/json": {"example": {"detail": "Authentication required"}}},
        },
        503: {
            "description": "Service timeout",
            "content": {"application/json": {"example": {"detail": "Service timeout"}}},
        },
    },
)
async def change_password(
    request: fastapi.Request,
    body: schemas.ChangePasswordRequest,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Change password for the currently authenticated account.

    Requires both the current password for verification and a new password.
    The new password must meet the following requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit

    Requires a valid JWT token in the Authorization header.
    """

    if not hasattr(request.state, "account_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    account_id = request.state.account_id

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.ChangePasswordRequest(
            account_id=account_id,
            old_password=body.old_password,
            new_password=body.new_password,
        )

        response = await stub.ChangePassword(grpc_request, timeout=config.settings.GRPC_TIMEOUT)

        if not response.success:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail="Failed to change password",
            )

        return schemas.ChangePasswordResponse()

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service timeout",
            )

        elif e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail=e.details(),
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password",
        )


@router.post(
    "/accounts/verify-email",
    response_model=schemas.VerifyEmailResponse,
    summary="Verify email address",
    description="Verify an account's email using the token emailed at registration (or resend). Unauthenticated — the token itself is the credential.",
    responses={
        200: {"description": "Email verified successfully"},
        400: {"description": "Invalid or expired verification token"},
        503: {"description": "Service timeout"},
    },
)
async def verify_email(
    body: schemas.VerifyEmailRequest,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_response = await stub.VerifyEmail(
            auth_pb2.VerifyEmailRequest(token=body.token),
            timeout=config.settings.GRPC_TIMEOUT,
        )

        if not grpc_response.success:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail=grpc_response.error_message or "Invalid or expired verification token",
            )

        return schemas.VerifyEmailResponse()

    except fastapi.HTTPException:
        raise

    except grpc.RpcError as e:
        logger.error(f"gRPC error verifying email: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service timeout",
            )
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail=e.details() or "Invalid or expired verification token",
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify email",
        )


@router.post(
    "/accounts/resend-verification",
    response_model=schemas.ResendVerificationResponse,
    summary="Resend verification email",
    description="Regenerate and re-send the email verification link for the currently authenticated account.",
    responses={
        200: {"description": "Verification email sent (or account already verified)"},
        401: {"description": "Not authenticated"},
        503: {"description": "Service timeout"},
    },
)
async def resend_verification(
    request: fastapi.Request,
    background_tasks: fastapi.BackgroundTasks,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    if not hasattr(request.state, "account_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_response = await stub.ResendVerificationEmail(
            auth_pb2.ResendVerificationEmailRequest(account_id=request.state.account_id),
            timeout=config.settings.GRPC_TIMEOUT,
        )

        if grpc_response.already_verified:
            return schemas.ResendVerificationResponse(
                already_verified=True, message="Email is already verified"
            )

        if grpc_response.verification_token:
            background_tasks.add_task(
                _send_verification_email,
                grpc_response.email,
                grpc_response.verification_token,
            )

        return schemas.ResendVerificationResponse()

    except grpc.RpcError as e:
        logger.error(f"gRPC error resending verification email: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service timeout",
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resend verification email",
        )


@router.post(
    "/accounts/2fa/setup",
    response_model=schemas.Setup2FAResponse,
    summary="Start TOTP 2FA setup",
    description="Generate a pending TOTP secret and provisioning URI for QR-code display. Does NOT enable 2FA — call /accounts/2fa/verify with a code to activate.",
    responses={
        200: {"description": "Pending TOTP secret generated"},
        401: {"description": "Not authenticated"},
        503: {"description": "Service timeout"},
    },
)
async def setup_2fa(
    request: fastapi.Request,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    if not hasattr(request.state, "account_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_response = await stub.Setup2FA(
            auth_pb2.Setup2FARequest(account_id=request.state.account_id),
            timeout=config.settings.GRPC_TIMEOUT,
        )

        return schemas.Setup2FAResponse(
            secret=grpc_response.secret,
            provisioning_uri=grpc_response.provisioning_uri,
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error setting up 2FA: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service timeout",
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start 2FA setup",
        )


@router.post(
    "/accounts/2fa/verify",
    response_model=schemas.Verify2FAResponse,
    summary="Confirm TOTP 2FA setup",
    description="Verify a code against the pending TOTP secret and enable 2FA. Returns one-time backup codes — shown only in this response.",
    responses={
        200: {"description": "2FA enabled, backup codes returned"},
        400: {"description": "Invalid verification code, or no pending setup"},
        401: {"description": "Not authenticated"},
        503: {"description": "Service timeout"},
    },
)
async def verify_2fa_setup(
    request: fastapi.Request,
    body: schemas.Verify2FARequest,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    if not hasattr(request.state, "account_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_response = await stub.Verify2FASetup(
            auth_pb2.Verify2FASetupRequest(account_id=request.state.account_id, code=body.code),
            timeout=config.settings.GRPC_TIMEOUT,
        )

        if not grpc_response.success:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail=grpc_response.error_message or "Invalid verification code",
            )

        return schemas.Verify2FAResponse(backup_codes=list(grpc_response.backup_codes))

    except fastapi.HTTPException:
        raise

    except grpc.RpcError as e:
        logger.error(f"gRPC error verifying 2FA setup: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service timeout",
            )
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail=e.details() or "Invalid verification code",
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify 2FA setup",
        )


@router.post(
    "/accounts/2fa/disable",
    response_model=schemas.Disable2FAResponse,
    summary="Disable 2FA",
    description="Disable TOTP 2FA for the account. Requires current password re-entry.",
    responses={
        200: {"description": "2FA disabled"},
        400: {"description": "Incorrect password, or 2FA not enabled"},
        401: {"description": "Not authenticated"},
        503: {"description": "Service timeout"},
    },
)
async def disable_2fa(
    request: fastapi.Request,
    body: schemas.Disable2FARequest,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    if not hasattr(request.state, "account_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_response = await stub.Disable2FA(
            auth_pb2.Disable2FARequest(account_id=request.state.account_id, password=body.password),
            timeout=config.settings.GRPC_TIMEOUT,
        )

        if not grpc_response.success:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail=grpc_response.error_message or "Failed to disable 2FA",
            )

        return schemas.Disable2FAResponse()

    except fastapi.HTTPException:
        raise

    except grpc.RpcError as e:
        logger.error(f"gRPC error disabling 2FA: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service timeout",
            )
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail=e.details() or "Failed to disable 2FA",
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disable 2FA",
        )


@router.post(
    "/accounts/2fa/login",
    response_model=schemas.LoginResponse,
    summary="Complete 2FA login",
    description="Complete a login that returned requires_2fa=true, using the totp_session_token and a TOTP (or backup) code. Unauthenticated — the session token + code together are the credential.",
    responses={
        200: {"description": "Login completed, tokens issued"},
        401: {"description": "Invalid/expired session token or invalid code"},
        503: {"description": "Service timeout"},
    },
)
async def complete_2fa_login(
    request: fastapi.Request,
    response: fastapi.Response,
    body: schemas.TOTPLoginRequest,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
    redis: redis_client.RedisClient = fastapi.Depends(dependencies.get_redis_client),
):
    account_id = await redis.get_totp_session(body.totp_session_token)
    if account_id is None:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="2FA session expired or invalid — please log in again",
        )

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_response = await stub.VerifyTOTPLogin(
            auth_pb2.VerifyTOTPLoginRequest(
                account_id=account_id,
                code=body.code,
                device_info=request.headers.get("user-agent", "")[:255],
            ),
            timeout=config.settings.GRPC_TIMEOUT,
        )

        if not grpc_response.success:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail=grpc_response.error_message or "Invalid 2FA code",
            )

        # One-shot: the session token can't be replayed after a successful
        # (or exhausted) attempt.
        await redis.delete_totp_session(body.totp_session_token)

        _set_refresh_cookie(response, grpc_response.refresh_token)

        return schemas.LoginResponse(
            access_token=grpc_response.access_token,
            refresh_token=grpc_response.refresh_token,
            account_id=grpc_response.account_id,
            email=grpc_response.email,
            expires_in=grpc_response.expires_in,
        )

    except fastapi.HTTPException:
        raise

    except grpc.RpcError as e:
        logger.error(f"gRPC error completing 2FA login: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service timeout",
            )
        if e.code() == grpc.StatusCode.UNAUTHENTICATED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail=e.details() or "Invalid 2FA code",
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete 2FA login",
        )


@router.get(
    "/accounts/sessions",
    response_model=schemas.ListSessionsResponse,
    summary="List active sessions",
    description="List the caller's active (non-revoked, non-expired) refresh-token sessions, e.g. for a 'manage devices' UI.",
    responses={
        200: {"description": "Sessions retrieved"},
        401: {"description": "Not authenticated"},
        503: {"description": "Service timeout"},
    },
)
async def list_sessions(
    request: fastapi.Request,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    if not hasattr(request.state, "account_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    current_raw_token = request.cookies.get(REFRESH_COOKIE_NAME)

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_kwargs = {"account_id": request.state.account_id}
        if current_raw_token:
            grpc_kwargs["current_refresh_token"] = current_raw_token

        grpc_response = await stub.ListSessions(
            auth_pb2.ListSessionsRequest(**grpc_kwargs),
            timeout=config.settings.GRPC_TIMEOUT,
        )

        sessions = [
            schemas.SessionInfo(
                id=s.id,
                device_info=s.device_info if s.HasField("device_info") else None,
                created_at=s.created_at,
                last_used_at=s.last_used_at if s.HasField("last_used_at") else None,
                expires_at=s.expires_at,
                is_current=s.is_current,
            )
            for s in grpc_response.sessions
        ]

        return schemas.ListSessionsResponse(sessions=sessions, total=len(sessions))

    except grpc.RpcError as e:
        logger.error(f"gRPC error listing sessions: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service timeout",
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list sessions",
        )


@router.post(
    "/accounts/sessions/{session_id}/revoke",
    response_model=schemas.RevokeSessionResponse,
    summary="Revoke a session",
    description="Revoke a single session (refresh token) belonging to the caller.",
    responses={
        200: {"description": "Session revoked"},
        401: {"description": "Not authenticated"},
        404: {"description": "Session not found"},
        503: {"description": "Service timeout"},
    },
)
async def revoke_session(
    request: fastapi.Request,
    session_id: int = fastapi.Path(..., description="Session (refresh token) ID to revoke"),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    if not hasattr(request.state, "account_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_response = await stub.RevokeSession(
            auth_pb2.RevokeSessionRequest(
                account_id=request.state.account_id, session_id=session_id
            ),
            timeout=config.settings.GRPC_TIMEOUT,
        )

        if not grpc_response.success:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail=grpc_response.error_message or "Session not found",
            )

        return schemas.RevokeSessionResponse()

    except fastapi.HTTPException:
        raise

    except grpc.RpcError as e:
        logger.error(f"gRPC error revoking session: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service timeout",
            )
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke session",
        )


@router.post(
    "/accounts/sessions/revoke-all",
    response_model=schemas.RevokeAllSessionsResponse,
    summary="Revoke all sessions",
    description="Revoke all of the caller's sessions. By default the current session is preserved (like GitHub's 'sign out all other sessions'); pass include_current=true to also sign out the current session.",
    responses={
        200: {"description": "Sessions revoked"},
        401: {"description": "Not authenticated"},
        503: {"description": "Service timeout"},
    },
)
async def revoke_all_sessions(
    request: fastapi.Request,
    response: fastapi.Response,
    include_current: bool = fastapi.Query(
        default=False,
        description="Also revoke the session making this request (equivalent to 'sign out everywhere including here')",
    ),
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    if not hasattr(request.state, "account_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    current_raw_token = request.cookies.get(REFRESH_COOKIE_NAME)

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_kwargs = {
            "account_id": request.state.account_id,
            "include_current": include_current,
        }
        if current_raw_token:
            grpc_kwargs["current_refresh_token"] = current_raw_token

        grpc_response = await stub.RevokeAllSessions(
            auth_pb2.RevokeAllSessionsRequest(**grpc_kwargs),
            timeout=config.settings.GRPC_TIMEOUT,
        )

        if include_current:
            _clear_refresh_cookie(response)

        return schemas.RevokeAllSessionsResponse(revoked_count=grpc_response.revoked_count)

    except grpc.RpcError as e:
        logger.error(f"gRPC error revoking all sessions: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service timeout",
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke sessions",
        )


@router.get(
    "/accounts/stats",
    summary="Get auth statistics",
    description="Performance metrics for auth endpoints (internal use)",
    include_in_schema=False,  # Hide from public docs
)
async def get_auth_stats(request: fastapi.Request):
    """
    Get authentication statistics.

    Args:
        request: HTTP request with app state

    Returns:
        Dictionary of auth-related stats
    """

    stats = {}

    if hasattr(request.app.state, "auth_middleware"):
        auth_middleware = request.app.state.auth_middleware
        stats["auth"] = auth_middleware.get_stats()

    if hasattr(request.app.state, "rate_limit_middleware"):
        rate_limit_middleware = request.app.state.rate_limit_middleware
        stats["rate_limit"] = rate_limit_middleware.get_stats()

    if hasattr(request.state, "circuit_breakers"):
        circuit_breakers = request.state.circuit_breakers
        stats["circuit_breakers"] = circuit_breakers.get_all_stats()

    return stats
    return stats
