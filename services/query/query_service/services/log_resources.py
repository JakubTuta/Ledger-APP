"""Reassembling a log's attributes from its row and its stored resource.

Since logs revision 024 a row's `attributes` holds only the record's own
attributes; the OTLP resource is stored once in `resources` and trace context
has its own columns. Clients still get the shape they always had: resource
attributes underneath the record's, plus `trace_id` / `span_id`. Rows stored
before that revision already carry all of it in the JSONB and pass through.
"""

import typing

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

import query_service.models as models
import query_service.schemas as schemas


class _LogRow(typing.Protocol):
    attributes: typing.Any
    resource_hash: int | None
    trace_id: str | None
    span_id: str | None


async def fetch_resource_attributes(
    session: AsyncSession, project_id: int, rows: typing.Iterable[_LogRow]
) -> dict[int, dict]:
    """resource_hash -> attributes for the resources `rows` reference (one query)."""
    hashes = {row.resource_hash for row in rows if row.resource_hash is not None}
    if not hashes:
        return {}
    result = await session.execute(
        sa.select(models.resources.c.resource_hash, models.resources.c.attributes).where(
            models.resources.c.project_id == project_id,
            models.resources.c.resource_hash.in_(hashes),
        )
    )
    return {row.resource_hash: row.attributes for row in result}


def client_attributes(row: _LogRow, resources: dict[int, dict]) -> dict | None:
    own = row.attributes if isinstance(row.attributes, dict) else None
    resource = resources.get(row.resource_hash) if row.resource_hash is not None else None
    if resource is None and row.trace_id is None and row.span_id is None:
        return own

    attributes = {**(resource or {}), **(own or {})}
    if row.trace_id:
        attributes["trace_id"] = row.trace_id
    if row.span_id:
        attributes["span_id"] = row.span_id
    return attributes


async def log_responses(
    session: AsyncSession, project_id: int, logs: typing.Sequence[models.Log]
) -> list[schemas.LogResponse]:
    resources = await fetch_resource_attributes(session, project_id, logs)
    return [
        schemas.LogResponse.model_validate(log).model_copy(
            update={"attributes": client_attributes(log, resources)}
        )
        for log in logs
    ]
