import datetime

import auth_service.database as database
from sqlalchemy import (
    CHAR,
    VARCHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Account(database.Base):
    """
    User accounts table.

    Performance notes:
    - CHAR(60) for bcrypt hash (fixed length)
    - Indexed email for fast login
    - Partial index on active accounts
    """

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)

    email: Mapped[str] = mapped_column(
        VARCHAR(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(CHAR(60), nullable=False)
    name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)

    plan: Mapped[str] = mapped_column(VARCHAR(20), default="free", nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(20), default="active", nullable=False)

    notification_preferences: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        server_default='{"enabled": true, "projects": {}}',
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        onupdate=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    projects: Mapped[list["Project"]] = relationship(
        "Project",
        back_populates="account",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_accounts_email", "email"),
        Index("idx_accounts_status", "status", postgresql_where=(status == "active")),
        Index(
            "idx_accounts_notification_prefs",
            "notification_preferences",
            postgresql_using="gin",
        ),
        CheckConstraint(
            "plan IN ('free', 'pro', 'enterprise')",
            name="check_account_plan",
        ),
        CheckConstraint(
            "status IN ('active', 'suspended', 'deleted')",
            name="check_account_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Account(id={self.id}, email={self.email}, plan={self.plan})>"


class RefreshToken(database.Base):
    """
    Refresh tokens table for JWT token refresh.

    Stores refresh tokens with expiration for automatic access token renewal.
    Enables token revocation and logout across devices.

    Performance notes:
    - Indexed token_hash for fast validation
    - Indexed account_id for user logout (revoke all tokens)
    - Partial index on active tokens only
    - Automatic cleanup via expires_at timestamp
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)

    account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token_hash: Mapped[str] = mapped_column(
        CHAR(64), unique=True, nullable=False, index=True
    )

    device_info: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)

    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    revoked: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    last_used_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    account: Mapped["Account"] = relationship("Account", backref="refresh_tokens")

    __table_args__ = (
        Index("idx_refresh_tokens_token_hash", "token_hash"),
        Index("idx_refresh_tokens_account_id", "account_id"),
        Index(
            "idx_refresh_tokens_active",
            "token_hash",
            "account_id",
            "expires_at",
            postgresql_where=(revoked == False),
        ),
        Index(
            "idx_refresh_tokens_cleanup",
            "expires_at",
            postgresql_where=(revoked == False),
        ),
    )

    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.id}, account_id={self.account_id}, revoked={self.revoked})>"


class Project(database.Base):
    """
    Projects table for multi-tenancy.

    Performance notes:
    - Indexed account_id for fast project listing
    - Unique slug for fast lookups
    - SmallInteger for retention_days (saves space)
    """

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)

    account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        VARCHAR(255), unique=True, nullable=False, index=True
    )
    environment: Mapped[str] = mapped_column(
        VARCHAR(20), default="production", nullable=False
    )

    retention_days: Mapped[int] = mapped_column(
        SmallInteger, default=30, nullable=False
    )
    daily_quota: Mapped[int] = mapped_column(
        BigInteger, default=1_000_000, nullable=False
    )

    available_routes: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, nullable=False, server_default="{}"
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        onupdate=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    account: Mapped["Account"] = relationship("Account", back_populates="projects")
    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    daily_usage: Mapped[list["DailyUsage"]] = relationship(
        "DailyUsage",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    members: Mapped[list["ProjectMember"]] = relationship(
        "ProjectMember",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    invite_codes: Mapped[list["ProjectInviteCode"]] = relationship(
        "ProjectInviteCode",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_projects_account_id", "account_id"),
        Index("idx_projects_slug", "slug"),
        CheckConstraint(
            "environment IN ('production', 'staging', 'dev')",
            name="check_project_environment",
        ),
        CheckConstraint(
            "retention_days >= 1 AND retention_days <= 365",
            name="check_retention_days",
        ),
        CheckConstraint(
            "daily_quota >= 1000",
            name="check_daily_quota",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Project(id={self.id}, slug={self.slug}, environment={self.environment})>"
        )


class ApiKey(database.Base):
    """
    API keys table for authentication.

    Performance notes:
    - CHAR(60) for bcrypt hash (fixed length)
    - Unique key_hash for fast validation
    - Covering index for validation query
    - Partial index on active keys only
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)

    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    key_prefix: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    key_hash: Mapped[str] = mapped_column(
        CHAR(60), unique=True, nullable=False, index=True
    )

    name: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(VARCHAR(20), default="active", nullable=False)
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer, default=1000, nullable=False
    )
    rate_limit_per_hour: Mapped[int] = mapped_column(
        Integer, default=50_000, nullable=False
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="api_keys")

    __table_args__ = (
        Index("idx_api_keys_key_hash", "key_hash"),
        Index("idx_api_keys_project_id", "project_id"),
        Index(
            "idx_api_keys_validation",
            "key_hash",
            "status",
            "expires_at",
            "project_id",
            postgresql_where=(status == "active"),
        ),
        CheckConstraint(
            "status IN ('active', 'revoked')",
            name="check_api_key_status",
        ),
        CheckConstraint(
            "rate_limit_per_minute >= 10",
            name="check_rate_limit_per_minute",
        ),
        CheckConstraint(
            "rate_limit_per_hour >= 100",
            name="check_rate_limit_per_hour",
        ),
    )

    def __repr__(self) -> str:
        return f"<ApiKey(id={self.id}, prefix={self.key_prefix}, status={self.status})>"


class DailyUsage(database.Base):
    """
    Daily usage tracking for quota enforcement and billing.

    Performance notes:
    - Composite unique index on (project_id, date)
    - UPSERT pattern for atomic increments
    - Descending date index for recent queries
    """

    __tablename__ = "daily_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)

    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    date: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
    )

    logs_ingested: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    logs_queried: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    storage_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        onupdate=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="daily_usage")

    __table_args__ = (
        Index(
            "idx_daily_usage_project_date",
            "project_id",
            "date",
            postgresql_ops={"date": "DESC"},
        ),
        Index("uq_daily_usage_project_date", "project_id", "date", unique=True),
        CheckConstraint(
            "logs_ingested >= 0",
            name="check_logs_ingested",
        ),
        CheckConstraint(
            "logs_queried >= 0",
            name="check_logs_queried",
        ),
    )

    def __repr__(self) -> str:
        return f"<DailyUsage(project_id={self.project_id}, date={self.date}, logs={self.logs_ingested})>"


class ProjectMember(database.Base):
    __tablename__ = "project_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)

    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(VARCHAR(20), default="member", nullable=False)

    joined_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="members")
    account: Mapped["Account"] = relationship("Account", backref="project_memberships")

    __table_args__ = (
        Index("idx_project_members_account_id", "account_id"),
        Index("idx_project_members_project_id", "project_id"),
        Index("uq_project_members", "project_id", "account_id", unique=True),
        CheckConstraint(
            "role IN ('owner', 'member')",
            name="check_member_role",
        ),
    )

    def __repr__(self) -> str:
        return f"<ProjectMember(project_id={self.project_id}, account_id={self.account_id}, role={self.role})>"


class ProjectInviteCode(database.Base):
    __tablename__ = "project_invite_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)

    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    used_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    used_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="invite_codes")

    __table_args__ = (
        Index(
            "idx_invite_codes_code_hash",
            "code_hash",
            postgresql_where=(used_at == None),  # noqa: E711
        ),
        Index("idx_invite_codes_project_expires", "project_id", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<ProjectInviteCode(project_id={self.project_id}, expires_at={self.expires_at})>"


class UserDashboard(database.Base):
    """
    User dashboard configuration table.

    Stores user-specific dashboard panel configurations using JSONB.
    Each user has one dashboard with multiple customizable panels.

    Performance notes:
    - JSONB for flexible panel storage with indexing support
    - One-to-one relationship with Account (unique user_id)
    - GIN index on panels for fast JSON queries
    """

    __tablename__ = "user_dashboards"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    panels: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        onupdate=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    account: Mapped["Account"] = relationship("Account", backref="dashboard")

    __table_args__ = (
        Index("idx_user_dashboards_user_id", "user_id"),
        Index("idx_user_dashboards_panels", "panels", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<UserDashboard(id={self.id}, user_id={self.user_id}, panels={len(self.panels)})>"


class Notification(database.Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    severity: Mapped[str] = mapped_column(VARCHAR(20), default="info", nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    read_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    account: Mapped["Account"] = relationship("Account", backref="notifications")

    __table_args__ = (
        Index("idx_notifications_user_unread", "user_id", "read_at"),
        Index("idx_notifications_project_id", "project_id"),
        Index("idx_notifications_expires_at", "expires_at"),
        CheckConstraint(
            "kind IN ('error', 'alert_firing', 'alert_resolved', 'quota_warning')",
            name="check_notification_kind",
        ),
        CheckConstraint(
            "severity IN ('critical', 'warning', 'info')",
            name="check_notification_severity",
        ),
    )

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, user_id={self.user_id}, kind={self.kind})>"


class AlertRule(database.Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)

    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    metric_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    comparator: Mapped[str] = mapped_column(VARCHAR(4), nullable=False)
    threshold: Mapped[float] = mapped_column(nullable=False)
    window_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    severity: Mapped[str] = mapped_column(VARCHAR(20), default="warning", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    state: Mapped[str] = mapped_column(VARCHAR(10), default="ok", nullable=False)
    last_fired_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fired_value: Mapped[float | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        onupdate=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    channels: Mapped[list["AlertChannel"]] = relationship(
        "AlertChannel",
        back_populates="rule",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_alert_rules_project_id", "project_id"),
        Index(
            "idx_alert_rules_enabled",
            "project_id",
            "enabled",
            postgresql_where=(enabled == True),  # noqa: E712
        ),
        CheckConstraint(
            "comparator IN ('>', '<', '>=', '<=')",
            name="check_alert_comparator",
        ),
        CheckConstraint(
            "severity IN ('critical', 'warning', 'info')",
            name="check_alert_severity",
        ),
        CheckConstraint(
            "state IN ('ok', 'firing')",
            name="check_alert_state",
        ),
        CheckConstraint(
            "window_minutes >= 1",
            name="check_alert_window_minutes",
        ),
    )

    def __repr__(self) -> str:
        return f"<AlertRule(id={self.id}, project_id={self.project_id}, name={self.name}, state={self.state})>"


class AlertChannel(database.Base):
    __tablename__ = "alert_channels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)

    rule_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("alert_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    rule: Mapped["AlertRule"] = relationship("AlertRule", back_populates="channels")

    __table_args__ = (
        Index("idx_alert_channels_rule_id", "rule_id"),
        CheckConstraint(
            "kind IN ('in_app', 'email', 'webhook')",
            name="check_alert_channel_kind",
        ),
    )

    def __repr__(self) -> str:
        return f"<AlertChannel(id={self.id}, rule_id={self.rule_id}, kind={self.kind})>"


class NotificationPreference(database.Base):
    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    rule_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("alert_rules.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    severity: Mapped[str | None] = mapped_column(VARCHAR(20), nullable=True)
    muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    channel_overrides: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        onupdate=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_notif_prefs_user_project", "user_id", "project_id"),
        Index(
            "uq_notif_prefs",
            "user_id",
            "project_id",
            "rule_id",
            "severity",
            unique=True,
        ),
        CheckConstraint(
            "severity IS NULL OR severity IN ('critical', 'warning', 'info')",
            name="check_notif_pref_severity",
        ),
    )

    def __repr__(self) -> str:
        return f"<NotificationPreference(user_id={self.user_id}, project_id={self.project_id}, muted={self.muted})>"
