import migration_service.databases as databases
import migration_service.versions as versions
import pytest


class TestSchemaVersions:
    def test_every_version_declares_every_database(self):
        for version, revisions in versions.SCHEMA_VERSIONS.items():
            assert set(revisions) == set(databases.KEYS), (
                f"schema version {version} does not cover every database"
            )

    def test_versions_are_consecutive_from_one(self):
        assert sorted(versions.SCHEMA_VERSIONS) == list(range(1, versions.LATEST_VERSION + 1))

    def test_version_one_is_the_pre_split_schema(self):
        assert versions.SCHEMA_VERSIONS[1] == {"auth": "b8c9d0e1f2a3", "logs": "016"}


class TestRevisionFor:
    def test_returns_declared_revision(self):
        assert versions.revision_for(1, "logs") == "016"

    def test_unknown_version_raises(self):
        with pytest.raises(KeyError):
            versions.revision_for(999, "auth")

    def test_unknown_database_raises(self):
        with pytest.raises(KeyError):
            versions.revision_for(1, "nope")


class TestVersionOf:
    def test_matches_declared_head(self):
        assert versions.version_of("logs", "016") == 1

    def test_unchanged_head_resolves_to_the_latest_version_that_declares_it(self):
        # auth's head has not moved since version 1; version_of reports the newest
        # schema version that still carries it, which is what schema_version_label wants.
        assert versions.version_of("auth", "b8c9d0e1f2a3") == versions.LATEST_VERSION

    def test_other_revision_is_unversioned(self):
        assert versions.version_of("auth", "a2dd1ac4850d") is None

    def test_empty_database_is_unversioned(self):
        assert versions.version_of("auth", None) is None
