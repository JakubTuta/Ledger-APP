import asyncio

import sqlalchemy.exc

# SQLSTATE prefixes for failures that say nothing about the rows being written:
# connection exceptions (08), insufficient resources such as "too many
# clients" (53), operator intervention such as shutdown or "starting up" (57P),
# and serialization/deadlock aborts (40001, 40P01). Retrying the same batch
# later succeeds once the database is back.
_TRANSIENT_SQLSTATE_PREFIXES = ("08", "53", "57P", "40001", "40P01")

_MAX_CHAIN_DEPTH = 8


def is_transient(exc: BaseException) -> bool:
    """Whether `exc` (or anything it wraps) is a database availability problem.

    The storage worker drops a batch that fails twice; that is right for bad
    data, but turned every database restart or connection-limit spike into
    silent data loss.
    """
    seen = 0
    current: BaseException | None = exc
    while current is not None and seen < _MAX_CHAIN_DEPTH:
        if isinstance(current, (OSError, asyncio.TimeoutError, sqlalchemy.exc.TimeoutError)):
            return True
        if isinstance(current, sqlalchemy.exc.DBAPIError) and current.connection_invalidated:
            return True
        sqlstate = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        if isinstance(sqlstate, str) and sqlstate.startswith(_TRANSIENT_SQLSTATE_PREFIXES):
            return True
        if type(current).__name__ in ("ConnectionDoesNotExistError", "InterfaceError"):
            # asyncpg's "connection was closed in the middle of operation".
            return True
        current = (
            getattr(current, "orig", None)
            if isinstance(current, sqlalchemy.exc.DBAPIError)
            else current.__cause__ or current.__context__
        )
        seen += 1
    return False
