import contextlib
import logging
import typing

import fastapi
import gateway_service.config as config
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from gateway_service.middleware import auth, circuit_breaker, rate_limit
from gateway_service.routes import api_key_routes, auth_routes, ingestion_routes, project_routes
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
    title="Ledger Gateway Service",
    version="1.0.0",
    description="High-performance API Gateway with authentication and rate limiting",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/health/deep")
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


add_middleware(
    CORSMiddleware,
    allow_origins=config.settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

add_middleware(
    circuit_breaker.CircuitBreakerMiddleware,
    grpc_pool=gateway_app.grpc_pool,
)
add_middleware(
    rate_limit.RateLimitMiddleware,
    redis_client=gateway_app.redis_client,
)
add_middleware(
    auth.AuthMiddleware,
    redis_client=gateway_app.redis_client,
    grpc_pool=gateway_app.grpc_pool,
)


def include_router(router, prefix: str = ""):
    app.include_router(router, prefix=prefix)


include_router(auth_routes.router, prefix="/api/v1")
include_router(project_routes.router, prefix="/api/v1")
include_router(api_key_routes.router, prefix="/api/v1")
include_router(ingestion_routes.router, prefix="/api/v1")


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
