import pydantic


class HealthThresholds(pydantic.BaseModel):
    error_rate_warn: float = pydantic.Field(..., description="Error rate above which status becomes degraded")
    error_rate_crit: float = pydantic.Field(..., description="Error rate above which status becomes down")
    p95_warn_ms: int = pydantic.Field(..., description="p95 latency (ms) above which status becomes degraded")
    p95_crit_ms: int = pydantic.Field(..., description="p95 latency (ms) above which status becomes down")


class HealthSummary(pydantic.BaseModel):
    project_id: str = pydantic.Field(..., description="Project identifier")
    error_rate: float = pydantic.Field(..., description="Error rate as fraction (0..1) over the period")
    p95_ms: float = pydantic.Field(..., description="95th percentile response time in milliseconds")
    rps: float = pydantic.Field(..., description="Average requests per second over the period")
    status: str = pydantic.Field(..., description="healthy | degraded | down")
    sparkline: list[int] = pydantic.Field(..., description="Request volume per hour for last 24 hours (24 buckets)")
    thresholds: HealthThresholds
    generated_at: str = pydantic.Field(..., description="ISO 8601 timestamp when summary was computed")


class HealthSummaryResponse(pydantic.BaseModel):
    summaries: list[HealthSummary]
