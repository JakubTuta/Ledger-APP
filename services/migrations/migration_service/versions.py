"""Product-level schema versions.

Alembic revisions are per-database and opaque; a schema version is the one
number that describes the whole platform's database state. Version 1 is the
schema as it stood when migrations moved into this service - every revision
that shipped from `services/auth` and `services/ingestion` up to and including
the heads below.

Cutting a new version: add the next integer with the head revision of every
database at that point. Revisions added after the newest entry are unreleased
and report as "1+3" style (base version plus pending revisions).
"""

SCHEMA_VERSIONS: dict[int, dict[str, str]] = {
    1: {
        "auth": "b8c9d0e1f2a3",
        "logs": "016",
    },
    2: {
        "auth": "b8c9d0e1f2a3",
        "logs": "017",
    },
    3: {
        "auth": "b8c9d0e1f2a3",
        "logs": "018",
    },
    4: {
        "auth": "b8c9d0e1f2a3",
        "logs": "022",
    },
}

LATEST_VERSION: int = max(SCHEMA_VERSIONS)


def revision_for(version: int, key: str) -> str:
    """Head revision of database `key` at schema version `version`."""
    if version not in SCHEMA_VERSIONS:
        known = ", ".join(str(v) for v in sorted(SCHEMA_VERSIONS))
        raise KeyError(f"Unknown schema version {version}. Known versions: {known}")

    revisions = SCHEMA_VERSIONS[version]
    if key not in revisions:
        raise KeyError(f"Schema version {version} declares no revision for database '{key}'")

    return revisions[key]


def version_of(key: str, revision: str | None) -> int | None:
    """Schema version whose `key` head is exactly `revision`, if any."""
    if revision is None:
        return None

    for version in sorted(SCHEMA_VERSIONS, reverse=True):
        if SCHEMA_VERSIONS[version].get(key) == revision:
            return version

    return None
