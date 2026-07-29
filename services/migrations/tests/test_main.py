import migration_service.databases as databases
import migration_service.main as main
import migration_service.runner as runner
import pytest


def parse(argv: list[str]):
    return main._build_parser().parse_args(argv)


class TestParser:
    def test_upgrade_defaults_to_every_database_at_head(self):
        args = parse(["upgrade"])
        assert args.handler is main.run_upgrade
        assert args.database is None
        assert args.version is None
        assert args.revision is None

    def test_database_option_is_repeatable(self):
        args = parse(["upgrade", "--database", "auth", "--database", "logs"])
        assert args.database == ["auth", "logs"]

    def test_downgrade_requires_a_destination(self):
        with pytest.raises(SystemExit):
            parse(["downgrade", "--database", "auth"])

    def test_version_and_revision_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            parse(["upgrade", "--version", "1", "--revision", "016"])

    def test_revision_autogenerates_by_default(self):
        args = parse(["revision", "--database", "auth", "-m", "add table"])
        assert args.autogenerate is True
        assert (
            parse(["revision", "--database", "auth", "-m", "x", "--no-autogenerate"]).autogenerate
            is False
        )


class TestTargetRevision:
    def test_explicit_revision_wins(self):
        target = databases.get_target("auth")
        assert main._target_revision(target, version=1, revision="abc") == "abc"

    def test_version_resolves_per_database(self):
        assert (
            main._target_revision(databases.get_target("logs"), version=1, revision=None) == "016"
        )

    def test_default_is_head(self):
        target = databases.get_target("auth")
        assert main._target_revision(target, version=None, revision=None) == "head"


class TestSelectedTargets:
    def test_revision_across_multiple_databases_is_rejected(self):
        args = parse(["upgrade", "--revision", "016"])
        with pytest.raises(runner.MigrationError):
            main._selected_targets(args)

    def test_revision_with_one_database_is_allowed(self):
        args = parse(["upgrade", "--database", "logs", "--revision", "016"])
        assert [target.key for target in main._selected_targets(args)] == ["logs"]
