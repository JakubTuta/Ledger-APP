import dataclasses
import pathlib

import migration_service.config as config

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent
ALEMBIC_ROOT = PACKAGE_ROOT / "alembic"
REPO_ROOT = PACKAGE_ROOT.parent.parent.parent


@dataclasses.dataclass(frozen=True)
class DatabaseTarget:
    """A physical database this service owns the schema history of."""

    key: str
    description: str
    url_setting: str
    owner_service: str
    models_module: str
    metadata_module: str

    @property
    def url(self) -> str:
        return getattr(config.settings, self.url_setting)

    @property
    def script_location(self) -> pathlib.Path:
        return ALEMBIC_ROOT / self.key

    @property
    def versions_location(self) -> pathlib.Path:
        return self.script_location / "versions"

    @property
    def models_path(self) -> pathlib.Path:
        """Repo checkout path holding the ORM models autogenerate diffs against.

        Only present when this service runs from the repo (dev host); the
        container image ships migration scripts, not the owning service's code,
        so autogenerate is a host-only operation.
        """
        return REPO_ROOT / self.owner_service


TARGETS: tuple[DatabaseTarget, ...] = (
    DatabaseTarget(
        key="auth",
        description="Auth DB (accounts, projects, API keys, alerts, monitors)",
        url_setting="AUTH_DATABASE_URL",
        owner_service="services/auth",
        models_module="auth_service.models",
        metadata_module="auth_service.database",
    ),
    # Autogenerate against the logs DB sees ingestion's models only - query owns
    # a second overlapping set and the rollup tables exist in migrations alone,
    # so a diff here reports tables it cannot see as dropped. Review before
    # applying; every revision so far was authored under the same constraint.
    DatabaseTarget(
        key="logs",
        description="Logs DB (logs, spans, metric points, rollups, error groups)",
        url_setting="LOGS_DATABASE_URL",
        owner_service="services/ingestion",
        models_module="ingestion_service.models",
        metadata_module="ingestion_service.database",
    ),
)

KEYS: tuple[str, ...] = tuple(target.key for target in TARGETS)


def get_target(key: str) -> DatabaseTarget:
    for target in TARGETS:
        if target.key == key:
            return target
    raise KeyError(f"Unknown database '{key}'. Known databases: {', '.join(KEYS)}")


def resolve_targets(keys: list[str] | None) -> list[DatabaseTarget]:
    if not keys:
        return list(TARGETS)
    return [get_target(key) for key in keys]
