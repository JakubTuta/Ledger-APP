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
    ramp: bool = True
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
    daily_quota: int = 1_000_000_000
    json_output: str | None = None
    verbose: bool = False
    request_timeout: int = pydantic.Field(default=30, ge=5)
    no_db_verify: bool = False
    auth_db_dsn: str = pydantic.Field(default_factory=_default_auth_db_dsn)
    logs_db_dsn: str = pydantic.Field(default_factory=_default_logs_db_dsn)
    redis_url: str = pydantic.Field(default_factory=_default_redis_url)
    rabbitmq_management_url: str = pydantic.Field(default_factory=_default_rabbitmq_management_url)
    rabbitmq_user: str = pydantic.Field(default_factory=_default_rabbitmq_user)
    rabbitmq_password: str = pydantic.Field(default_factory=_default_rabbitmq_password)
    rabbitmq_queue: str = pydantic.Field(default_factory=_default_rabbitmq_queue)

    @pydantic.model_validator(mode="after")
    def validate_run_mode(self) -> "BenchmarkConfig":
        if not self.ramp:
            if self.duration_seconds is None and self.total_logs is None:
                raise ValueError("Non-ramp mode requires --duration or --total-logs")
        return self
