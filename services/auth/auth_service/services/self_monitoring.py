"""Ledger reporting its own telemetry to one of its own projects.

Set SELF_MONITORING_API_KEY to an API key of a project (e.g. "Ledger", owned by
the operator's account) and every service exports its logs, errors, traces and
pipeline metrics over OTLP to this deployment's own gateway. It then shows on the
dashboard like any other project, visible only to that project's members - no
extra infrastructure. Unset, every helper here is a no-op and the SDK is never
imported.

The same module ships in every service (they share no package); keep the copies
in sync.
"""

import logging
import time
import typing

import auth_service.config as config

if typing.TYPE_CHECKING:
    import ledger

logger = logging.getLogger(__name__)

# Log lines from these loggers stay in the container log. Each one fires while
# telemetry is being exported or ingested (exporter retries, OTLP quota and
# ingestion errors), so forwarding it would feed the export that caused it.
_UNFORWARDED_LOGGER_PREFIXES = (
    "opentelemetry",
    "urllib3",
    "gateway_service.routes.otlp_routes",
)

_client: "ledger.LedgerClient | None" = None


def _is_forwarded(record: logging.LogRecord) -> bool:
    return not record.name.startswith(_UNFORWARDED_LOGGER_PREFIXES)


def _forward_warnings_and_up(root: logging.Logger) -> None:
    """Narrow the OpenTelemetry handler instrument_logging() put on the root
    logger: WARNING and up (INFO stays in the container log), minus the
    loggers above. The root logger's own level, which drives the console
    output, is left alone."""
    for handler in root.handlers:
        if type(handler).__module__.startswith("opentelemetry"):
            handler.setLevel(logging.WARNING)
            handler.addFilter(_is_forwarded)


def start(service: str) -> "ledger.LedgerClient | None":
    """Begin reporting this process's telemetry, if self-monitoring is configured."""
    global _client
    if _client is not None or not config.settings.SELF_MONITORING_API_KEY:
        return _client

    import ledger

    _client = ledger.LedgerClient(
        api_key=config.settings.SELF_MONITORING_API_KEY,
        base_url=config.settings.SELF_MONITORING_URL,
        service_name=f"ledger-{service}",
        environment=config.settings.ENV,
    )
    _client.instrument_logging()
    _forward_warnings_and_up(logging.getLogger())
    _client.capture_uncaught()
    logger.info(f"Self-monitoring enabled for ledger-{service}")
    return _client


def client() -> "ledger.LedgerClient | None":
    return _client


def increment(name: str, value: int | float = 1, tags: dict[str, str] | None = None) -> None:
    if _client is not None:
        _client.metric_increment(name, value, tags)


def record(name: str, value: int | float, tags: dict[str, str] | None = None) -> None:
    """Record one observation into a histogram."""
    if _client is not None:
        _client.metric_histogram(name, value, tags)


def rpc_interceptors(service: str) -> list:
    """gRPC server interceptors timing every unary RPC per method and outcome
    (the `ledger.<service>.rpc_ms` histogram); none when disabled."""
    if _client is None:
        return []

    import grpc

    metric = f"ledger.{service}.rpc_ms"

    class _RpcTimingInterceptor(grpc.aio.ServerInterceptor):
        async def intercept_service(self, continuation, handler_call_details):
            handler = await continuation(handler_call_details)
            if handler is None or handler.unary_unary is None:
                return handler

            method = handler_call_details.method.rsplit("/", 1)[-1]
            behavior = handler.unary_unary

            async def timed(request, context):
                start = time.perf_counter()
                failed = True
                try:
                    response = await behavior(request, context)
                    failed = context.code() not in (None, grpc.StatusCode.OK)
                    return response
                finally:
                    record(
                        metric,
                        (time.perf_counter() - start) * 1000,
                        {"method": method, "outcome": "error" if failed else "ok"},
                    )

            return grpc.unary_unary_rpc_method_handler(
                timed,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

    return [_RpcTimingInterceptor()]


def stop() -> None:
    global _client
    if _client is not None:
        _client.shutdown_sync()
        _client = None
