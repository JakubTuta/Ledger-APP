import dataclasses
import pathlib

import migration_service.config as config

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent
ALEMBIC_ROOT = PACKAGE_ROOT / "alembic"


@dataclasses.dataclass(frozen=True)
class DatabaseTarget:
    """A physical database this service owns the schema history of."""

    key: str
    description: str
    url_setting: str
    models_module: str

    @property
    def url(self) -> str:
        return getattr(config.settings, self.url_setting)

    @property
    def script_location(self) -> pathlib.Path:
        return ALEMBIC_ROOT / self.key

    @property
    def versions_location(self) -> pathlib.Path:
        return self.script_location / "versions"


TARGETS: tuple[DatabaseTarget, ...] = (
    DatabaseTarget(
        key="auth",
        description="Auth DB (accounts, projects, API keys, alerts, monitors)",
        url_setting="AUTH_DATABASE_URL",
        models_module="ledger_common.models.auth",
    ),
    # The rollup tables exist in migrations alone (analytics reads and writes them with raw SQL),
    # so autogenerate against the logs DB reports them as dropped. Review before applying.
    DatabaseTarget(
        key="logs",
        description="Logs DB (logs, spans, metric points, rollups, error groups)",
        url_setting="LOGS_DATABASE_URL",
        models_module="ledger_common.models.logs",
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
