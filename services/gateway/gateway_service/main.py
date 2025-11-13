import contextlib
import logging
import typing

import fastapi
import gateway_service.config as config
from fastapi.responses import JSONResponse
from gateway_service.middleware import auth, circuit_breaker, rate_limit
from gateway_service.routes import (
    api_key_routes,
    auth_routes,
    dashboard_routes,
    ingestion_routes,
    project_routes,
    settings_routes,
)
from gateway_service.services import grpc_pool, redis_client

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class GatewayApp:
    def __init__(self):
        self.grpc_pool: grpc_pool.GRPCPoolManager | None = None
        self.redis_client: redis_client.RedisClient | None = None

    async def startup(self):
        logger.info("Gateway Service starting up...")

        self.redis_client = redis_client.RedisClient(
            url=config.settings.REDIS_URL,
            max_connections=50,
            decode_responses=False,
        )
        await self.redis_client.connect()
        logger.info("Redis connection pool initialized")

        self.grpc_pool = grpc_pool.GRPCPoolManager()

        await self.grpc_pool.add_service(
            service_name="auth",
            address=config.settings.AUTH_SERVICE_URL,
            pool_size=10,
        )

        await self.grpc_pool.add_service(
            service_name="ingestion",
            address=config.settings.INGESTION_SERVICE_URL,
            pool_size=10,
        )

        logger.info(f"gRPC pool initialized: {self.grpc_pool.get_stats()}")

    async def shutdown(self):
        logger.info("Gateway Service shutting down...")

        if self.grpc_pool:
            await self.grpc_pool.close_all()
            logger.info("gRPC channels closed")

        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")

        logger.info("Shutdown complete")


gateway_app = GatewayApp()


@contextlib.asynccontextmanager
async def lifespan(app: fastapi.FastAPI) -> typing.AsyncIterator[None]:
    await gateway_app.startup()
    app.state.grpc_pool = gateway_app.grpc_pool
    app.state.redis_client = gateway_app.redis_client
    yield
    await gateway_app.shutdown()


app = fastapi.FastAPI(
    title="Ledger API",
    version="1.0.0",
    description="""
## Ledger - Distributed Log Analytics Platform

Production-ready API for ingesting, storing, and querying millions of logs per second.

### Features

* **High-throughput ingestion** - Process 10K+ requests per second
* **Multi-tenant architecture** - Project-based isolation with API key authentication
* **Rate limiting** - Automatic rate limiting per API key (per-minute and per-hour)
* **Circuit breaker** - Graceful degradation with fallback mechanisms
* **Real-time analytics** - Pre-computed metrics and dashboards
* **Flexible querying** - Filter logs by level, type, time range, and more

### Authentication

All endpoints (except registration and login) require authentication via:
- **JWT Bearer Token** - For account-level operations (project management, settings)
- **API Key** - For log ingestion and project-specific operations

Use the `X-API-Key` header for API key authentication, or `Authorization: Bearer <token>` for JWT authentication.
    """,
    lifespan=lifespan,
    contact={
        "name": "Ledger API Support",
        "url": "https://github.com/JakubTuta/Ledger-APP",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token obtained from /api/v1/accounts/login",
        },
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key created for a project via /api/v1/projects/{project_id}/api-keys",
        },
    }

    openapi_schema["tags"] = [
        {
            "name": "Authentication",
            "description": "Account registration, login, and profile management",
        },
        {
            "name": "Projects",
            "description": "Project creation and management for organizing logs",
        },
        {
            "name": "API Keys",
            "description": "API key creation and revocation for project access",
        },
        {
            "name": "Ingestion",
            "description": "High-throughput log ingestion endpoints (single and batch)",
        },
        {
            "name": "Dashboard",
            "description": "Dashboard panel management for custom views",
        },
        {
            "name": "Settings",
            "description": "Project settings, quotas, and rate limits",
        },
        {
            "name": "Health",
            "description": "Service health and monitoring endpoints",
        },
    ]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get(
    "/health",
    tags=["Health"],
    summary="Basic health check",
    description="Quick health check endpoint that returns service status",
    response_description="Service health status",
    responses={
        200: {
            "description": "Service is healthy",
            "content": {"application/json": {"example": {"status": "healthy"}}},
        }
    },
)
async def health_check():
    return {"status": "healthy"}


@app.get(
    "/health/deep",
    tags=["Health"],
    summary="Deep health check",
    description="Comprehensive health check that verifies Redis and gRPC connections",
    response_description="Detailed health status of all dependencies",
    responses={
        200: {
            "description": "All services healthy or degraded",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "services": {
                            "redis": "healthy",
                            "grpc": {
                                "auth": {
                                    "pool_size": 10,
                                    "active_channels": 10,
                                    "address": "ledger-auth-service:50051",
                                },
                                "ingestion": {
                                    "pool_size": 10,
                                    "active_channels": 10,
                                    "address": "ledger-ingestion:50052",
                                },
                            },
                        },
                    }
                }
            },
        }
    },
)
async def deep_health_check():
    health_status = {"status": "healthy", "services": {}}

    try:
        await gateway_app.redis_client.ping()  # type: ignore
        health_status["services"]["redis"] = "healthy"
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["services"]["redis"] = f"unhealthy: {str(e)}"

    grpc_stats = gateway_app.grpc_pool.get_stats()  # type: ignore
    health_status["services"]["grpc"] = grpc_stats

    return health_status


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    if isinstance(exc, fastapi.HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500, content={"error": "Internal server error", "detail": str(exc)}
    )


def add_middleware(middleware_class, **options):
    app.add_middleware(middleware_class, **options)


# CORS MANAGED BY REVERSE PROXY

add_middleware(
    circuit_breaker.CircuitBreakerMiddleware,
)
add_middleware(
    rate_limit.RateLimitMiddleware,
)
add_middleware(
    auth.AuthMiddleware,
)


def include_router(router, prefix: str = ""):
    app.include_router(router, prefix=prefix)


include_router(auth_routes.router, prefix="/api/v1")
include_router(project_routes.router, prefix="/api/v1")
include_router(api_key_routes.router, prefix="/api/v1")
include_router(dashboard_routes.router, prefix="/api/v1")
include_router(ingestion_routes.router, prefix="/api/v1")
include_router(settings_routes.router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=4 if config.settings.ENV == "production" else 1,
        log_level="info",
        access_log=True,
    )
