import datetime
import gzip
import json
import random

from google.protobuf import message as protobuf_message
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.logs.v1 import logs_pb2
from opentelemetry.proto.resource.v1 import resource_pb2

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
    ["debug"] * 25 + ["info"] * 30 + ["warning"] * 20 + ["error"] * 15 + ["critical"] * 10
)

_SEVERITY_NUMBER_BY_LEVEL = {
    "debug": 5,
    "info": 9,
    "warning": 13,
    "error": 17,
    "critical": 21,
}

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
        "attributes": {
            "http.request.method": method,
            "http.route": path,
            "http.response.status_code": status,
            "ledger.duration_ms": round(rng.uniform(5.0, 500.0), 2),
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
        "attributes": {
            "exception.type": error_type,
            "exception.message": message,
            "exception.stacktrace": _STACK_TRACE_TEMPLATE.format(
                line1=rng.randint(20, 200),
                line2=rng.randint(20, 100),
                line3=rng.randint(50, 120),
                error_type=error_type,
                message=message,
            ),
            "retry_count": rng.randint(0, 3),
        },
    }


def _any_value_json(value) -> dict:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def _template_to_log_record_json(
    template: dict, timestamp: datetime.datetime, log_id: str | None
) -> dict:
    attributes = [
        {"key": "ledger.log_type", "value": _any_value_json(template["log_type"])},
        {"key": "ledger.importance", "value": _any_value_json(template["importance"])},
    ]
    for key, value in template.get("attributes", {}).items():
        attributes.append({"key": key, "value": _any_value_json(value)})
    if log_id is not None:
        attributes.append({"key": "ledger.log_id", "value": _any_value_json(log_id)})

    return {
        "timeUnixNano": str(int(timestamp.timestamp() * 1e9)),
        "severityNumber": _SEVERITY_NUMBER_BY_LEVEL.get(template["level"], 9),
        "severityText": template["level"].upper(),
        "body": {"stringValue": template["message"]},
        "attributes": attributes,
    }


def _build_batch_json(
    pool: list[dict],
    batch_size: int,
    rng: random.Random,
    log_ids: list[str] | None,
) -> bytes:
    now = datetime.datetime.now(datetime.timezone.utc)
    templates = rng.choices(pool, k=batch_size)
    log_records = []
    for i, tmpl in enumerate(templates):
        jitter = datetime.timedelta(seconds=rng.uniform(0, 2))
        log_id = log_ids[i] if log_ids is not None else None
        log_records.append(_template_to_log_record_json(tmpl, now - jitter, log_id))

    body = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": _any_value_json("benchmark")},
                        {
                            "key": "deployment.environment.name",
                            "value": _any_value_json("production"),
                        },
                        {"key": "service.version", "value": _any_value_json("v1.0.0")},
                        {"key": "telemetry.sdk.language", "value": _any_value_json("python")},
                    ]
                },
                "scopeLogs": [{"logRecords": log_records}],
            }
        ]
    }
    return json.dumps(body).encode()


def _any_value_pb(value) -> common_pb2.AnyValue:
    if isinstance(value, bool):
        return common_pb2.AnyValue(bool_value=value)
    if isinstance(value, int):
        return common_pb2.AnyValue(int_value=value)
    if isinstance(value, float):
        return common_pb2.AnyValue(double_value=value)
    return common_pb2.AnyValue(string_value=str(value))


def _template_to_log_record_pb(
    template: dict, timestamp: datetime.datetime, log_id: str | None
) -> logs_pb2.LogRecord:
    attributes = [
        common_pb2.KeyValue(key="ledger.log_type", value=_any_value_pb(template["log_type"])),
        common_pb2.KeyValue(key="ledger.importance", value=_any_value_pb(template["importance"])),
    ]
    for key, value in template.get("attributes", {}).items():
        attributes.append(common_pb2.KeyValue(key=key, value=_any_value_pb(value)))
    if log_id is not None:
        attributes.append(common_pb2.KeyValue(key="ledger.log_id", value=_any_value_pb(log_id)))

    return logs_pb2.LogRecord(
        time_unix_nano=int(timestamp.timestamp() * 1e9),
        severity_number=_SEVERITY_NUMBER_BY_LEVEL.get(template["level"], 9),
        severity_text=template["level"].upper(),
        body=common_pb2.AnyValue(string_value=template["message"]),
        attributes=attributes,
    )


def _build_batch_protobuf(
    pool: list[dict],
    batch_size: int,
    rng: random.Random,
    log_ids: list[str] | None,
) -> bytes:
    now = datetime.datetime.now(datetime.timezone.utc)
    templates = rng.choices(pool, k=batch_size)
    log_records = []
    for i, tmpl in enumerate(templates):
        jitter = datetime.timedelta(seconds=rng.uniform(0, 2))
        log_id = log_ids[i] if log_ids is not None else None
        log_records.append(_template_to_log_record_pb(tmpl, now - jitter, log_id))

    request = logs_service_pb2.ExportLogsServiceRequest(
        resource_logs=[
            logs_pb2.ResourceLogs(
                resource=resource_pb2.Resource(
                    attributes=[
                        common_pb2.KeyValue(key="service.name", value=_any_value_pb("benchmark")),
                        common_pb2.KeyValue(
                            key="deployment.environment.name",
                            value=_any_value_pb("production"),
                        ),
                        common_pb2.KeyValue(key="service.version", value=_any_value_pb("v1.0.0")),
                        common_pb2.KeyValue(
                            key="telemetry.sdk.language", value=_any_value_pb("python")
                        ),
                    ]
                ),
                scope_logs=[logs_pb2.ScopeLogs(log_records=log_records)],
            )
        ]
    )
    return request.SerializeToString()


def build_batch_body(
    pool: list[dict],
    batch_size: int,
    rng: random.Random,
    wire: str = "protobuf",
    log_ids: list[str] | None = None,
) -> tuple[bytes, str]:
    """
    Returns (body_bytes, content_type). `wire="protobuf"` matches the OTLP/HTTP
    spec default and what real OTel SDKs send; `wire="json"` exercises the
    slower json_format.ParseDict decode path some clients still use.
    """
    if wire == "protobuf":
        return _build_batch_protobuf(pool, batch_size, rng, log_ids), "application/x-protobuf"
    return _build_batch_json(pool, batch_size, rng, log_ids), "application/json"


def maybe_gzip(body: bytes, enabled: bool) -> tuple[bytes, dict]:
    if not enabled:
        return body, {}
    return gzip.compress(body, compresslevel=1), {"Content-Encoding": "gzip"}


def parse_partial_success(content_type: str, raw_body: bytes) -> int:
    """
    Parses a gateway response's rejected-record count. JSON responses always
    come back as OTLP/JSON regardless of what wire the request used; protobuf
    responses only happen when the client sent protobuf and didn't set an
    Accept header favoring JSON (the gateway mirrors the request's format).
    """
    if content_type == "application/x-protobuf":
        try:
            resp = logs_service_pb2.ExportLogsServiceResponse()
            resp.ParseFromString(raw_body)
            return int(resp.partial_success.rejected_log_records)
        except protobuf_message.DecodeError:
            return 0
    try:
        data = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    return int(data.get("partialSuccess", {}).get("rejectedLogRecords", 0))
