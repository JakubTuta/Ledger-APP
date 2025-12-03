import asyncio
import logging
import typing

import fastapi
import gateway_service.schemas as schemas
import grpc
from gateway_service import dependencies
from gateway_service.proto import auth_pb2, auth_pb2_grpc
from gateway_service.services import grpc_pool, redis_client

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(tags=["Authentication"])


# ==================== ROUTE HANDLERS ====================
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
            "content": {
                "application/json": {"example": {"detail": "Email already registered"}}
            },
        },
        503: {
            "description": "Service temporarily unavailable",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Registration service timeout, please try again"
                    }
                }
            },
        },
    },
)
async def register_account(
    request: schemas.RegisterRequest,
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

        register_request = auth_pb2.RegisterRequest(
            email=request.email, password=request.password
        )

        register_response = await asyncio.wait_for(
            stub.Register(register_request),
            timeout=10.0,
        )

        login_request = auth_pb2.LoginRequest(
            email=request.email, password=request.password
        )

        login_response = await asyncio.wait_for(
            stub.Login(login_request),
            timeout=10.0,
        )

        return schemas.RegisterResponse(
            access_token=login_response.access_token,
            refresh_token=login_response.refresh_token,
            account_id=register_response.account_id,
            email=register_response.email,
            name=register_response.name,
            expires_in=login_response.expires_in,
        )

    except asyncio.TimeoutError:
        logger.error("Auth Service timeout during registration")
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration service timeout, please try again",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error during registration: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.ALREADY_EXISTS:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        elif e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail=e.details()
            )

        else:
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
            "content": {
                "application/json": {"example": {"detail": "Invalid email or password"}}
            },
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

        grpc_request = auth_pb2.LoginRequest(
            email=request.email, password=request.password
        )

        response = await asyncio.wait_for(stub.Login(grpc_request), timeout=10.0)

        return schemas.LoginResponse(
            access_token=response.access_token,
            refresh_token=response.refresh_token,
            account_id=response.account_id,
            email=response.email,
            expires_in=response.expires_in,
        )

    except asyncio.TimeoutError:
        logger.error("Auth Service timeout during login")
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login service timeout, please try again",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error during login: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.UNAUTHENTICATED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        elif e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        else:
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
                "application/json": {
                    "example": {"detail": "Invalid or expired refresh token"}
                }
            },
        },
        503: {
            "description": "Service temporarily unavailable",
            "content": {
                "application/json": {
                    "example": {"detail": "Token refresh service timeout"}
                }
            },
        },
    },
)
async def refresh_token(
    request: schemas.RefreshTokenRequest,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Refresh access token using a valid refresh token.

    This endpoint implements token rotation: a new access token AND a new
    refresh token are issued, and the old refresh token is revoked.

    Refresh tokens are long-lived (7 days by default) while access tokens
    are short-lived (15 minutes by default).

    This enables users to stay logged in without re-entering credentials.
    """

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.RefreshTokenRequest(
            refresh_token=request.refresh_token
        )

        response = await asyncio.wait_for(
            stub.RefreshToken(grpc_request), timeout=10.0
        )

        return schemas.RefreshTokenResponse(
            access_token=response.access_token,
            refresh_token=response.refresh_token,
            account_id=response.account_id,
            email=response.email,
            expires_in=response.expires_in,
        )

    except asyncio.TimeoutError:
        logger.error("Auth Service timeout during token refresh")
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token refresh service timeout",
        )

    except grpc.RpcError as e:
        logger.error(f"gRPC error during token refresh: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.UNAUTHENTICATED:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        else:
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
            "content": {
                "application/json": {"example": {"detail": "Authentication required"}}
            },
        },
    },
)
async def logout_account(
    request: fastapi.Request,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Logout from account and revoke all refresh tokens.

    This will invalidate all refresh tokens for the account, effectively
    logging out the user from all devices.

    Access tokens will continue to work until they expire (15 minutes).

    Requires a valid JWT token in the Authorization header.
    """

    if not hasattr(request.state, "account_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return fastapi.Response(status_code=fastapi.status.HTTP_204_NO_CONTENT)


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
            "content": {
                "application/json": {"example": {"detail": "Authentication required"}}
            },
        },
        404: {
            "description": "Account not found",
            "content": {
                "application/json": {"example": {"detail": "Account not found"}}
            },
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

        response = await asyncio.wait_for(stub.GetAccount(grpc_request), timeout=5.0)

        return {
            "account_id": response.account_id,
            "email": response.email,
            "name": response.name,
            "created_at": response.created_at,
        }

    except asyncio.TimeoutError:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout",
        )

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
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
            "content": {
                "application/json": {"example": {"detail": "Name cannot be empty"}}
            },
        },
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {"example": {"detail": "Authentication required"}}
            },
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

        response = await asyncio.wait_for(
            stub.UpdateAccountName(grpc_request), timeout=5.0
        )

        if not response.success:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail="Failed to update account name",
            )

        return schemas.UpdateAccountNameResponse(name=response.name)

    except asyncio.TimeoutError:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout",
        )

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
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
                "application/json": {
                    "example": {"detail": "Current password is incorrect"}
                }
            },
        },
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {"example": {"detail": "Authentication required"}}
            },
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

        response = await asyncio.wait_for(
            stub.ChangePassword(grpc_request), timeout=5.0
        )

        if not response.success:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail="Failed to change password",
            )

        return schemas.ChangePasswordResponse()

    except asyncio.TimeoutError:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service timeout",
        )

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail=e.details(),
            )

        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password",
        )


# ==================== HELPER FUNCTIONS ====================


async def verify_jwt_token(token: str, redis: redis_client.RedisClient) -> typing.Dict:
    session_key = f"session:{token}"
    cached = await redis.client.get(session_key)  # type: ignore

    if cached:
        return eval(cached.decode())

    raise fastapi.HTTPException(
        status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
    )


# ==================== PERFORMANCE MONITORING ====================


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
