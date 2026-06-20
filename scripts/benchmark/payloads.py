import datetime
import gzip
import json
import random


_ENDPOINT_PATHS = [
    "/api/v1/users/:id",
    "/api/v1/orders",
    "/api/v1/products/:id",
    "/api/v1/auth/login",
    "/api/v1/search",
    "/api/v1/reports/:id",
]
_ENDPOINT_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]
_ENDPOINT_STATUSES = [200, 200, 200, 201, 204, 400, 404, 500]

_ERROR_TYPES = [
    "ValueError",
    "DatabaseConnectionError",
    "TimeoutError",
    "KeyError",
    "RuntimeError",
    "PermissionError",
]

_STACK_TRACE_TEMPLATE = (
    "Traceback (most recent call last):\n"
    '  File "/app/services/api.py", line {line1}, in handle_request\n'
    "    result = await process(data)\n"
    '  File "/app/core/processor.py", line {line2}, in process\n'
    "    return await db.execute(query)\n"
    '  File "/app/db/connection.py", line {line3}, in execute\n'
    "    raise {error_type}('{message}')\n"
    "{error_type}: {message}\n"
)

_LEVELS_WEIGHTED = (
    ["debug"] * 25
    + ["info"] * 30
    + ["warning"] * 20
    + ["error"] * 15
    + ["critical"] * 10
)

_SERVICES = ["auth", "gateway", "ingestion", "query", "analytics"]


def build_template_pool(count: int, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    pool: list[dict] = []
    for _ in range(count):
        roll = rng.random()
        if roll < 0.20:
            pool.append(_make_exception_template(rng))
        elif roll < 0.45:
            pool.append(_make_endpoint_template(rng))
        else:
            pool.append(_make_logger_template(rng))
    return pool


def _make_logger_template(rng: random.Random) -> dict:
    return {
        "level": rng.choice(_LEVELS_WEIGHTED),
        "log_type": rng.choice(["logger", "console"]),
        "importance": rng.choice(["standard", "standard", "standard", "low", "high"]),
        "message": f"Service event: operation completed in {rng.randint(1, 500)}ms",
        "environment": "production",
        "release": "v1.0.0",
        "sdk_version": "1.0.0",
        "platform": "python",
        "platform_version": "3.12",
        "attributes": {
            "service": rng.choice(_SERVICES),
            "request_id": f"req_{rng.randint(100000, 999999)}",
            "duration_ms": rng.randint(1, 500),
        },
    }


def _make_endpoint_template(rng: random.Random) -> dict:
    status = rng.choice(_ENDPOINT_STATUSES)
    level = "info" if status < 400 else "warning" if status < 500 else "error"
    method = rng.choice(_ENDPOINT_METHODS)
    path = rng.choice(_ENDPOINT_PATHS)
    return {
        "level": level,
        "log_type": "endpoint",
        "importance": "standard",
        "message": f"{method} {path}",
        "environment": "production",
        "release": "v1.0.0",
        "sdk_version": "1.0.0",
        "platform": "python",
        "platform_version": "3.12",
        "attributes": {
            "endpoint": {
                "method": method,
                "path": path,
                "status_code": status,
                "duration_ms": round(rng.uniform(5.0, 500.0), 2),
            },
            "user_id": f"usr_{rng.randint(1000, 9999)}",
        },
    }


def _make_exception_template(rng: random.Random) -> dict:
    error_type = rng.choice(_ERROR_TYPES)
    message = f"Operation failed: code={rng.randint(1000, 9999)}"
    return {
        "level": "error",
        "log_type": "exception",
        "importance": rng.choice(["high", "critical"]),
        "message": message,
        "error_type": error_type,
        "error_message": message,
        "stack_trace": _STACK_TRACE_TEMPLATE.format(
            line1=rng.randint(20, 200),
            line2=rng.randint(20, 100),
            line3=rng.randint(50, 120),
            error_type=error_type,
            message=message,
        ),
        "environment": "production",
        "release": "v1.0.0",
        "sdk_version": "1.0.0",
        "platform": "python",
        "platform_version": "3.12",
        "attributes": {"retry_count": rng.randint(0, 3)},
    }


def build_batch_body(
    pool: list[dict],
    batch_size: int,
    rng: random.Random,
) -> bytes:
    now = datetime.datetime.now(datetime.timezone.utc)
    templates = rng.choices(pool, k=batch_size)
    logs = []
    for tmpl in templates:
        jitter = datetime.timedelta(seconds=rng.uniform(0, 2))
        entry = dict(tmpl)
        entry["timestamp"] = (now - jitter).isoformat()
        logs.append(entry)
    return json.dumps({"logs": logs}).encode()


def maybe_gzip(body: bytes, enabled: bool) -> tuple[bytes, dict]:
    if not enabled:
        return body, {}
    return gzip.compress(body, compresslevel=1), {"Content-Encoding": "gzip"}
