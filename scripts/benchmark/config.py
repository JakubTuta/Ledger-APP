import os

import pydantic


def _default_base_url() -> str:
    port = os.environ.get("GATEWAY_HTTP_PORT", "8020")
    return f"http://localhost:{port}"


def _default_auth_db_dsn() -> str:
    pw = os.environ.get("AUTH_DB_PASSWORD", "")
    return f"postgresql://postgres:{pw}@localhost:5432/auth_db"


def _default_logs_db_dsn() -> str:
    pw = os.environ.get("LOGS_DB_PASSWORD", "")
    return f"postgresql://postgres:{pw}@localhost:5433/logs_db"


def _default_redis_url() -> str:
    pw = os.environ.get("REDIS_PASSWORD", "")
    return f"redis://:{pw}@localhost:6379/0"


def _default_rabbitmq_management_url() -> str:
    return "http://localhost:15672"


def _default_rabbitmq_host() -> str:
    # Deliberately not reading $RABBITMQ_HOST from .env: that variable is set to
    # the in-container hostname (ledger-rabbitmq) for services running inside
    # the compose network. The benchmark client runs on the host, where the
    # broker is only reachable via the published localhost port.
    return "localhost"


def _default_rabbitmq_port() -> int:
    return 5672


def _default_rabbitmq_user() -> str:
    return os.environ.get("RABBITMQ_USER", "ledger")


def _default_rabbitmq_password() -> str:
    return os.environ.get("RABBITMQ_PASSWORD", "ledger")


def _default_rabbitmq_queue() -> str:
    return os.environ.get("RABBITMQ_QUEUE", "ingestion.logs")


class BenchmarkConfig(pydantic.BaseModel):
    base_url: str = pydantic.Field(default_factory=_default_base_url)
    batch_size: int = pydantic.Field(default=1000, ge=1, le=1000)
    concurrency: int = pydantic.Field(default=16, ge=1)
    gzip: bool = True
    wire: str = pydantic.Field(default="protobuf", pattern="^(protobuf|json)$")

    # --mode: "steady" is the default and the one whose headline number is
    # trustworthy (open-loop pacer, slope-based verdict). "ramp" is the legacy
    # closed-loop burst-then-drain sweep, kept for quick smoke checks - its
    # drain_rate is a haircut on ingress, not a measurement, and it should not
    # be used to justify a performance claim. "single" is one closed-loop burst.
    mode: str = pydantic.Field(default="steady", pattern="^(steady|ramp|single)$")

    # steady-state (open-loop) settings
    offered_rate: float | None = None
    find_max: bool = False
    warmup_seconds: float = pydantic.Field(default=10.0, ge=0)
    hold_seconds: float = pydantic.Field(default=120.0, ge=5)
    max_inflight: int = pydantic.Field(default=256, ge=1)
    depth_slope_tolerance: float = pydantic.Field(default=2.0, ge=0)
    slo_p50_ms: float = pydantic.Field(default=250.0, ge=0)
    slo_p99_ms: float = pydantic.Field(default=1000.0, ge=0)
    client_cpu_budget: float = pydantic.Field(default=0.6, ge=0, le=64.0)
    ingress_tolerance: float = pydantic.Field(default=0.02, ge=0, le=1.0)
    log_id_mode: str = pydantic.Field(default="client", pattern="^(client|none)$")

    # ramp (legacy) settings
    ramp_start: int = pydantic.Field(default=4, ge=1)
    ramp_step: int = pydantic.Field(default=4, ge=1)
    ramp_max: int = pydantic.Field(default=64, ge=1)
    ramp_stage_seconds: int = pydantic.Field(default=30, ge=5)
    ramp_drain_timeout: int = pydantic.Field(default=60, ge=10)
    ramp_confirm: bool = False

    duration_seconds: int | None = None
    total_logs: int | None = None
    api_key: str | None = None
    project_id: int | None = None
    respect_limits: bool = False
    per_minute_limit: int = 1_000_000
    per_hour_limit: int = 1_000_000_000
    # Ceiling applied to all three per-signal quotas (logs/spans/metrics) during
    # provisioning, so benchmark load isn't throttled by any one signal's quota.
    daily_quota: int = 1_000_000_000
    json_output: str | None = None
    publish: bool = False
    verbose: bool = False
    request_timeout: int = pydantic.Field(default=30, ge=5)
    no_db_verify: bool = False

    destructive_reset: bool = False
    expect_db: str | None = None

    auth_db_dsn: str = pydantic.Field(default_factory=_default_auth_db_dsn)
    logs_db_dsn: str = pydantic.Field(default_factory=_default_logs_db_dsn)
    redis_url: str = pydantic.Field(default_factory=_default_redis_url)
    rabbitmq_management_url: str = pydantic.Field(default_factory=_default_rabbitmq_management_url)
    rabbitmq_host: str = pydantic.Field(default_factory=_default_rabbitmq_host)
    rabbitmq_port: int = pydantic.Field(default_factory=_default_rabbitmq_port)
    rabbitmq_user: str = pydantic.Field(default_factory=_default_rabbitmq_user)
    rabbitmq_password: str = pydantic.Field(default_factory=_default_rabbitmq_password)
    rabbitmq_vhost: str = "/"
    rabbitmq_queue: str = pydantic.Field(default_factory=_default_rabbitmq_queue)

    @property
    def rabbitmq_amqp_url(self) -> str:
        import urllib.parse

        password = urllib.parse.quote(self.rabbitmq_password, safe="")
        vhost = urllib.parse.quote(self.rabbitmq_vhost, safe="")
        return (
            f"amqp://{self.rabbitmq_user}:{password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/{vhost}"
        )

    @pydantic.model_validator(mode="after")
    def validate_run_mode(self) -> "BenchmarkConfig":
        if self.mode == "single":
            if self.duration_seconds is None and self.total_logs is None:
                raise ValueError("mode=single requires --duration or --total-logs")
        if self.destructive_reset and not self.expect_db:
            raise ValueError("--destructive-reset requires --expect-db as a safety confirmation")
        return self
