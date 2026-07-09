import datetime

import ingestion_service.database as database
from sqlalchemy import (
    CHAR,
    VARCHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    SmallInteger,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


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
    importance: Mapped[str] = mapped_column(VARCHAR(20), default="standard", nullable=False)

    environment: Mapped[str | None] = mapped_column(VARCHAR(20), nullable=True)
    release: Mapped[str | None] = mapped_column(VARCHAR(100), nullable=True)

    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)

    attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    method: Mapped[str | None] = mapped_column(VARCHAR(8), nullable=True)
    path: Mapped[str | None] = mapped_column(VARCHAR(2048), nullable=True)
    status_code: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sdk_version: Mapped[str | None] = mapped_column(VARCHAR(20), nullable=True)
    platform: Mapped[str | None] = mapped_column(VARCHAR(50), nullable=True)
    platform_version: Mapped[str | None] = mapped_column(VARCHAR(50), nullable=True)

    processing_time_ms: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    error_fingerprint: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)

    log_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)

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
        Index(
            "idx_logs_dedup",
            "project_id",
            "log_id",
            "timestamp",
            unique=True,
            postgresql_where="log_id IS NOT NULL",
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

    status: Mapped[str] = mapped_column(VARCHAR(20), default="unresolved", nullable=False)
    assigned_to: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    sample_log_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sample_stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)

    resolved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_in_release: Mapped[str | None] = mapped_column(VARCHAR(100), nullable=True)

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


class Span(database.Base):
    __tablename__ = "spans"

    span_id: Mapped[str] = mapped_column(CHAR(16), primary_key=True, nullable=False)
    trace_id: Mapped[str] = mapped_column(CHAR(32), nullable=False, index=True)
    parent_span_id: Mapped[str | None] = mapped_column(CHAR(16), nullable=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    service_name: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)

    start_time: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
    )
    duration_ns: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    status_code: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    attributes: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    events: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    error_fingerprint: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)

    __table_args__ = (
        Index("brin_spans_project_time", "project_id", "start_time"),
        Index("idx_spans_op", "project_id", "service_name", "name", "start_time"),
        {"postgresql_partition_by": "RANGE (start_time)"},
    )

    def __repr__(self) -> str:
        return (
            f"<Span(span_id={self.span_id}, trace_id={self.trace_id}, "
            f"project_id={self.project_id}, name={self.name})>"
        )


class MetricPoint(database.Base):
    __tablename__ = "metric_points"

    project_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    type: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    tags_hash: Mapped[str] = mapped_column(CHAR(16), primary_key=True, nullable=False)
    ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
    )

    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sum: Mapped[float | None] = mapped_column(Float, nullable=True)
    bucket_counts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    explicit_bounds: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    tags: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    service_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_metric_points_lookup", "project_id", "name", "ts"),
        {"postgresql_partition_by": "RANGE (ts)"},
    )

    def __repr__(self) -> str:
        return f"<MetricPoint(project_id={self.project_id}, name={self.name}, ts={self.ts})>"
