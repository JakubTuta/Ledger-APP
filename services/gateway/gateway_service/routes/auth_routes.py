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
    email: str = pydantic.Field(..., max_length=255)
    password: str = pydantic.Field(..., min_length=8, max_length=64)
    name: str = pydantic.Field(..., min_length=1, max_length=255)

    @pydantic.field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[1]:
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


class RegisterResponse(pydantic.BaseModel):
    account_id: int
    email: str
    name: str
    message: str = "Account created successfully"


class LoginRequest(pydantic.BaseModel):
    email: str = pydantic.Field(..., max_length=255)
    password: str = pydantic.Field(..., min_length=8, max_length=64)

    @pydantic.field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return v.lower()


class LoginResponse(pydantic.BaseModel):
    access_token: str
    token_type: str = "bearer"
    account_id: int
    email: str
    expires_in: int = 3600


# ==================== ROUTE HANDLERS ====================


@router.post(
    "/accounts/register",
    response_model=RegisterResponse,
    status_code=fastapi.status.HTTP_201_CREATED,
    summary="Register new account",
    description="Create a new account with email and password",
)
async def register_account(
    request: RegisterRequest,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Register a new account.

    Args:
        request: Registration details

    Returns:
        Created account details

    Raises:
        203: Email already registered
        400: Invalid input
        500: Registration failed
    """

    try:
        stub = grpc_pool.get_stub("auth", auth_pb2_grpc.AuthServiceStub)

        grpc_request = auth_pb2.RegisterRequest(
            email=request.email, password=request.password
        )

        response = await asyncio.wait_for(
            stub.Register(grpc_request),
            timeout=10.0,
        )

        return RegisterResponse(
            account_id=response.account_id, email=response.email, name=response.name
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
    description="Authenticate with email and password, receive JWT token",
)
async def login_account(
    request: LoginRequest,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
    redis: redis_client.RedisClient = fastapi.Depends(dependencies.get_redis_client),
):
    """
    Login to account and receive JWT token.

    Args:
        request: Login details

    Returns:
        JWT token and account details

    Raises:
        401: Invalid credentials
        500: Login failed
        503: Service timeout
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
    description="Invalidate JWT token",
)
async def logout_account(
    request: fastapi.Request,
    redis: redis_client.RedisClient = fastapi.Depends(dependencies.get_redis_client),
):
    """
    Logout: Invalidate JWT token.

    Args:
        request: HTTP request with Authorization header

    Returns:
        None (204 No Content)

    Raises:
        401: Not authenticated
        500: Logout failed
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
    description="Get account details for authenticated user",
)
async def get_current_account(
    request: fastapi.Request,
    grpc_pool: grpc_pool.GRPCPoolManager = fastapi.Depends(dependencies.get_grpc_pool),
):
    """
    Get current account information.

    Args:
        request: HTTP request with account_id in state

    Returns:
        Account details

    Raises:
        401: Not authenticated
        404: Account not found
        500: Failed to fetch account
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
