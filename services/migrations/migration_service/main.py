import argparse
import logging
import sys

import migration_service.config as config
import migration_service.databases as databases
import migration_service.runner as runner
import migration_service.versions as versions

logger = logging.getLogger("migration_service")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_logging()

    try:
        return args.handler(args)
    except (runner.MigrationError, KeyError) as error:
        logger.error("%s", error)
        return 1


def run_upgrade(args: argparse.Namespace) -> int:
    """Bring every selected database up to a schema version (default: latest)."""
    targets = _selected_targets(args)

    for target in targets:
        runner.wait_until_ready(target)
        revision = _target_revision(target, args.version, args.revision)
        before = runner.current_revision(target)

        if not runner.pending_revisions(target) and revision == "head":
            logger.info(
                "[%s] already at %s (schema version %s)", target.key, before, _label(target, before)
            )
            continue

        runner.upgrade(target, revision)
        after = runner.current_revision(target)
        logger.info(
            "[%s] %s -> %s (schema version %s)",
            target.key,
            before or "empty",
            after,
            _label(target, after),
        )

    return 0


def run_downgrade(args: argparse.Namespace) -> int:
    """Roll a database back to a schema version or an explicit revision."""
    targets = _selected_targets(args)

    for target in targets:
        runner.wait_until_ready(target)
        revision = _target_revision(target, args.version, args.revision)
        runner.downgrade(target, revision)
        logger.info(
            "[%s] now at %s",
            target.key,
            runner.current_revision(target) or "empty",
        )

    return 0


def run_status(args: argparse.Namespace) -> int:
    """Report current revision, head, pending count and schema version per database."""
    targets = databases.resolve_targets(args.database)

    print(f"Latest declared schema version: {versions.LATEST_VERSION}")
    for target in targets:
        runner.wait_until_ready(target)
        current = runner.current_revision(target)
        pending = runner.pending_revisions(target)
        print(
            f"  {target.key:<6} version={_label(target, current):<8} "
            f"current={current or 'empty':<14} head={runner.head_revision(target) or 'none':<14} "
            f"pending={len(pending)}"
        )
        for revision in pending:
            print(f"           pending: {revision}")

    return 0


def run_history(args: argparse.Namespace) -> int:
    for target in databases.resolve_targets(args.database):
        print(f"=== {target.key}: {target.description} ===")
        runner.history(target)

    return 0


def run_revision(args: argparse.Namespace) -> int:
    """Create a new revision file for one database."""
    target = databases.get_target(args.database)
    runner.create_revision(target, message=args.message, autogenerate=args.autogenerate)
    return 0


def run_stamp(args: argparse.Namespace) -> int:
    """Record a revision as applied without running it."""
    target = databases.get_target(args.database)
    revision = _target_revision(target, args.version, args.revision)
    runner.wait_until_ready(target)
    runner.stamp(target, revision)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migration_service",
        description="Manage the schema version of every Ledger database.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    upgrade = subparsers.add_parser("upgrade", help="Apply pending migrations")
    _add_database_option(upgrade)
    _add_revision_options(upgrade)
    upgrade.set_defaults(handler=run_upgrade)

    downgrade = subparsers.add_parser("downgrade", help="Roll back migrations")
    _add_database_option(downgrade)
    _add_revision_options(downgrade, required=True)
    downgrade.set_defaults(handler=run_downgrade)

    status = subparsers.add_parser("status", help="Show schema version per database")
    _add_database_option(status)
    status.set_defaults(handler=run_status)

    history = subparsers.add_parser("history", help="Show revision history")
    _add_database_option(history)
    history.set_defaults(handler=run_history)

    revision = subparsers.add_parser("revision", help="Create a new revision file")
    revision.add_argument("--database", required=True, choices=databases.KEYS)
    revision.add_argument("-m", "--message", required=True, help="Revision description")
    revision.add_argument(
        "--no-autogenerate",
        dest="autogenerate",
        action="store_false",
        help="Write an empty revision instead of diffing models against the database",
    )
    revision.set_defaults(handler=run_revision, autogenerate=True)

    stamp = subparsers.add_parser(
        "stamp",
        help="Record a revision as applied without running it",
    )
    stamp.add_argument("--database", required=True, choices=databases.KEYS)
    _add_revision_options(stamp, required=True)
    stamp.set_defaults(handler=run_stamp)

    return parser


def _add_database_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--database",
        action="append",
        choices=databases.KEYS,
        help="Database to act on (repeatable, default: all)",
    )


def _add_revision_options(parser: argparse.ArgumentParser, required: bool = False) -> None:
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument(
        "--version",
        type=int,
        help=f"Schema version to move to (declared versions: 1..{versions.LATEST_VERSION})",
    )
    group.add_argument(
        "--revision",
        help="Explicit alembic revision (single database only)",
    )


def _selected_targets(args: argparse.Namespace) -> list[databases.DatabaseTarget]:
    targets = databases.resolve_targets(args.database)
    if args.revision is not None and len(targets) > 1:
        raise runner.MigrationError(
            "--revision names a revision of one database; pass --database, or use --version"
        )
    return targets


def _target_revision(
    target: databases.DatabaseTarget,
    version: int | None,
    revision: str | None,
) -> str:
    if revision is not None:
        return revision
    if version is not None:
        return versions.revision_for(version, target.key)
    return "head"


def _label(target: databases.DatabaseTarget, revision: str | None) -> str:
    return runner.schema_version_label(target, revision)


def _configure_logging() -> None:
    logging.basicConfig(
        level=config.settings.LOG_LEVEL,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    # Alembic reports each revision it applies at INFO; that output is the
    # point of this service's logs, so it is never quieter than the root level.
    logging.getLogger("alembic").setLevel(logging.INFO)


if __name__ == "__main__":
    sys.exit(main())
