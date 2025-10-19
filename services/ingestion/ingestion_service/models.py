import datetime

import ingestion_service.database as database
from sqlalchemy import (
    CHAR,
    VARCHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    SmallInteger,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Log(database.Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
    )
    ingested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    level: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    log_type: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    importance: Mapped[str] = mapped_column(
        VARCHAR(20), default="standard", nullable=False
    )

    environment: Mapped[str | None] = mapped_column(VARCHAR(20), nullable=True)
    release: Mapped[str | None] = mapped_column(VARCHAR(100), nullable=True)

    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)

    attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    sdk_version: Mapped[str | None] = mapped_column(VARCHAR(20), nullable=True)
    platform: Mapped[str | None] = mapped_column(VARCHAR(50), nullable=True)
    platform_version: Mapped[str | None] = mapped_column(VARCHAR(50), nullable=True)

    processing_time_ms: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    error_fingerprint: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)

    __table_args__ = (
        Index("idx_logs_project_timestamp", "project_id", "timestamp"),
        Index(
            "idx_logs_project_level",
            "project_id",
            "level",
            "timestamp",
            postgresql_where="level IN ('error', 'critical')",
        ),
        Index(
            "idx_logs_error_fingerprint",
            "project_id",
            "error_fingerprint",
            "timestamp",
            postgresql_where="error_fingerprint IS NOT NULL",
        ),
        CheckConstraint(
            "level IN ('debug', 'info', 'warning', 'error', 'critical')",
            name="check_log_level",
        ),
        CheckConstraint(
            "log_type IN ('console', 'logger', 'exception', 'network', 'database', 'endpoint', 'custom')",
            name="check_log_type",
        ),
        CheckConstraint(
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


class ErrorGroup(database.Base):
    __tablename__ = "error_groups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    error_type: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_seen: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    last_seen: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    occurrence_count: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)

    status: Mapped[str] = mapped_column(
        VARCHAR(20), default="unresolved", nullable=False
    )
    assigned_to: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    sample_log_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sample_stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)

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

    __table_args__ = (
        Index(
            "idx_error_groups_fingerprint",
            "project_id",
            "fingerprint",
            unique=True,
        ),
        Index("idx_error_groups_status", "project_id", "status", "last_seen"),
        Index("idx_error_groups_type", "project_id", "error_type", "last_seen"),
        CheckConstraint(
            "status IN ('unresolved', 'resolved', 'ignored', 'muted')",
            name="check_error_status",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ErrorGroup(id={self.id}, project_id={self.project_id}, "
            f"error_type={self.error_type}, status={self.status})>"
        )


class IngestionMetrics(database.Base):
    __tablename__ = "ingestion_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        default=datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    logs_received: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    logs_processed: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    logs_failed: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    latency_p50: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    latency_p95: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    latency_p99: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    queue_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    worker_count: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    __table_args__ = ({"postgresql_partition_by": "RANGE (timestamp)"},)

    def __repr__(self) -> str:
        return f"<IngestionMetrics(timestamp={self.timestamp}, logs_received={self.logs_received})>"
