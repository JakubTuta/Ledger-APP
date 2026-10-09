"""Regression tests for ingestion durability and input-validation fixes."""

import datetime
import json
import unittest.mock

import pytest
import sqlalchemy.exc

import ingestion_service.grpc.servicers as servicers
import ingestion_service.proto.ingestion_pb2 as ingestion_pb2
import ingestion_service.schemas as schemas
import ingestion_service.services.db_errors as db_errors
import ingestion_service.services.enricher as enricher
import ingestion_service.worker as worker_module
from ingestion_service.notifications import publisher as notif_publisher


class _PgError(Exception):
    def __init__(self, sqlstate: str):
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


def _wrapped(exc: Exception) -> sqlalchemy.exc.DBAPIError:
    """How SQLAlchemy surfaces an asyncpg error: DBAPIError -> .orig -> __cause__."""
    adapted = Exception("adapted")
    adapted.__cause__ = exc
    return sqlalchemy.exc.DBAPIError("INSERT ...", {}, adapted)


class TestTransientDatabaseErrors:
    @pytest.mark.parametrize(
        "exc",
        [
            ConnectionRefusedError("refused"),
            TimeoutError(),
            _wrapped(_PgError("53300")),  # too many connections
            _wrapped(_PgError("57P01")),  # admin shutdown
            _wrapped(_PgError("08006")),  # connection failure
            _wrapped(_PgError("40P01")),  # deadlock
            sqlalchemy.exc.TimeoutError("QueuePool limit reached"),
        ],
    )
    def test_availability_problems_are_transient(self, exc):
        assert db_errors.is_transient(exc)

    @pytest.mark.parametrize(
        "exc",
        [
            ValueError("bad payload"),
            _wrapped(_PgError("22001")),  # value too long
            _wrapped(_PgError("23502")),  # not-null violation
        ],
    )
    def test_data_problems_are_not_transient(self, exc):
        assert not db_errors.is_transient(exc)


class _Message:
    def __init__(self):
        self.ack_calls: list[bool] = []
        self.nack_calls: list[bool] = []

    async def ack(self, multiple: bool = False) -> None:
        self.ack_calls.append(multiple)

    async def nack(self, requeue: bool = True) -> None:
        self.nack_calls.append(requeue)


@pytest.mark.asyncio
class TestWorkerWaitsOutDatabaseOutages:
    async def test_batch_is_retried_until_the_database_is_back(self, monkeypatch):
        monkeypatch.setattr(worker_module, "_DB_RETRY_INITIAL_DELAY_SECONDS", 0)
        worker = worker_module.StorageWorker(worker_id=1)
        worker.running = True
        messages = [_Message(), _Message()]
        process = unittest.mock.AsyncMock(
            side_effect=[ConnectionRefusedError(), _wrapped(_PgError("53300")), None]
        )

        with unittest.mock.patch.object(worker, "process_logs_batch", new=process):
            await worker._flush_batch(messages, [[{"id": 1}], [{"id": 2}]])

        assert process.await_count == 3
        assert messages[1].ack_calls == [True]
        assert all(m.nack_calls == [] for m in messages)
        assert worker.failed_count == 0

    async def test_shutdown_during_outage_requeues_instead_of_dropping(self, monkeypatch):
        monkeypatch.setattr(worker_module, "_DB_RETRY_INITIAL_DELAY_SECONDS", 0)
        worker = worker_module.StorageWorker(worker_id=1)
        worker.running = False
        messages = [_Message(), _Message()]
        process = unittest.mock.AsyncMock(side_effect=ConnectionRefusedError())

        with unittest.mock.patch.object(worker, "process_logs_batch", new=process):
            await worker._flush_batch(messages, [[{"id": 1}], [{"id": 2}]])

        assert [m.nack_calls for m in messages] == [[True], [True]]
        assert worker.failed_count == 0


class TestTimestampWindow:
    def test_logs_older_than_the_window_are_rejected(self):
        old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=45)

        with pytest.raises(ValueError, match="in the past"):
            schemas.LogEntry(timestamp=old, level="info")

    def test_recent_logs_are_accepted(self):
        recent = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)

        assert schemas.LogEntry(timestamp=recent, level="info").timestamp == recent


def _span(**overrides) -> ingestion_pb2.Span:
    now_ns = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1e9)
    fields = {
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "name": "GET /x",
        "service_name": "svc",
        "start_unix_nano": now_ns,
        "end_unix_nano": now_ns + 1_000_000,
    }
    fields.update(overrides)
    return ingestion_pb2.Span(**fields)


@pytest.mark.asyncio
class TestSpanValidation:
    async def _ingest(self, *spans: ingestion_pb2.Span) -> tuple[int, int, list]:
        enqueued: list = []

        async def capture(project_id, rows, resources=None):
            enqueued.extend(rows)

        with unittest.mock.patch.object(
            servicers.queue_service, "enqueue_spans_envelope", side_effect=capture
        ):
            response = await servicers.IngestionServicer().IngestSpansBatch(
                ingestion_pb2.IngestSpansBatchRequest(project_id=1, spans=list(spans)),
                unittest.mock.AsyncMock(),
            )
        return response.accepted, response.rejected, enqueued

    async def test_oversized_parent_span_id_is_rejected(self):
        accepted, rejected, _ = await self._ingest(_span(), _span(parent_span_id="c" * 32))

        assert (accepted, rejected) == (1, 1)

    async def test_negative_duration_is_rejected(self):
        now_ns = _span().start_unix_nano
        accepted, rejected, _ = await self._ingest(_span(end_unix_nano=now_ns - 1))

        assert (accepted, rejected) == (0, 1)

    async def test_span_far_in_the_past_is_rejected(self):
        a_year_ago_ns = _span().start_unix_nano - 365 * 24 * 3600 * 10**9
        accepted, rejected, _ = await self._ingest(
            _span(start_unix_nano=a_year_ago_ns, end_unix_nano=a_year_ago_ns + 1)
        )

        assert (accepted, rejected) == (0, 1)


def _python_traceback(innermost_file: str) -> str:
    return (
        "Traceback (most recent call last):\n"
        '  File "/venv/starlette/routing.py", line 74, in app\n'
        '  File "/venv/fastapi/routing.py", line 301, in run_endpoint\n'
        '  File "/venv/fastapi/routing.py", line 212, in call\n'
        f'  File "/app/{innermost_file}", line 10, in handler\n'
        "KeyError: 'x'\n"
    )


class TestErrorFingerprint:
    def _fingerprint(self, stack_trace: str) -> str | None:
        entry = schemas.LogEntry(
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            level="error",
            log_type="exception",
            error_type="KeyError",
            error_message="'x'",
            stack_trace=stack_trace,
            platform="python",
        )
        return enricher.generate_error_fingerprint(entry)

    def test_errors_raised_in_different_places_get_different_groups(self):
        assert self._fingerprint(_python_traceback("orders.py")) != self._fingerprint(
            _python_traceback("billing.py")
        )

    def test_same_origin_gets_the_same_group(self):
        assert self._fingerprint(_python_traceback("orders.py")) == self._fingerprint(
            _python_traceback("orders.py")
        )


@pytest.mark.asyncio
class TestErrorNotificationBudget:
    async def test_error_storm_publishes_at_most_the_per_second_budget(self):
        pipeline = unittest.mock.MagicMock()
        pipeline.execute = unittest.mock.AsyncMock()
        redis_mock = unittest.mock.MagicMock()
        redis_mock.pipeline.return_value = pipeline
        publisher = notif_publisher.NotificationPublisher(redis_mock, enabled=True)
        notifications = [
            notif_publisher.ErrorNotification(
                project_id=1,
                level="error",
                log_type="logger",
                message=f"boom {i}",
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            for i in range(1000)
        ]

        with unittest.mock.patch.object(notif_publisher.time, "time", return_value=1_000.0):
            await publisher.publish_error_notifications(1, notifications)
            await publisher.publish_error_notifications(1, notifications)

        budget = notif_publisher.NotificationPublisher.MAX_NOTIFICATIONS_PER_PROJECT_PER_SECOND
        assert pipeline.publish.call_count == budget
        first = json.loads(pipeline.publish.call_args_list[0].args[1])
        assert first["message"] == "boom 0"
