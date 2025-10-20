import datetime

import sqlalchemy
import sqlalchemy.dialects.postgresql as postgresql
import sqlalchemy.orm as orm

Base = orm.declarative_base()


class Log(Base):
    __tablename__ = "logs"

    id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger, primary_key=True, autoincrement=True
    )
    project_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger, nullable=False, index=True
    )

    timestamp: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sqlalchemy.DateTime(timezone=True),
        primary_key=True,
        nullable=False,
    )
    ingested_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sqlalchemy.DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    level: orm.Mapped[str] = orm.mapped_column(sqlalchemy.VARCHAR(20), nullable=False)
    log_type: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.VARCHAR(30), nullable=False
    )
    importance: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.VARCHAR(20), default="standard", nullable=False
    )

    environment: orm.Mapped[str | None] = orm.mapped_column(
        sqlalchemy.VARCHAR(20), nullable=True
    )
    release: orm.Mapped[str | None] = orm.mapped_column(
        sqlalchemy.VARCHAR(100), nullable=True
    )

    message: orm.Mapped[str | None] = orm.mapped_column(sqlalchemy.Text, nullable=True)
    error_type: orm.Mapped[str | None] = orm.mapped_column(
        sqlalchemy.VARCHAR(255), nullable=True
    )
    error_message: orm.Mapped[str | None] = orm.mapped_column(
        sqlalchemy.Text, nullable=True
    )
    stack_trace: orm.Mapped[str | None] = orm.mapped_column(
        sqlalchemy.Text, nullable=True
    )

    attributes: orm.Mapped[dict | None] = orm.mapped_column(
        postgresql.JSONB, nullable=True
    )

    sdk_version: orm.Mapped[str | None] = orm.mapped_column(
        sqlalchemy.VARCHAR(20), nullable=True
    )
    platform: orm.Mapped[str | None] = orm.mapped_column(
        sqlalchemy.VARCHAR(50), nullable=True
    )
    platform_version: orm.Mapped[str | None] = orm.mapped_column(
        sqlalchemy.VARCHAR(50), nullable=True
    )

    processing_time_ms: orm.Mapped[int | None] = orm.mapped_column(
        sqlalchemy.SmallInteger, nullable=True
    )

    error_fingerprint: orm.Mapped[str | None] = orm.mapped_column(
        sqlalchemy.CHAR(64), nullable=True
    )

    __table_args__ = (
        sqlalchemy.Index("idx_logs_project_timestamp", "project_id", "timestamp"),
        sqlalchemy.Index(
            "idx_logs_project_level",
            "project_id",
            "level",
            "timestamp",
            postgresql_where=sqlalchemy.text("level IN ('error', 'critical')"),
        ),
        sqlalchemy.Index(
            "idx_logs_error_fingerprint",
            "project_id",
            "error_fingerprint",
            "timestamp",
            postgresql_where=sqlalchemy.text("error_fingerprint IS NOT NULL"),
        ),
        sqlalchemy.CheckConstraint(
            "level IN ('debug', 'info', 'warning', 'error', 'critical')",
            name="check_log_level",
        ),
        sqlalchemy.CheckConstraint(
            "log_type IN ('console', 'logger', 'exception', 'network', 'database', 'endpoint', 'custom')",
            name="check_log_type",
        ),
        sqlalchemy.CheckConstraint(
            "importance IN ('critical', 'high', 'standard', 'low')",
            name="check_importance",
        ),
        {"postgresql_partition_by": "RANGE (timestamp)"},
    )

    def __repr__(self) -> str:
        return (
            f"<Log(id={self.id}, project_id={self.project_id}, "
            f"level={self.level}, timestamp={self.timestamp})>"
        )


class ErrorGroup(Base):
    __tablename__ = "error_groups"

    id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger, primary_key=True, index=True, autoincrement=True
    )
    project_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger, nullable=False, index=True
    )

    fingerprint: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.CHAR(64), nullable=False
    )
    error_type: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.VARCHAR(255), nullable=False
    )
    error_message: orm.Mapped[str | None] = orm.mapped_column(
        sqlalchemy.Text, nullable=True
    )

    first_seen: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sqlalchemy.DateTime(timezone=True),
        nullable=False,
    )
    last_seen: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sqlalchemy.DateTime(timezone=True),
        nullable=False,
    )
    occurrence_count: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger, default=1, nullable=False
    )

    status: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.VARCHAR(20), default="unresolved", nullable=False
    )
    assigned_to: orm.Mapped[int | None] = orm.mapped_column(
        sqlalchemy.BigInteger, nullable=True
    )

    sample_log_id: orm.Mapped[int | None] = orm.mapped_column(
        sqlalchemy.BigInteger, nullable=True
    )
    sample_stack_trace: orm.Mapped[str | None] = orm.mapped_column(
        sqlalchemy.Text, nullable=True
    )

    created_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sqlalchemy.DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    updated_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sqlalchemy.DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        onupdate=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        sqlalchemy.Index(
            "idx_error_groups_fingerprint",
            "project_id",
            "fingerprint",
            unique=True,
        ),
        sqlalchemy.Index("idx_error_groups_status", "project_id", "status", "last_seen"),
        sqlalchemy.Index("idx_error_groups_type", "project_id", "error_type", "last_seen"),
        sqlalchemy.CheckConstraint(
            "status IN ('unresolved', 'resolved', 'ignored', 'muted')",
            name="check_error_status",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ErrorGroup(id={self.id}, project_id={self.project_id}, "
            f"error_type={self.error_type}, status={self.status})>"
        )
