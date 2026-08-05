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
    client_cpu_fraction: float | None = None
    run_id: str | None = None


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
    table_growth: "TableGrowthStats | None" = None


class TableGrowthStats(pydantic.BaseModel):
    """
    pg_statio/pg_stat snapshot for `logs` and its dedup index, taken after a
    stage completes. Lets a ramp/steady run be read alongside table size rather
    than mistaking table-growth-driven slowdown for a concurrency effect.
    """

    total_relation_bytes: int
    dedup_index_bytes: int
    dedup_index_hit_ratio: float | None
    autovacuum_ran_during_stage: bool


class SteadyResult(pydantic.BaseModel):
    """
    Result of one open-loop steady-state hold at a fixed offered rate. Unlike
    PhaseResult (closed-loop, N workers hammering as fast as they can),
    `accepted`/`rejected` here only count the post-warmup hold window, and the
    verdict is threshold-based rather than inferred from a haircut on ingress.
    """

    offered_rate: float
    warmup_seconds: float
    hold_seconds: float
    batch_size: int
    max_inflight: int
    pacer_stalls: int
    achieved_ingress_rate: float
    accepted: int
    rejected: int
    total_requests: int
    errors: ErrorBreakdown
    latency: LatencyStats
    client_cpu_fraction: float | None
    depth_series: list[int] = pydantic.Field(default_factory=list)
    depth_slope_per_s: float
    missing_rows: int | None
    expected_dedupe_collisions: int | None = None
    post_run_flush_seconds: float
    table_growth: TableGrowthStats | None = None
    healthy: bool
    fail_reasons: list[str] = pydantic.Field(default_factory=list)
    started_at: float
    run_id: str | None = None


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
    steady_runs: list[SteadyResult] = pydantic.Field(default_factory=list)
    max_sustainable_offered_rate: float | None = None
    headline_logs_per_second: float | None = None
    headline_concurrency: int | None = None
    verdict: str = "UNKNOWN"
    config_summary: dict = pydantic.Field(default_factory=dict)
    started_at_utc: str = ""
    finished_at_utc: str = ""
    total_wall_seconds: float = 0.0
