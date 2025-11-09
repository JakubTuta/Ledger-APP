import asyncio
import logging
import typing

import fastapi
import grpc
import pydantic
from gateway_service import dependencies
from gateway_service.proto import auth_pb2, auth_pb2_grpc
from gateway_service.services import grpc_pool, redis_client

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(tags=["Authentication"])


# ==================== REQUEST/RESPONSE MODELS ====================


class RegisterRequest(pydantic.BaseModel):
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
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123",
                "name": "John Doe",
            }
        }
    )


class RegisterResponse(pydantic.BaseModel):
    access_token: str = pydantic.Field(..., description="JWT access token for immediate use")
    token_type: str = pydantic.Field(
        default="bearer", description="Token type (always 'bearer')"
    )
    account_id: int = pydantic.Field(..., description="Unique account identifier")
    email: str = pydantic.Field(..., description="Registered email address")
    name: str = pydantic.Field(..., description="User's full name")
    expires_in: int = pydantic.Field(
        default=3600, description="Token expiration time in seconds"
    )
    message: str = pydantic.Field(
        default="Account created successfully", description="Success message"
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
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
    )


class LoginRequest(pydantic.BaseModel):
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
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123",
            }
        }
    )


class LoginResponse(pydantic.BaseModel):
    access_token: str = pydantic.Field(..., description="JWT access token")
    token_type: str = pydantic.Field(
        default="bearer", description="Token type (always 'bearer')"
    )
    account_id: int = pydantic.Field(..., description="Account identifier")
    email: str = pydantic.Field(..., description="Logged in email address")
    expires_in: int = pydantic.Field(
        default=3600, description="Token expiration time in seconds"
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "account_id": 123,
                "email": "user@example.com",
                "expires_in": 3600,
            }
        }
    )


# ==================== ROUTE HANDLERS ====================


@router.post(
    "/accounts/register",
    response_model=RegisterResponse,
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
                    "example": {
                        "detail": "Password must contain uppercase letter"
                    }
                }
            },
        },
        409: {
            "description": "Email already registered",
            "content": {
                "application/json": {
                    "example": {"detail": "Email already registered"}
                }
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
    request: RegisterRequest,
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

        session_key = f"session:{login_response.access_token}"
        session_data = {
            "account_id": login_response.account_id,
            "email": login_response.email,
            "logged_in_at": asyncio.get_event_loop().time(),
        }

        asyncio.create_task(redis.client.setex(session_key, 3600, str(session_data)))  # type: ignore

        return RegisterResponse(
            access_token=login_response.access_token,
            account_id=register_response.account_id,
            email=register_response.email,
            name=register_response.name,
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
    response_model=LoginResponse,
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
                "application/json": {
                    "example": {"detail": "Invalid email or password"}
                }
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
    request: LoginRequest,
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

        session_key = f"session:{response.access_token}"
        session_data = {
            "account_id": response.account_id,
            "email": response.email,
            "logged_in_at": asyncio.get_event_loop().time(),
        }

        asyncio.create_task(redis.client.setex(session_key, 3600, str(session_data)))  # type: ignore

        return LoginResponse(
            access_token=response.access_token,
            account_id=response.account_id,
            email=response.email,
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
    "/accounts/logout",
    status_code=fastapi.status.HTTP_204_NO_CONTENT,
    summary="Logout from account",
    description="Invalidate the current JWT token by removing it from the session cache",
    responses={
        204: {"description": "Logout successful, token invalidated"},
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {"example": {"detail": "Not authenticated"}}
            },
        },
    },
)
async def logout_account(
    request: fastapi.Request,
    redis: redis_client.RedisClient = fastapi.Depends(dependencies.get_redis_client),
):
    """
    Invalidate the current JWT token.

    Removes the token from the Redis session cache, effectively logging out
    the user. The token will no longer be valid for authenticated requests.

    Requires a valid JWT token in the Authorization header.
    """

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    parts = auth_header.split()
    token = parts[1] if len(parts) == 2 else parts[0]

    session_key = f"session:{token}"
    await redis.delete(session_key)

    logger.info("User logged out successfully")


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
                "application/json": {
                    "example": {"detail": "Authentication required"}
                }
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
            "content": {
                "application/json": {"example": {"detail": "Service timeout"}}
            },
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
