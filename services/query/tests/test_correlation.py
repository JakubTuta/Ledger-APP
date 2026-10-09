import datetime
import json

import grpc
import pytest
import sqlalchemy as sa

import query_service.database as database
import query_service.models as models
import query_service.proto.query_pb2 as query_pb2
import tests.test_base as test_base

_SERVER, _CLIENT, _INTERNAL = 0, 1, 2
_ERROR = 2
_TRACE = "a" * 32
_OTHER_TRACE = "f" * 32

_INSERT_SPAN = sa.text("""
    INSERT INTO spans (span_id, trace_id, parent_span_id, project_id, service_name, name,
                       kind, start_time, duration_ns, status_code, attributes)
    VALUES (:span_id, :trace_id, :parent_span_id, 1, :service, :name, :kind, :start,
            :duration_ns, :status_code, CAST(:attributes AS jsonb))
""")


class CorrelationFixtures(test_base.BaseQueryTest):
    base = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)

    async def _span(
        self,
        span_id: str,
        service: str,
        *,
        trace_id: str = _TRACE,
        parent: str | None = None,
        kind: int = _SERVER,
        name: str = "GET /orders",
        offset_ms: int = 0,
        duration_ms: float = 10.0,
        error: bool = False,
        attributes: dict | None = None,
    ) -> None:
        async with database.get_logs_session() as session:
            await session.execute(
                _INSERT_SPAN,
                {
                    "span_id": span_id.ljust(16, "0"),
                    "trace_id": trace_id,
                    "parent_span_id": parent.ljust(16, "0") if parent else None,
                    "service": service,
                    "name": name,
                    "kind": kind,
                    "start": self.base + datetime.timedelta(milliseconds=offset_ms),
                    "duration_ns": int(duration_ms * 1_000_000),
                    "status_code": _ERROR if error else 0,
                    "attributes": json.dumps(attributes or {}),
                },
            )
            await session.commit()

    async def _log(self, message: str, offset_ms: int, **fields) -> None:
        async with self.test_db_manager.session_factory() as session:
            session.add(
                models.Log(
                    project_id=1,
                    timestamp=self.base + datetime.timedelta(milliseconds=offset_ms),
                    ingested_at=datetime.datetime.now(datetime.timezone.utc),
                    level="info",
                    log_type="logger",
                    importance="standard",
                    message=message,
                    **fields,
                )
            )
            await session.commit()

    def _window(self) -> dict:
        return {
            "from_time": (self.base - datetime.timedelta(minutes=1)).isoformat(),
            "to_time": (self.base + datetime.timedelta(minutes=1)).isoformat(),
        }


class TestTraceLogs(CorrelationFixtures):
    @pytest.mark.asyncio
    async def test_returns_the_traces_logs_oldest_first(self):
        await self._span("1", "api", duration_ms=50)
        await self._log("second", 20, trace_id=_TRACE, span_id="2".ljust(16, "0"))
        await self._log("first", 5, trace_id=_TRACE, span_id="1".ljust(16, "0"))
        await self._log("legacy row", 30, attributes={"trace_id": _TRACE})
        await self._log("other trace", 10, trace_id=_OTHER_TRACE)

        response = await self.stub.GetTraceLogs(
            query_pb2.GetTraceLogsRequest(project_id=1, trace_id=_TRACE)
        )

        assert [log.message for log in response.logs] == ["first", "second", "legacy row"]
        assert json.loads(response.logs[0].attributes)["trace_id"] == _TRACE
        assert response.truncated is False

    @pytest.mark.asyncio
    async def test_span_filter_narrows_to_one_span(self):
        await self._span("1", "api")
        await self._log("in span 1", 1, trace_id=_TRACE, span_id="1".ljust(16, "0"))
        await self._log("in span 2", 2, trace_id=_TRACE, span_id="2".ljust(16, "0"))

        response = await self.stub.GetTraceLogs(
            query_pb2.GetTraceLogsRequest(project_id=1, trace_id=_TRACE, span_id="1".ljust(16, "0"))
        )

        assert [log.message for log in response.logs] == ["in span 1"]

    @pytest.mark.asyncio
    async def test_limit_reports_truncation(self):
        await self._span("1", "api")
        for i in range(3):
            await self._log(f"log {i}", i, trace_id=_TRACE)

        response = await self.stub.GetTraceLogs(
            query_pb2.GetTraceLogsRequest(project_id=1, trace_id=_TRACE, limit=2)
        )

        assert len(response.logs) == 2
        assert response.truncated is True

    @pytest.mark.asyncio
    async def test_logs_of_a_trace_without_stored_spans_are_still_found(self):
        await self._log("sampled-out trace", 0, trace_id=_TRACE)

        response = await self.stub.GetTraceLogs(
            query_pb2.GetTraceLogsRequest(project_id=1, trace_id=_TRACE)
        )

        assert [log.message for log in response.logs] == ["sampled-out trace"]


class TestServiceMap(CorrelationFixtures):
    @pytest.mark.asyncio
    async def test_edges_follow_parent_spans_across_services_and_into_dependencies(self):
        await self._span("1", "web")
        await self._span("2", "web", parent="1", kind=_CLIENT, name="GET /api/orders")
        await self._span("3", "api", parent="2", error=True)
        await self._span(
            "4", "api", parent="3", kind=_CLIENT, attributes={"db.system": "postgresql"}
        )
        await self._span("5", "api", parent="3", kind=_INTERNAL, name="serialize")

        response = await self.stub.GetServiceMap(
            query_pb2.GetServiceMapRequest(project_id=1, **self._window())
        )

        edges = {(e.caller, e.callee): (e.calls, e.errors) for e in response.edges}
        assert edges == {("web", "api"): (1, 1), ("api", "postgresql"): (1, 0)}
        nodes = {n.service: (n.calls, n.errors) for n in response.nodes}
        assert nodes == {"web": (1, 0), "api": (1, 1), "postgresql": (0, 0)}

    @pytest.mark.asyncio
    async def test_window_wider_than_a_week_is_rejected(self):
        with pytest.raises(grpc.aio.AioRpcError) as error:
            await self.stub.GetServiceMap(
                query_pb2.GetServiceMapRequest(
                    project_id=1,
                    from_time=(self.base - datetime.timedelta(days=8)).isoformat(),
                    to_time=self.base.isoformat(),
                )
            )
        assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT


class TestServiceMapRollup(CorrelationFixtures):
    @pytest.mark.asyncio
    async def test_wide_windows_read_the_hourly_rollup(self):
        hour = self.base.replace(minute=0, second=0, microsecond=0)
        async with database.get_logs_session() as session:
            for bucket_offset, p95_ns in ((0, 20_000_000), (1, 50_000_000)):
                for caller, callee, calls in (("", "api", 10), ("web", "api", 4)):
                    await session.execute(
                        sa.text(
                            "INSERT INTO service_edges_1h (project_id, bucket, caller, callee, "
                            "calls, errors, duration_ns_sum, p95_ns) VALUES "
                            "(1, :bucket, :caller, :callee, :calls, 1, 0, :p95_ns)"
                        ),
                        {
                            "bucket": hour - datetime.timedelta(hours=bucket_offset),
                            "caller": caller,
                            "callee": callee,
                            "calls": calls,
                            "p95_ns": p95_ns,
                        },
                    )
            await session.commit()
        # A raw span the rollup does not contain must not show up.
        await self._span("1", "worker")

        response = await self.stub.GetServiceMap(
            query_pb2.GetServiceMapRequest(
                project_id=1,
                from_time=(self.base - datetime.timedelta(hours=24)).isoformat(),
                to_time=(self.base + datetime.timedelta(minutes=1)).isoformat(),
            )
        )

        assert response.downsampled is True
        assert {(n.service, n.calls, n.errors) for n in response.nodes} == {
            ("api", 20, 2),
            ("web", 0, 0),
        }
        (edge,) = response.edges
        assert (edge.caller, edge.callee, edge.calls, edge.p95_ms) == ("web", "api", 8, 50.0)


class TestServiceRed(CorrelationFixtures):
    @pytest.mark.asyncio
    async def test_service_level_counts_entry_spans_only(self):
        await self._span("1", "api", duration_ms=10)
        await self._span("2", "api", trace_id=_OTHER_TRACE, duration_ms=30, error=True)
        await self._span("3", "api", parent="1", kind=_CLIENT, duration_ms=500)

        response = await self.stub.GetServiceRed(
            query_pb2.GetServiceRedRequest(project_id=1, interval="1h", **self._window())
        )

        (series,) = response.series
        assert (series.service, series.operation) == ("api", "")
        assert (series.calls, series.errors) == (2, 1)
        assert sum(point.calls for point in series.points) == 2
        assert series.p95_ms == pytest.approx(29.0)

    @pytest.mark.asyncio
    async def test_one_service_splits_by_operation(self):
        await self._span("1", "api", name="GET /orders")
        await self._span("2", "api", trace_id=_OTHER_TRACE, name="POST /orders")
        await self._span("3", "web", trace_id="b" * 32, name="GET /")

        response = await self.stub.GetServiceRed(
            query_pb2.GetServiceRedRequest(project_id=1, service="api", **self._window())
        )

        assert sorted(s.operation for s in response.series) == ["GET /orders", "POST /orders"]
