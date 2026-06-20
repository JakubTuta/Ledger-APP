import pydantic


class ErrorBreakdown(pydantic.BaseModel):
    rate_429: int = 0
    quota_402: int = 0
    queue_503: int = 0
    server_500: int = 0
    transport: int = 0

    @property
    def total(self) -> int:
        return self.rate_429 + self.quota_402 + self.queue_503 + self.server_500 + self.transport


class LatencyStats(pydantic.BaseModel):
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    mean_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0


class PhaseResult(pydantic.BaseModel):
    concurrency: int
    duration_s: float
    total_requests: int
    accepted: int
    rejected: int
    errors: ErrorBreakdown
    latency: LatencyStats
    ingress_rate: float
    started_at: float


class DrainResult(pydantic.BaseModel):
    drained: bool
    drain_seconds: float
    max_depth: int
    depth_series: list[int] = pydantic.Field(default_factory=list)


class StageResult(pydantic.BaseModel):
    concurrency: int
    phase: PhaseResult
    drain: DrainResult
    db_delta: int | None = None
    ingress_rate: float
    drain_rate: float
    healthy: bool
    saturation_cause: str | None = None


class RunReport(pydantic.BaseModel):
    mode: str
    provisioned_email: str | None = None
    provisioned_project_id: int | None = None
    api_key_prefix: str | None = None
    limits_bumped: bool = False
    stages: list[StageResult] = pydantic.Field(default_factory=list)
    best_stage: StageResult | None = None
    single_phase: PhaseResult | None = None
    single_drain: DrainResult | None = None
    single_db_delta: int | None = None
    headline_logs_per_second: float | None = None
    headline_concurrency: int | None = None
    verdict: str = "UNKNOWN"
    config_summary: dict = pydantic.Field(default_factory=dict)
    started_at_utc: str = ""
    finished_at_utc: str = ""
    total_wall_seconds: float = 0.0
