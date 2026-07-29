"""drop redundant auth-db indexes and dead schema

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-29 10:00:00.000000

Three sources of duplication had accumulated:

1. `mapped_column(..., primary_key=True, index=True)` in models.py. The primary
   key already has a unique index, so every `ix_<table>_id` is a second full
   copy of it that is never chosen by the planner.
2. `mapped_column(..., unique=True, index=True)` plus a hand-written
   `Index("idx_...")` on the same column - three indexes where one suffices.
   The unique index is kept (it enforces the constraint) and the two plain
   copies are dropped.
3. Single-column indexes that are a strict leading prefix of an existing
   composite index (project_members.project_id, notifications.user_id,
   monitor_checks.monitor_id, daily_usage.project_id, ...). Postgres can use
   the composite for any prefix, so the narrow copy is pure write and vacuum
   cost.

Also dropped:
  feature_flags
      Feature flags were removed from the product (the gateway service module
      is an empty stub); nothing reads or writes the table.
  daily_usage.logs_queried / daily_usage.storage_bytes
      Never incremented - the usage stats job writes literal 0 into both and no
      reader exists.
  idx_accounts_notification_prefs / idx_user_dashboards_panels
      GIN indexes over JSONB columns that are only ever fetched whole by
      account/user id; no query uses a GIN-indexable operator on either.
"""

from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None

# Redundant duplicates of a primary key's own index.
_PK_DUPLICATE_INDEXES = (
    "ix_accounts_id",
    "ix_projects_id",
    "ix_api_keys_id",
    "ix_daily_usage_id",
    "ix_user_dashboards_id",
    "ix_refresh_tokens_id",
    "ix_project_members_id",
    "ix_project_invite_codes_id",
    "ix_notifications_id",
    "ix_alert_rules_id",
    "ix_connectors_id",
    "ix_alert_events_id",
    "ix_maintenance_windows_id",
    "ix_monitors_id",
    "ix_monitor_checks_id",
    "ix_notification_preferences_id",
)

# Duplicates of a unique index on the same single column.
_UNIQUE_DUPLICATE_INDEXES = (
    "idx_accounts_email",
    "idx_projects_slug",
    "idx_api_keys_key_hash",
    "idx_refresh_tokens_token_hash",
    "idx_user_dashboards_user_id",
    "ix_user_dashboards_user_id",
)

# Single-column indexes fully covered by the leading prefix of a composite one.
_PREFIX_COVERED_INDEXES = (
    "ix_projects_account_id",
    "ix_api_keys_project_id",
    "ix_daily_usage_project_id",
    "idx_daily_usage_project_date",
    "ix_project_members_project_id",
    "idx_project_members_project_id",
    "ix_project_members_account_id",
    "ix_notifications_user_id",
    "ix_alert_rules_project_id",
    "ix_alert_events_project_id",
    "ix_alert_events_fired_at",
    "ix_monitor_checks_monitor_id",
    "ix_monitor_checks_checked_at",
    "ix_notification_preferences_user_id",
    "ix_notification_preferences_project_id",
    "ix_notification_preferences_rule_id",
)

_DEAD_GIN_INDEXES = (
    "idx_accounts_notification_prefs",
    "idx_user_dashboards_panels",
)


def upgrade() -> None:
    for index_name in (
        _PK_DUPLICATE_INDEXES
        + _UNIQUE_DUPLICATE_INDEXES
        + _PREFIX_COVERED_INDEXES
        + _DEAD_GIN_INDEXES
    ):
        op.execute(f"DROP INDEX IF EXISTS {index_name}")

    op.execute("DROP INDEX IF EXISTS idx_feature_flags_project_id")
    op.execute("DROP TABLE IF EXISTS feature_flags")

    op.execute("ALTER TABLE daily_usage DROP CONSTRAINT IF EXISTS check_logs_queried")
    op.execute("ALTER TABLE daily_usage DROP COLUMN IF EXISTS logs_queried")
    op.execute("ALTER TABLE daily_usage DROP COLUMN IF EXISTS storage_bytes")

    # monitor_checks is append-only (one row per monitor per interval, forever)
    # and nothing prunes it; the analytics retention job now trims it, and this
    # index is what makes that trim an index scan rather than a full scan.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_monitor_checks_checked_at "
        "ON monitor_checks (checked_at)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE daily_usage ADD COLUMN IF NOT EXISTS storage_bytes BIGINT NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE daily_usage ADD COLUMN IF NOT EXISTS logs_queried BIGINT NOT NULL DEFAULT 0")
    op.execute(
        "ALTER TABLE daily_usage ADD CONSTRAINT check_logs_queried CHECK (logs_queried >= 0)"
    )

    op.create_table(
        "feature_flags",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("key", sa.VARCHAR(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "key", name="uq_feature_flag"),
    )
    op.create_index("idx_feature_flags_project_id", "feature_flags", ["project_id"])

    op.create_index(
        "idx_user_dashboards_panels",
        "user_dashboards",
        ["panels"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_accounts_notification_prefs",
        "accounts",
        ["notification_preferences"],
        postgresql_using="gin",
    )

    op.execute("CREATE INDEX IF NOT EXISTS idx_accounts_email ON accounts (email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_projects_slug ON projects (slug)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys (key_hash)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash "
        "ON refresh_tokens (token_hash)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_dashboards_user_id ON user_dashboards (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_daily_usage_project_date "
        "ON daily_usage (project_id, date DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_members_project_id "
        "ON project_members (project_id)"
    )

    # The `ix_*` copies are intentionally not recreated: they were byproducts of
    # `index=True` on primary-key / already-indexed columns in models.py, which
    # this revision also removes.
