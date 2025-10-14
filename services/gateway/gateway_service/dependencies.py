import typing

import fastapi
from gateway_service.services import grpc_pool, redis_client

# ==================== SINGLETON DEPENDENCIES ====================


def get_grpc_pool(request: fastapi.Request) -> grpc_pool.GRPCPoolManager:
    """
    Get gRPC connection pool manager.

    Performance: Returns singleton instance from app state.
    Pool is initialized once at startup, reused for all requests.

    Usage:
        @router.get("/endpoint")
        async def handler(grpc_pool: GRPCPoolManager = Depends(get_grpc_pool)):
            stub = grpc_pool.get_stub("auth", AuthServiceStub)
            ...
    """
    if not hasattr(request.app.state, "grpc_pool"):
        raise RuntimeError("gRPC pool not initialized")

    return request.app.state.grpc_pool


def get_redis_client(request: fastapi.Request) -> redis_client.RedisClient:
    """
    Get Redis client instance.

    Performance: Returns singleton instance with connection pool.
    Client is initialized once at startup, reused for all requests.

    Usage:
        @router.get("/endpoint")
        async def handler(redis: RedisClient = Depends(get_redis_client)):
            data = await redis.get_cached_api_key(key)
            ...
    """
    if not hasattr(request.app.state, "redis_client"):
        raise RuntimeError("Redis client not initialized")

    return request.app.state.redis_client


# ==================== AUTH DEPENDENCIES ====================


def get_current_project_id(request: fastapi.Request) -> int:
    """
    Get current project ID from request state.

    Performance: O(1) attribute access.
    Data is attached by AuthMiddleware, no I/O needed.

    Usage:
        @router.get("/projects/{project_id}/logs")
        async def get_logs(project_id: int = Depends(get_current_project_id)):
            # project_id is validated and guaranteed to exist
            ...

    Raises:
        HTTPException: 401 if not authenticated
    """
    if not hasattr(request.state, "project_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return request.state.project_id


def get_current_account_id(request: fastapi.Request) -> int:
    """
    Get current account ID from request state.

    Performance: O(1) attribute access.
    """
    if not hasattr(request.state, "account_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return request.state.account_id


def get_auth_context(request: fastapi.Request) -> typing.Dict:
    """
    Get full authentication context.

    Performance: O(1) attribute access, bundles multiple fields.

    Returns:
        Dict with project_id, account_id, rate_limits, daily_quota

    Usage:
        @router.post("/logs")
        async def ingest_logs(auth: Dict = Depends(get_auth_context)):
            project_id = auth["project_id"]
            rate_limits = auth["rate_limits"]
            ...
    """
    if not hasattr(request.state, "project_id"):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return {
        "project_id": request.state.project_id,
        "account_id": request.state.account_id,
        "rate_limits": request.state.rate_limits,
        "daily_quota": request.state.daily_quota,
    }


# ==================== PAGINATION DEPENDENCIES ====================


class PaginationParams:
    """
    Pagination parameters with validation.

    Performance: Pydantic-like validation without overhead.
    Limits are enforced to prevent expensive queries.
    """

    def __init__(self, page: int = 1, page_size: int = 50, max_page_size: int = 1000):
        if page < 1:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail="Page must be >= 1",
            )

        if page_size < 1:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail="Page size must be >= 1",
            )

        if page_size > max_page_size:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail=f"Page size must be <= {max_page_size}",
            )

        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size
        self.limit = page_size

    def get_offset_limit(self) -> tuple[int, int]:
        """Get SQL OFFSET and LIMIT values."""
        return self.offset, self.limit


def get_pagination(page: int = 1, page_size: int = 50) -> PaginationParams:
    """
    Dependency for pagination parameters.

    Usage:
        @router.get("/projects")
        async def list_projects(
            pagination: PaginationParams = Depends(get_pagination)
        ):
            offset, limit = pagination.get_offset_limit()
            # Use in SQL query
    """
    return PaginationParams(page=page, page_size=page_size)


# ==================== QUERY PARAMETER DEPENDENCIES ====================


class SortParams:
    """
    Sorting parameters with validation.

    Performance: Validates allowed fields to prevent SQL injection.
    """

    def __init__(
        self,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        allowed_fields: typing.Optional[list[str]] = None,
    ):
        if sort_order.lower() not in ["asc", "desc"]:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail="Sort order must be 'asc' or 'desc'",
            )

        if allowed_fields and sort_by not in allowed_fields:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sort field. Allowed: {', '.join(allowed_fields)}",
            )

        self.sort_by = sort_by
        self.sort_order = sort_order.upper()

    def get_order_by_clause(self) -> str:
        """Get SQL ORDER BY clause."""
        return f"{self.sort_by} {self.sort_order}"


# ==================== RATE LIMIT DEPENDENCIES ====================


async def check_endpoint_rate_limit(
    request: fastapi.Request, endpoint_limit: typing.Optional[int] = None
):
    """
    Check rate limit for specific endpoint.

    Performance: Redis pipeline check (<1ms).

    Usage:
        @router.post("/expensive-operation")
        async def expensive_op(
            _: None = Depends(lambda r: check_endpoint_rate_limit(r, 10))
        ):
            # This endpoint has custom limit of 10 req/min
            ...
    """
    if not hasattr(request.state, "project_id"):
        return

    project_id = request.state.project_id
    redis = request.app.state.redis_client

    if endpoint_limit:
        limit_per_minute = endpoint_limit
        limit_per_hour = endpoint_limit * 60
    else:
        limit_per_minute = request.state.rate_limits["per_minute"]
        limit_per_hour = request.state.rate_limits["per_hour"]

    allowed, metadata = await redis.check_rate_limit(
        project_id, limit_per_minute, limit_per_hour
    )

    if not allowed:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for this endpoint",
            headers={"Retry-After": "60"},
        )


# ==================== CIRCUIT BREAKER DEPENDENCIES ====================


def get_circuit_breakers(request: fastapi.Request):
    """
    Get circuit breaker manager.

    Usage:
        @router.get("/endpoint")
        async def handler(
            breakers = Depends(get_circuit_breakers)
        ):
            breaker = breakers.get_breaker("auth")
            result = await breaker.call(some_grpc_call)
    """
    if not hasattr(request.state, "circuit_breakers"):
        raise RuntimeError("Circuit breaker middleware not enabled")

    return request.state.circuit_breakers
