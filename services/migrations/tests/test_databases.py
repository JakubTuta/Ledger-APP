import migration_service.databases as databases
import pytest


class TestTargets:
    def test_keys_are_unique(self):
        assert len(set(databases.KEYS)) == len(databases.KEYS)

    def test_every_target_has_a_script_directory(self):
        for target in databases.TARGETS:
            assert (target.script_location / "env.py").is_file()
            assert (target.script_location / "script.py.mako").is_file()
            assert target.versions_location.is_dir()

    def test_every_target_has_revision_files(self):
        for target in databases.TARGETS:
            assert list(target.versions_location.glob("*.py"))

    def test_urls_come_from_settings(self):
        auth = databases.get_target("auth")
        assert auth.url.startswith("postgresql+asyncpg://")


class TestResolveTargets:
    def test_none_selects_every_database(self):
        assert databases.resolve_targets(None) == list(databases.TARGETS)

    def test_explicit_keys_preserve_order(self):
        resolved = databases.resolve_targets(["logs", "auth"])
        assert [target.key for target in resolved] == ["logs", "auth"]

    def test_unknown_key_raises(self):
        with pytest.raises(KeyError):
            databases.resolve_targets(["nope"])
