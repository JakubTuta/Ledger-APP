import asyncio
import importlib
import logging
import pathlib
import sys
import time

import alembic.command
import alembic.config
import alembic.script
import migration_service.config as config
import migration_service.databases as databases
import migration_service.versions as versions
import pydantic
import sqlalchemy
import sqlalchemy.exc
import sqlalchemy.ext.asyncio as sqlalchemy_asyncio
from alembic.runtime import migration
from sqlalchemy import pool

logger = logging.getLogger(__name__)

ALEMBIC_INI = pathlib.Path(__file__).resolve().parent.parent / "alembic.ini"


class MigrationError(RuntimeError):
    """A migration could not be planned or applied."""


def build_config(target: databases.DatabaseTarget) -> alembic.config.Config:
    """Alembic config pointed at one database's script directory."""
    alembic_config = alembic.config.Config(str(ALEMBIC_INI))
    alembic_config.set_main_option("script_location", str(target.script_location))
    alembic_config.set_main_option("sqlalchemy.url", target.url)
    alembic_config.set_main_option("database_key", target.key)
    return alembic_config


def script_directory(target: databases.DatabaseTarget) -> alembic.script.ScriptDirectory:
    return alembic.script.ScriptDirectory.from_config(build_config(target))


def head_revision(target: databases.DatabaseTarget) -> str | None:
    return script_directory(target).get_current_head()


def current_heads(target: databases.DatabaseTarget) -> tuple[str, ...]:
    """Revisions recorded in the database's alembic_version table."""
    return asyncio.run(_fetch_current_heads(target))


def current_revision(target: databases.DatabaseTarget) -> str | None:
    heads = current_heads(target)
    return ", ".join(heads) if heads else None


def pending_revisions(target: databases.DatabaseTarget) -> list[str]:
    """Revisions between the database's current revision and the script head."""
    script = script_directory(target)
    head = script.get_current_head()
    if head is None:
        return []

    heads = current_heads(target)
    lower = heads[0] if heads else "base"
    revisions = script.iterate_revisions(head, lower)
    return [revision.revision for revision in reversed(list(revisions))]


def schema_version_label(target: databases.DatabaseTarget, revision: str | None) -> str:
    """Schema version of `revision`.

    "1" sits exactly on a declared version, "1+2" is two unreleased revisions
    past it, "pre-1" is a database older than the first declared version.
    """
    if revision is None:
        return "uninitialized"

    exact = versions.version_of(target.key, revision)
    if exact is not None:
        return str(exact)

    script = script_directory(target)
    for distance, script_revision in enumerate(script.iterate_revisions(revision, "base")):
        base = versions.version_of(target.key, script_revision.revision)
        if base is not None:
            return f"{base}+{distance}"

    return f"pre-{min(versions.SCHEMA_VERSIONS)}"


def wait_until_ready(target: databases.DatabaseTarget) -> None:
    """Block until the database accepts connections or the timeout expires."""
    asyncio.run(_wait_until_ready(target))


def upgrade(target: databases.DatabaseTarget, revision: str = "head") -> None:
    logger.info("[%s] upgrading to %s", target.key, revision)
    alembic.command.upgrade(build_config(target), revision)


def downgrade(target: databases.DatabaseTarget, revision: str) -> None:
    logger.info("[%s] downgrading to %s", target.key, revision)
    alembic.command.downgrade(build_config(target), revision)


def stamp(target: databases.DatabaseTarget, revision: str) -> None:
    logger.info("[%s] stamping alembic_version as %s", target.key, revision)
    alembic.command.stamp(build_config(target), revision)


def history(target: databases.DatabaseTarget) -> None:
    alembic.command.history(build_config(target), indicate_current=True)


def create_revision(
    target: databases.DatabaseTarget,
    message: str,
    autogenerate: bool,
) -> None:
    """Write a new revision file into the target's versions directory."""
    if autogenerate and load_metadata(target) is None:
        raise MigrationError(
            f"Cannot autogenerate for '{target.key}': {target.models_module} is not importable. "
            f"Autogenerate needs {target.owner_service} checked out next to this service "
            f"(it is not shipped in the image) - or use --no-autogenerate and write the "
            f"revision by hand."
        )

    alembic.command.revision(
        build_config(target),
        message=message,
        autogenerate=autogenerate,
    )


def load_metadata(target: databases.DatabaseTarget) -> sqlalchemy.MetaData | None:
    """Owning service's `Base.metadata`, or None when its code is not available.

    Only autogenerate needs it - `upgrade`/`downgrade` replay revision scripts
    and run fine without the models, which is what the container does.
    """
    models_path = str(target.models_path)
    if models_path not in sys.path and target.models_path.is_dir():
        sys.path.insert(0, models_path)

    try:
        importlib.import_module(target.models_module)
        metadata_module = importlib.import_module(target.metadata_module)
    except (ImportError, pydantic.ValidationError):
        logger.debug("[%s] models not importable, autogenerate unavailable", target.key)
        return None

    return metadata_module.Base.metadata


async def _fetch_current_heads(target: databases.DatabaseTarget) -> tuple[str, ...]:
    engine = sqlalchemy_asyncio.create_async_engine(target.url, poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(_read_heads)
    finally:
        await engine.dispose()


def _read_heads(connection: sqlalchemy.Connection) -> tuple[str, ...]:
    return migration.MigrationContext.configure(connection).get_current_heads()


async def _wait_until_ready(target: databases.DatabaseTarget) -> None:
    deadline = time.monotonic() + config.settings.DB_CONNECT_TIMEOUT_SECONDS
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        engine = sqlalchemy_asyncio.create_async_engine(target.url, poolclass=pool.NullPool)
        try:
            async with engine.connect() as connection:
                await connection.execute(sqlalchemy.text("SELECT 1"))
            return
        except (sqlalchemy.exc.SQLAlchemyError, OSError) as error:
            last_error = error
            logger.info("[%s] database not ready yet, retrying", target.key)
        finally:
            await engine.dispose()

        await asyncio.sleep(config.settings.DB_CONNECT_RETRY_INTERVAL_SECONDS)

    raise MigrationError(
        f"Database '{target.key}' did not become reachable within "
        f"{config.settings.DB_CONNECT_TIMEOUT_SECONDS}s: {last_error}"
    )
