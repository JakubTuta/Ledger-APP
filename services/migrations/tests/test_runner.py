import migration_service.databases as databases
import migration_service.runner as runner
import migration_service.versions as versions


class TestScriptDirectories:
    def test_every_revision_file_loads(self):
        for target in databases.TARGETS:
            script = runner.script_directory(target)
            revisions = list(script.walk_revisions())
            assert len(revisions) == len(list(target.versions_location.glob("*.py")))

    def test_history_is_linear_with_a_single_head(self):
        for target in databases.TARGETS:
            script = runner.script_directory(target)
            assert len(script.get_heads()) == 1, f"{target.key} has branched history"
            assert len(script.get_bases()) == 1, f"{target.key} has more than one base"

    def test_head_matches_the_latest_declared_version(self):
        for target in databases.TARGETS:
            expected = versions.revision_for(versions.LATEST_VERSION, target.key)
            assert runner.head_revision(target) == expected


class TestSchemaVersionLabel:
    def test_declared_head_reports_its_version(self):
        target = databases.get_target("logs")
        assert runner.schema_version_label(target, "016") == "1"

    def test_empty_database_is_uninitialized(self):
        target = databases.get_target("logs")
        assert runner.schema_version_label(target, None) == "uninitialized"

    def test_revision_below_version_one_is_reported_as_pre_1(self):
        target = databases.get_target("logs")
        assert runner.schema_version_label(target, "010") == "pre-1"


class TestBuildConfig:
    def test_points_alembic_at_the_target_scripts(self):
        target = databases.get_target("auth")
        config = runner.build_config(target)
        assert config.get_main_option("script_location") == str(target.script_location)
        assert config.get_main_option("database_key") == "auth"
