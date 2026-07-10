import typing

import pydantic


class CreateProjectRequest(pydantic.BaseModel):
    """Request body for creating a new project."""

    name: str = pydantic.Field(
        ...,
        min_length=1,
        max_length=255,
        description="Project display name",
        examples=["My Production App"],
    )
    slug: str = pydantic.Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9-]+$",
        description="Unique project identifier (lowercase, alphanumeric, hyphens only)",
        examples=["my-production-app"],
    )
    environment: str = pydantic.Field(
        default="production",
        pattern=r"^(production|staging|dev)$",
        description="Deployment environment (production, staging, or dev)",
        examples=["production"],
    )

    @pydantic.field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                "Slug must contain only alphanumeric characters, hyphens, and underscores"
            )

        return v.lower()

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "My Production App",
                    "slug": "my-production-app",
                    "environment": "production",
                }
            ]
        }
    )


class ProjectResponse(pydantic.BaseModel):
    """Project details response."""

    project_id: int = pydantic.Field(..., description="Unique project identifier")
    name: str = pydantic.Field(..., description="Project display name")
    slug: str = pydantic.Field(..., description="Project slug")
    environment: str = pydantic.Field(..., description="Deployment environment")
    retention_days: int = pydantic.Field(..., description="Log retention period in days")
    logs_daily_quota: int = pydantic.Field(..., description="Daily log ingestion quota")
    spans_daily_quota: int = pydantic.Field(..., description="Daily span ingestion quota")
    metrics_daily_quota: int = pydantic.Field(..., description="Daily metric point ingestion quota")
    available_routes: list[str] = pydantic.Field(
        default_factory=list,
        description="List of unique API endpoint routes (e.g., 'GET /api/v1/users') discovered from endpoint logs. Populated by analytics workers.",
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "project_id": 456,
                    "name": "My Production App",
                    "slug": "my-production-app",
                    "environment": "production",
                    "retention_days": 30,
                    "logs_daily_quota": 100000,
                    "spans_daily_quota": 300000,
                    "metrics_daily_quota": 100000,
                    "available_routes": [
                        "GET /api/v1/users",
                        "POST /api/v1/orders",
                        "GET /api/v1/products/:id",
                    ],
                }
            ]
        }
    )


class ProjectListResponse(pydantic.BaseModel):
    """Response containing a list of projects."""

    projects: typing.List[ProjectResponse] = pydantic.Field(..., description="List of projects")
    total: int = pydantic.Field(..., description="Total number of projects")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "projects": [
                        {
                            "project_id": 456,
                            "name": "My Production App",
                            "slug": "my-production-app",
                            "environment": "production",
                            "retention_days": 30,
                            "logs_daily_quota": 100000,
                            "spans_daily_quota": 300000,
                            "metrics_daily_quota": 100000,
                            "available_routes": ["GET /api/v1/users"],
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    )


class SignalQuota(pydantic.BaseModel):
    """Quota/usage/remaining for a single ingestion signal (logs, spans, or metrics)."""

    quota: int = pydantic.Field(..., description="Maximum items allowed per day", ge=0)
    usage: int = pydantic.Field(..., description="Items ingested today", ge=0)
    remaining: int = pydantic.Field(..., description="Remaining quota for today", ge=0)


class ProjectQuotaResponse(pydantic.BaseModel):
    """Project quota and usage information for frontend display, split per signal."""

    project_id: int = pydantic.Field(..., description="Project identifier")
    project_name: str = pydantic.Field(..., description="Project display name")
    project_slug: str = pydantic.Field(..., description="Project slug")
    environment: str = pydantic.Field(..., description="Deployment environment")
    logs: SignalQuota = pydantic.Field(..., description="Log ingestion quota/usage")
    spans: SignalQuota = pydantic.Field(..., description="Span ingestion quota/usage")
    metrics: SignalQuota = pydantic.Field(..., description="Metric point ingestion quota/usage")
    quota_reset_at: str = pydantic.Field(
        ..., description="When the daily quotas reset (midnight UTC, ISO 8601)"
    )
    retention_days: int = pydantic.Field(..., description="Log retention period in days")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "project_id": 456,
                    "project_name": "My Production App",
                    "project_slug": "my-production-app",
                    "environment": "production",
                    "logs": {"quota": 100000, "usage": 1234, "remaining": 98766},
                    "spans": {"quota": 300000, "usage": 555, "remaining": 299445},
                    "metrics": {"quota": 100000, "usage": 42, "remaining": 99958},
                    "quota_reset_at": "2024-01-16T00:00:00Z",
                    "retention_days": 30,
                }
            ]
        }
    )


class UpdateProjectRequest(pydantic.BaseModel):
    """Update a project's retention/quota settings. Project owner only."""

    retention_days: typing.Optional[int] = pydantic.Field(
        None, ge=1, le=365, description="Log retention period in days (1-365)"
    )
    logs_daily_quota: typing.Optional[int] = pydantic.Field(
        None, ge=1, description="Maximum logs allowed per day"
    )
    spans_daily_quota: typing.Optional[int] = pydantic.Field(
        None, ge=1, description="Maximum spans allowed per day"
    )
    metrics_daily_quota: typing.Optional[int] = pydantic.Field(
        None, ge=1, description="Maximum metric points allowed per day"
    )

    model_config = pydantic.ConfigDict(json_schema_extra={"examples": [{"retention_days": 90}]})


class UsageStatsDay(pydantic.BaseModel):
    """Per-day usage counts and quotas for all three signals."""

    date: str = pydantic.Field(..., description="Date (YYYY-MM-DD)")
    log_count: int = pydantic.Field(..., description="Logs ingested that day")
    span_count: int = pydantic.Field(..., description="Spans ingested that day")
    metric_point_count: int = pydantic.Field(..., description="Metric points ingested that day")
    logs_daily_quota: int = pydantic.Field(..., description="Daily log quota in effect that day")
    spans_daily_quota: int = pydantic.Field(..., description="Daily span quota in effect that day")
    metrics_daily_quota: int = pydantic.Field(
        ..., description="Daily metric point quota in effect that day"
    )
    logs_quota_used_percent: float = pydantic.Field(
        ..., description="Percent of log quota used that day"
    )
    spans_quota_used_percent: float = pydantic.Field(
        ..., description="Percent of span quota used that day"
    )
    metrics_quota_used_percent: float = pydantic.Field(
        ..., description="Percent of metric point quota used that day"
    )


class UsageStatsResponse(pydantic.BaseModel):
    """Per-day usage history for a project, one entry per day with data."""

    project_id: int = pydantic.Field(..., description="Project identifier")
    usage: typing.List[UsageStatsDay] = pydantic.Field(
        ..., description="Per-day usage entries (missing days had no ingestion)"
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "project_id": 456,
                    "usage": [
                        {
                            "date": "2026-07-10",
                            "log_count": 1234,
                            "span_count": 4567,
                            "metric_point_count": 89,
                            "logs_daily_quota": 100000,
                            "spans_daily_quota": 300000,
                            "metrics_daily_quota": 100000,
                            "logs_quota_used_percent": 1.23,
                            "spans_quota_used_percent": 0.19,
                            "metrics_quota_used_percent": 0.09,
                        }
                    ],
                }
            ]
        }
    )
