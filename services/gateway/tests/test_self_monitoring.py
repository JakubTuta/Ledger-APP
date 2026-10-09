import logging
import pathlib
import sys

import grpc
import pytest

import gateway_service.services.self_monitoring as self_monitoring

_SERVICES_DIR = pathlib.Path(__file__).resolve().parents[2]

# Every service ships its own copy of the module (they share no package); only
# the config import differs.
_COPIES = {
    "auth/auth_service/services/self_monitoring.py": "import auth_service.config as config",
    "ingestion/ingestion_service/services/self_monitoring.py": (
        "import ingestion_service.config as config"
    ),
    "query/query_service/services/self_monitoring.py": "import query_service.config as config",
    "analytics/analytics_workers/services/self_monitoring.py": (
        "import analytics_workers.config as config"
    ),
}


class _FakeClient:
    def __init__(self):
        self.increments: list[tuple] = []
        self.histograms: list[tuple] = []

    def metric_increment(self, name, value, tags):
        self.increments.append((name, value, tags))

    def metric_histogram(self, name, value, tags):
        self.histograms.append((name, value, tags))


class _FakeContext:
    def __init__(self, code=None):
        self._code = code

    def code(self):
        return self._code


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(self_monitoring, "_client", client)
    return client


class TestDisabled:
    def test_start_without_api_key_never_imports_the_sdk(self, monkeypatch):
        monkeypatch.setattr(self_monitoring.config.settings, "SELF_MONITORING_API_KEY", "")
        monkeypatch.setattr(self_monitoring, "_client", None)
        # A None entry makes `import ledger` raise ImportError.
        monkeypatch.setitem(sys.modules, "ledger", None)

        assert self_monitoring.start("gateway") is None
        assert self_monitoring.client() is None
        assert self_monitoring.rpc_interceptors("gateway") == []

    def test_helpers_are_no_ops(self, monkeypatch):
        monkeypatch.setattr(self_monitoring, "_client", None)

        self_monitoring.increment("ledger.otlp.items", 5, {"signal": "logs"})
        self_monitoring.record("ledger.storage.batch_ms", 12.5)
        self_monitoring.stop()


class _CapturingHandler(logging.Handler):
    """Stands in for the OpenTelemetry handler instrument_logging() installs."""

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


_CapturingHandler.__module__ = "opentelemetry.instrumentation.logging.handler"


class _ConsoleHandler(_CapturingHandler):
    pass


_ConsoleHandler.__module__ = "logging"


class TestForwardedLogs:
    @pytest.fixture
    def root(self):
        root = logging.Logger("test-root", level=logging.INFO)
        self.otel_handler = _CapturingHandler()
        self.console_handler = _ConsoleHandler()
        root.addHandler(self.otel_handler)
        root.addHandler(self.console_handler)
        self_monitoring._forward_warnings_and_up(root)
        return root

    def _emit(self, root, logger_name, level):
        root.handle(root.makeRecord(logger_name, level, __file__, 1, "message", (), None))

    def test_info_stays_in_the_container_log(self, root):
        self._emit(root, "gateway_service.main", logging.INFO)

        assert self.otel_handler.records == []
        assert len(self.console_handler.records) == 1

    def test_warning_and_up_is_forwarded(self, root):
        self._emit(root, "gateway_service.main", logging.WARNING)
        self._emit(root, "auth_service.main", logging.ERROR)

        assert [r.levelno for r in self.otel_handler.records] == [logging.WARNING, logging.ERROR]

    @pytest.mark.parametrize(
        "logger_name",
        [
            "gateway_service.routes.otlp_routes",
            "opentelemetry.exporter.otlp.proto.http._log_exporter",
            "urllib3.connectionpool",
        ],
    )
    def test_export_path_loggers_are_never_forwarded(self, root, logger_name):
        self._emit(root, logger_name, logging.ERROR)

        assert self.otel_handler.records == []
        assert len(self.console_handler.records) == 1

    def test_root_level_is_left_alone(self, root):
        assert root.level == logging.INFO


class TestRpcTiming:
    async def _wrapped(self, behavior):
        (interceptor,) = self_monitoring.rpc_interceptors("query")

        async def continuation(_details):
            return grpc.unary_unary_rpc_method_handler(behavior)

        class Details:
            method = "/query.QueryService/QueryLogs"

        return await interceptor.intercept_service(continuation, Details())

    async def test_successful_call_is_timed_as_ok(self, fake_client):
        async def behavior(request, context):
            return "response"

        handler = await self._wrapped(behavior)
        assert await handler.unary_unary("request", _FakeContext()) == "response"

        ((name, value, tags),) = fake_client.histograms
        assert name == "ledger.query.rpc_ms"
        assert value >= 0
        assert tags == {"method": "QueryLogs", "outcome": "ok"}

    async def test_status_set_on_context_counts_as_error(self, fake_client):
        async def behavior(request, context):
            return None

        handler = await self._wrapped(behavior)
        await handler.unary_unary("request", _FakeContext(grpc.StatusCode.NOT_FOUND))

        assert fake_client.histograms[0][2] == {"method": "QueryLogs", "outcome": "error"}

    async def test_raising_handler_is_timed_and_reraised(self, fake_client):
        async def behavior(request, context):
            raise RuntimeError("boom")

        handler = await self._wrapped(behavior)
        with pytest.raises(RuntimeError):
            await handler.unary_unary("request", _FakeContext())

        assert fake_client.histograms[0][2]["outcome"] == "error"

    async def test_streaming_handlers_pass_through_untouched(self, fake_client):
        (interceptor,) = self_monitoring.rpc_interceptors("query")

        async def stream(request, context):
            yield "chunk"

        original = grpc.unary_stream_rpc_method_handler(stream)

        async def continuation(_details):
            return original

        class Details:
            method = "/query.QueryService/Tail"

        assert await interceptor.intercept_service(continuation, Details()) is original


class TestServiceCopiesInSync:
    @pytest.mark.parametrize("relative_path", sorted(_COPIES))
    def test_copy_matches_the_gateway_module(self, relative_path):
        copy = _SERVICES_DIR / relative_path
        if not copy.exists():
            pytest.skip(f"{relative_path} not checked out")

        gateway_source = pathlib.Path(self_monitoring.__file__).read_text(encoding="utf-8")
        expected = gateway_source.replace(
            "import gateway_service.config as config", _COPIES[relative_path]
        )
        assert copy.read_text(encoding="utf-8") == expected
