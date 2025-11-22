import datetime

import auth_service.database as database
from sqlalchemy import (
    CHAR,
    VARCHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
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
