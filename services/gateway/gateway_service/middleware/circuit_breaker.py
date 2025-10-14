import asyncio
import enum
import logging
import time
import typing

import fastapi
from gateway_service import config
from gateway_service.services import grpc_pool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class CircuitState(str, enum.Enum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"  # Healthy, requests pass through
    OPEN = "OPEN"  # Failing, fast-fail immediately
    HALF_OPEN = "HALF_OPEN"  # Testing recovery


class CircuitBreaker:
    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_max_calls: int = 3,
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: typing.Optional[float] = None
        self.half_open_calls = 0

        self._lock = asyncio.Lock()

        self._total_calls = 0
        self._failed_calls = 0
        self._rejected_calls = 0

    async def call(self, func, *args, **kwargs):
        """
        Execute function with circuit breaker protection.

        Returns:
            Function result or raises exception

        Raises:
            HTTPException: If circuit is open and no fallback available
        """

        self._total_calls += 1

        current_state = await self._check_state()

        if current_state == CircuitState.OPEN:
            self._rejected_calls += 1
            logger.warning(
                f"Circuit breaker OPEN for {self.service_name}, "
                f"fast-failing request"
            )
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"{self.service_name} is currently unavailable",
            )

        if current_state == CircuitState.HALF_OPEN:
            async with self._lock:
                if self.half_open_calls >= self.half_open_max_calls:
                    self._rejected_calls += 1
                    logger.debug(
                        f"Circuit breaker HALF_OPEN limit reached for "
                        f"{self.service_name}"
                    )
                    raise fastapi.HTTPException(
                        status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"{self.service_name} is recovering, try again",
                    )
                self.half_open_calls += 1

        try:
            result = await func(*args, **kwargs)

            await self._on_success()

            return result

        except Exception as e:
            await self._on_failure()

            raise

        finally:
            if current_state == CircuitState.HALF_OPEN:
                async with self._lock:
                    self.half_open_calls -= 1

    async def _check_state(self) -> CircuitState:
        """
        Check and update circuit state.

        State Transitions:
        - CLOSED → OPEN: After failure_threshold failures
        - OPEN → HALF_OPEN: After recovery_timeout seconds
        - HALF_OPEN → CLOSED: After successful call
        - HALF_OPEN → OPEN: After any failure
        """

        async with self._lock:
            if self.state == CircuitState.OPEN:
                if (
                    self.last_failure_time
                    and time.time() - self.last_failure_time >= self.recovery_timeout
                ):

                    logger.info(
                        f"Circuit breaker transitioning to HALF_OPEN for "
                        f"{self.service_name}"
                    )
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0

            return self.state

    async def _on_success(self):
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                logger.info(
                    f"Circuit breaker transitioning to CLOSED for "
                    f"{self.service_name}"
                )
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.last_failure_time = None

            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    async def _on_failure(self):
        self._failed_calls += 1

        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                logger.warning(
                    f"Circuit breaker transitioning back to OPEN for "
                    f"{self.service_name}"
                )
                self.state = CircuitState.OPEN

            elif self.state == CircuitState.CLOSED:
                if self.failure_count >= self.failure_threshold:
                    logger.error(
                        f"Circuit breaker transitioning to OPEN for "
                        f"{self.service_name} "
                        f"(failures: {self.failure_count})"
                    )
                    self.state = CircuitState.OPEN

    def get_stats(self) -> typing.Dict:
        failure_rate = 0.0
        if self._total_calls > 0:
            failure_rate = (self._failed_calls / self._total_calls) * 100

        rejection_rate = 0.0
        if self._total_calls > 0:
            rejection_rate = (self._rejected_calls / self._total_calls) * 100

        return {
            "service": self.service_name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "total_calls": self._total_calls,
            "failed_calls": self._failed_calls,
            "rejected_calls": self._rejected_calls,
            "failure_rate": round(failure_rate, 2),
            "rejection_rate": round(rejection_rate, 2),
            "last_failure_time": self.last_failure_time,
        }


class CircuitBreakerMiddleware(BaseHTTPMiddleware):
    """
    Middleware that wraps gRPC calls with circuit breakers.

    Design: Per-service circuit breakers prevent one failing service
    from bringing down the entire system.
    """

    def __init__(self, app, grpc_pool: grpc_pool.GRPCPoolManager):
        super().__init__(app)
        self.grpc_pool = grpc_pool

        self.breakers: typing.Dict[str, CircuitBreaker] = {}

        # Initialize breakers for known services
        self._init_breaker("auth")
        # Add more services as they're implemented:
        # self._init_breaker("ingestion")
        # self._init_breaker("query")

    def _init_breaker(self, service_name: str):
        self.breakers[service_name] = CircuitBreaker(
            service_name=service_name,
            failure_threshold=config.settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=config.settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
            half_open_max_calls=config.settings.CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS,
        )
        logger.info(f"Initialized circuit breaker for {service_name}")

    def get_breaker(self, service_name: str) -> CircuitBreaker:
        if service_name not in self.breakers:
            self._init_breaker(service_name)
        return self.breakers[service_name]

    async def dispatch(self, request: fastapi.Request, call_next) -> Response:
        """
        Middleware dispatch.

        Note: Circuit breaker logic is applied at the gRPC call level,
        not at the HTTP request level. This middleware just exposes
        breaker stats and manages state.
        """

        request.state.circuit_breakers = self

        try:
            response = await call_next(request)
            return response

        except fastapi.HTTPException:
            raise

        except Exception as e:
            logger.error(f"Circuit breaker middleware error: {e}", exc_info=True)
            raise

    def get_all_stats(self) -> typing.Dict[str, typing.Dict]:
        return {name: breaker.get_stats() for name, breaker in self.breakers.items()}


async def call_with_circuit_breaker(
    request: fastapi.Request, service_name: str, grpc_call, *args, **kwargs
):
    """
    Wrap a gRPC call with circuit breaker protection.

    Usage in routes:
        async def validate_key(request: Request, api_key: str):
            stub = grpc_pool.get_stub("auth", AuthServiceStub)

            response = await call_with_circuit_breaker(
                request,
                "auth",
                stub.ValidateApiKey,
                ValidateApiKeyRequest(api_key=api_key)
            )
    """

    if not hasattr(request.state, "circuit_breakers"):
        logger.warning("Circuit breaker middleware not enabled")
        return await grpc_call(*args, **kwargs)

    breaker_manager: CircuitBreakerMiddleware = request.state.circuit_breakers
    breaker = breaker_manager.get_breaker(service_name)

    return await breaker.call(grpc_call, *args, **kwargs)
