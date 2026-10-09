import datetime
import json

import analytics_workers.database as database
import analytics_workers.jobs.service_edges_1h_rollup as rollup_job
import pytest
import sqlalchemy as sa

_SERVER, _CLIENT, _INTERNAL = 0, 1, 2

_INSERT_SPAN = sa.text("""
    INSERT INTO spans (span_id, trace_id, parent_span_id, project_id, service_name, name,
                       kind, start_time, duration_ns, status_code, attributes)
    VALUES (:span_id, :trace_id, :parent, 1, :service, 'op', :kind, :start, :duration_ns,
            :status_code, CAST(:attributes AS jsonb))
""")


async def _span(
    span_id: str,
    service: str,
    start: datetime.datetime,
    *,
    parent: str | None = None,
    kind: int = _SERVER,
    duration_ms: int = 10,
    error: bool = False,
    attributes: dict | None = None,
) -> None:
    async with database.get_logs_session() as session:
        await session.execute(
            _INSERT_SPAN,
            {
                "span_id": span_id.ljust(16, "0"),
                "trace_id": "a" * 32,
                "parent": parent.ljust(16, "0") if parent else None,
                "service": service,
                "kind": kind,
                "start": start,
                "duration_ns": duration_ms * 1_000_000,
                "status_code": 2 if error else 0,
                "attributes": json.dumps(attributes or {}),
            },
        )
        await session.commit()


async def _rollup_rows() -> dict[tuple[str, str], tuple[int, int]]:
    async with database.get_logs_session() as session:
        rows = (
            await session.execute(
                sa.text("SELECT caller, callee, calls, errors FROM service_edges_1h")
            )
        ).all()
    return {(row.caller, row.callee): (row.calls, row.errors) for row in rows}


@pytest.mark.asyncio
class TestServiceEdgesRollup:
    async def test_builds_entry_rows_cross_service_edges_and_dependency_edges(self, test_dbs):
        start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)
        await _span("1", "web", start)
        await _span("2", "web", start, parent="1", kind=_CLIENT)
        await _span("3", "api", start, parent="2", error=True)
        await _span("4", "api", start, parent="3", kind=_CLIENT, attributes={"db.system": "redis"})
        await _span("5", "api", start, parent="3", kind=_INTERNAL)

        await rollup_job.rollup_service_edges_1h()

        assert await _rollup_rows() == {
            ("", "web"): (1, 0),
            ("", "api"): (1, 1),
            ("web", "api"): (1, 1),
            ("api", "redis"): (1, 0),
        }

    async def test_rerun_recomputes_the_open_hour_instead_of_adding_to_it(self, test_dbs):
        start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)
        await _span("1", "web", start)

        await rollup_job.rollup_service_edges_1h()
        await rollup_job.rollup_service_edges_1h()

        assert await _rollup_rows() == {("", "web"): (1, 0)}
