import base64
import binascii
import datetime
import json
import typing

from google.protobuf import json_format
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from opentelemetry.proto.common.v1 import common_pb2

import gateway_service.proto.ingestion_pb2 as ingestion_pb2

_HEX_ID_KEYS = ("traceId", "spanId", "parentSpanId")

_SPAN_KIND_MAP = {
    0: ingestion_pb2.INTERNAL,
    1: ingestion_pb2.INTERNAL,
    2: ingestion_pb2.SERVER,
    3: ingestion_pb2.CLIENT,
    4: ingestion_pb2.PRODUCER,
    5: ingestion_pb2.CONSUMER,
}

_SPAN_ATTRIBUTE_KEY_MAP = {
    "http.request.method": "http.method",
    "http.response.status_code": "http.status_code",
    "url.full": "http.url",
    "url.path": "http.target",
    "client.address": "http.client_ip",
}

_SEVERITY_TEXT_MAP = {
    "trace": "debug",
    "debug": "debug",
    "info": "info",
    "warn": "warning",
    "warning": "warning",
    "error": "error",
    "fatal": "critical",
    "critical": "critical",
}

_VALID_LOG_TYPES = {"console", "logger", "exception", "database", "endpoint", "custom"}
_VALID_IMPORTANCE = {"critical", "high", "standard", "low"}
_HTTP_METHOD_KEYS = ("http.request.method", "http.method")
_HTTP_ROUTE_KEYS = ("http.route", "url.path")
_HTTP_STATUS_KEYS = ("http.response.status_code", "http.status_code")


class TranslationError(Exception):
    pass


def any_value_to_python(value: common_pb2.AnyValue) -> typing.Any:
    kind = value.WhichOneof("value")

    if kind is None:
        return None
    if kind == "string_value":
        return value.string_value
    if kind == "bool_value":
        return value.bool_value
    if kind == "int_value":
        return value.int_value
    if kind == "double_value":
        return value.double_value
    if kind == "bytes_value":
        return base64.b64encode(value.bytes_value).decode("ascii")
    if kind == "array_value":
        return [any_value_to_python(v) for v in value.array_value.values]
    if kind == "kvlist_value":
        return {kv.key: any_value_to_python(kv.value) for kv in value.kvlist_value.values}
    return None


def _attributes_to_dict(
    attributes: typing.Iterable[common_pb2.KeyValue],
) -> dict[str, typing.Any]:
    return {kv.key: any_value_to_python(kv.value) for kv in attributes}


def _stringify(value: typing.Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def _truncate(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    return value[:max_length]


def _hexify_ids_in_json(data: dict) -> None:
    for resource_key in ("resourceSpans", "resourceLogs"):
        for resource_entry in data.get(resource_key, []):
            scope_key = "scopeSpans" if resource_key == "resourceSpans" else "scopeLogs"
            item_key = "spans" if resource_key == "resourceSpans" else "logRecords"
            for scope_entry in resource_entry.get(scope_key, []):
                for item in scope_entry.get(item_key, []):
                    for id_key in _HEX_ID_KEYS:
                        raw = item.get(id_key)
                        if not raw:
                            continue
                        try:
                            item[id_key] = base64.b64encode(bytes.fromhex(raw)).decode("ascii")
                        except (ValueError, binascii.Error):
                            raise TranslationError(f"Invalid hex id for {id_key}: {raw}")


def decode_trace_request(
    body: bytes, content_type: str
) -> trace_service_pb2.ExportTraceServiceRequest:
    request = trace_service_pb2.ExportTraceServiceRequest()

    if content_type == "application/x-protobuf":
        try:
            request.ParseFromString(body)
        except Exception as e:
            raise TranslationError(f"Malformed protobuf body: {e}")
        return request

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise TranslationError(f"Malformed JSON body: {e}")

    _hexify_ids_in_json(data)

    try:
        json_format.ParseDict(data, request, ignore_unknown_fields=True)
    except json_format.ParseError as e:
        raise TranslationError(f"Malformed OTLP/JSON trace payload: {e}")

    return request


def decode_logs_request(
    body: bytes, content_type: str
) -> logs_service_pb2.ExportLogsServiceRequest:
    request = logs_service_pb2.ExportLogsServiceRequest()

    if content_type == "application/x-protobuf":
        try:
            request.ParseFromString(body)
        except Exception as e:
            raise TranslationError(f"Malformed protobuf body: {e}")
        return request

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise TranslationError(f"Malformed JSON body: {e}")

    _hexify_ids_in_json(data)

    try:
        json_format.ParseDict(data, request, ignore_unknown_fields=True)
    except json_format.ParseError as e:
        raise TranslationError(f"Malformed OTLP/JSON logs payload: {e}")

    return request


def decode_metrics_request(
    body: bytes, content_type: str
) -> metrics_service_pb2.ExportMetricsServiceRequest:
    request = metrics_service_pb2.ExportMetricsServiceRequest()

    if content_type == "application/x-protobuf":
        try:
            request.ParseFromString(body)
        except Exception as e:
            raise TranslationError(f"Malformed protobuf body: {e}")
        return request

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise TranslationError(f"Malformed JSON body: {e}")

    # Metric points carry no hex trace/span ids at the top level (unlike spans
    # and logs), so no id-hexify pass is needed before ParseDict here.
    try:
        json_format.ParseDict(data, request, ignore_unknown_fields=True)
    except json_format.ParseError as e:
        raise TranslationError(f"Malformed OTLP/JSON metrics payload: {e}")

    return request


def otlp_spans_to_proto(
    request: trace_service_pb2.ExportTraceServiceRequest,
) -> list[ingestion_pb2.Span]:
    spans: list[ingestion_pb2.Span] = []

    for resource_spans in request.resource_spans:
        resource_attrs = _attributes_to_dict(resource_spans.resource.attributes)
        service_name = resource_attrs.get("service.name") or "unknown_service"

        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                spans.append(_translate_span(span, str(service_name)))

    return spans


def _translate_span(span, service_name: str) -> ingestion_pb2.Span:
    attrs = _attributes_to_dict(span.attributes)
    proto_attrs: dict[str, str] = {}
    for key, value in attrs.items():
        proto_attrs[_SPAN_ATTRIBUTE_KEY_MAP.get(key, key)] = _stringify(value)

    events = [
        ingestion_pb2.SpanEvent(
            name=event.name,
            ts_unix_nano=event.time_unix_nano,
            attrs={
                key: _stringify(value)
                for key, value in _attributes_to_dict(event.attributes).items()
            },
        )
        for event in span.events
    ]

    return ingestion_pb2.Span(
        trace_id=span.trace_id.hex(),
        span_id=span.span_id.hex(),
        parent_span_id=span.parent_span_id.hex() if span.parent_span_id else "",
        name=span.name,
        kind=_SPAN_KIND_MAP.get(int(span.kind), ingestion_pb2.INTERNAL),
        start_unix_nano=span.start_time_unix_nano,
        end_unix_nano=span.end_time_unix_nano,
        status=int(span.status.code),
        status_message=span.status.message,
        attributes=proto_attrs,
        events=events,
        service_name=service_name,
    )


def _severity_to_level(severity_number: int, severity_text: str) -> str:
    if severity_number:
        if severity_number <= 8:
            return "debug"
        if severity_number <= 12:
            return "info"
        if severity_number <= 16:
            return "warning"
        if severity_number <= 20:
            return "error"
        return "critical"

    return _SEVERITY_TEXT_MAP.get(severity_text.lower(), "info")


def _infer_log_type(attrs: dict[str, typing.Any]) -> str:
    explicit = attrs.get("ledger.log_type")
    if isinstance(explicit, str) and explicit in _VALID_LOG_TYPES:
        return explicit

    if any(key.startswith("exception.") for key in attrs):
        return "exception"
    if any(key in attrs for key in _HTTP_METHOD_KEYS) and any(
        key in attrs for key in _HTTP_STATUS_KEYS
    ):
        return "endpoint"
    if "db.system" in attrs:
        return "database"
    if "code.filepath" in attrs or "code.function" in attrs:
        return "logger"
    return "custom"


def _infer_importance(attrs: dict[str, typing.Any], level: str) -> str:
    explicit = attrs.get("ledger.importance")
    if isinstance(explicit, str) and explicit in _VALID_IMPORTANCE:
        return explicit

    if level == "critical":
        return "critical"
    if level == "error":
        return "high"
    return "standard"


def _first_present(attrs: dict[str, typing.Any], keys: tuple[str, ...]) -> typing.Any:
    for key in keys:
        if key in attrs:
            return attrs[key]
    return None


def _build_endpoint_attributes(
    attrs: dict[str, typing.Any],
) -> dict[str, typing.Any] | None:
    method = _first_present(attrs, _HTTP_METHOD_KEYS)
    path = _first_present(attrs, _HTTP_ROUTE_KEYS)
    status_code = _first_present(attrs, _HTTP_STATUS_KEYS)
    duration_ms = attrs.get("ledger.duration_ms")

    if method is None or path is None or status_code is None or duration_ms is None:
        return None

    endpoint: dict[str, typing.Any] = {
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": duration_ms,
    }

    query_params = attrs.get("url.query")
    if query_params:
        endpoint["query_params"] = query_params

    path_params = attrs.get("ledger.path_params")
    if path_params:
        if isinstance(path_params, str):
            try:
                path_params = json.loads(path_params)
            except json.JSONDecodeError:
                pass
        endpoint["path_params"] = path_params

    response_body = attrs.get("ledger.response_body")
    if response_body:
        endpoint["response_body"] = response_body

    return endpoint


def otlp_logs_to_proto(
    request: logs_service_pb2.ExportLogsServiceRequest,
) -> list[ingestion_pb2.LogEntry]:
    logs: list[ingestion_pb2.LogEntry] = []

    for resource_logs in request.resource_logs:
        resource_attrs = _attributes_to_dict(resource_logs.resource.attributes)

        for scope_logs in resource_logs.scope_logs:
            for log_record in scope_logs.log_records:
                logs.append(_translate_log_record(log_record, resource_attrs))

    return logs


def _translate_log_record(
    log_record, resource_attrs: dict[str, typing.Any]
) -> ingestion_pb2.LogEntry:
    merged_attrs = {**resource_attrs, **_attributes_to_dict(log_record.attributes)}

    time_unix_nano = (
        log_record.time_unix_nano
        or log_record.observed_time_unix_nano
        or int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1e9)
    )
    timestamp = datetime.datetime.fromtimestamp(
        time_unix_nano / 1e9, tz=datetime.timezone.utc
    ).isoformat()

    level = _severity_to_level(int(log_record.severity_number), log_record.severity_text)
    log_type = _infer_log_type(merged_attrs)
    importance = _infer_importance(merged_attrs, level)

    body = any_value_to_python(log_record.body)
    message = _truncate(_stringify(body) if body is not None else None, 10000)

    error_type = None
    error_message = None
    stack_trace = None

    if log_type == "exception":
        error_type = _truncate(merged_attrs.get("exception.type"), 255)
        error_message = _truncate(merged_attrs.get("exception.message"), 5000)
        stack_trace = _truncate(merged_attrs.get("exception.stacktrace"), 50000)
        if not error_type or not error_message:
            log_type = "custom"

    attrs_out = dict(merged_attrs)

    if log_type == "endpoint":
        endpoint = _build_endpoint_attributes(merged_attrs)
        if endpoint is None:
            log_type = "custom"
        else:
            attrs_out["endpoint"] = endpoint

    if log_record.trace_id:
        attrs_out["trace_id"] = log_record.trace_id.hex()
    if log_record.span_id:
        attrs_out["span_id"] = log_record.span_id.hex()

    environment = _truncate(
        _as_str_or_none(
            merged_attrs.get("deployment.environment.name")
            or merged_attrs.get("deployment.environment")
        ),
        20,
    )
    release = _truncate(_as_str_or_none(merged_attrs.get("service.version")), 100)
    sdk_version = _truncate(
        _as_str_or_none(
            merged_attrs.get("ledger.sdk_version") or merged_attrs.get("telemetry.sdk.version")
        ),
        20,
    )
    platform = _truncate(_as_str_or_none(merged_attrs.get("telemetry.sdk.language")), 50)
    platform_version = _truncate(
        _as_str_or_none(
            merged_attrs.get("ledger.platform_version")
            or merged_attrs.get("process.runtime.version")
        ),
        50,
    )
    log_id = _truncate(_as_str_or_none(merged_attrs.get("ledger.log_id")), 64)

    log_entry = ingestion_pb2.LogEntry(
        timestamp=timestamp,
        level=level,
        log_type=log_type,
        importance=importance,
    )

    if message is not None:
        log_entry.message = message
    if error_type is not None:
        log_entry.error_type = error_type
    if error_message is not None:
        log_entry.error_message = error_message
    if stack_trace is not None:
        log_entry.stack_trace = stack_trace
    if environment is not None:
        log_entry.environment = environment
    if release is not None:
        log_entry.release = release
    if sdk_version is not None:
        log_entry.sdk_version = sdk_version
    if platform is not None:
        log_entry.platform = platform
    if platform_version is not None:
        log_entry.platform_version = platform_version
    if log_id is not None:
        log_entry.log_id = log_id
    if attrs_out:
        log_entry.attributes = json.dumps(attrs_out)

    return log_entry


def _as_str_or_none(value: typing.Any) -> str | None:
    if value is None:
        return None
    return _stringify(value)


def _nano_to_iso(time_unix_nano: int) -> str:
    if not time_unix_nano:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()
    return datetime.datetime.fromtimestamp(
        time_unix_nano / 1e9, tz=datetime.timezone.utc
    ).isoformat()


def _merge_point_tags(resource_attrs: dict[str, typing.Any], point_attributes) -> dict[str, str]:
    merged = {**resource_attrs, **_attributes_to_dict(point_attributes)}
    return {key: _stringify(value) for key, value in merged.items()}


def otlp_metrics_to_proto(
    request: metrics_service_pb2.ExportMetricsServiceRequest,
) -> list[ingestion_pb2.MetricPoint]:
    points: list[ingestion_pb2.MetricPoint] = []

    for resource_metrics in request.resource_metrics:
        resource_attrs = _attributes_to_dict(resource_metrics.resource.attributes)
        service_name = str(resource_attrs.get("service.name") or "unknown_service")

        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                data_kind = metric.WhichOneof("data")

                if data_kind == "sum":
                    for dp in metric.sum.data_points:
                        points.append(
                            _translate_number_point(
                                metric.name, ingestion_pb2.SUM, dp, resource_attrs, service_name
                            )
                        )
                elif data_kind == "gauge":
                    for dp in metric.gauge.data_points:
                        points.append(
                            _translate_number_point(
                                metric.name, ingestion_pb2.GAUGE, dp, resource_attrs, service_name
                            )
                        )
                elif data_kind == "histogram":
                    for dp in metric.histogram.data_points:
                        points.append(
                            _translate_histogram_point(
                                metric.name, dp, resource_attrs, service_name
                            )
                        )
                # exponential_histogram and summary metric types are not yet
                # supported by the internal MetricPoint model and are skipped.

    return points


def _translate_number_point(
    name: str,
    metric_type,
    dp,
    resource_attrs: dict[str, typing.Any],
    service_name: str,
) -> ingestion_pb2.MetricPoint:
    value = dp.as_double if dp.WhichOneof("value") == "as_double" else float(dp.as_int)

    point = ingestion_pb2.MetricPoint(
        name=name[:255],
        type=metric_type,
        timestamp=_nano_to_iso(dp.time_unix_nano),
        tags=_merge_point_tags(resource_attrs, dp.attributes),
        service_name=service_name[:255],
    )
    point.value = value
    return point


def _translate_histogram_point(
    name: str,
    dp,
    resource_attrs: dict[str, typing.Any],
    service_name: str,
) -> ingestion_pb2.MetricPoint:
    point = ingestion_pb2.MetricPoint(
        name=name[:255],
        type=ingestion_pb2.HISTOGRAM,
        timestamp=_nano_to_iso(dp.time_unix_nano),
        tags=_merge_point_tags(resource_attrs, dp.attributes),
        service_name=service_name[:255],
        bucket_counts=[float(c) for c in dp.bucket_counts],
        explicit_bounds=list(dp.explicit_bounds),
    )
    point.count = dp.count
    if dp.HasField("sum"):
        point.sum = dp.sum
    return point


def encode_export_response(message, content_type: str) -> bytes:
    if content_type == "application/x-protobuf":
        return message.SerializeToString()
    return json_format.MessageToJson(message, preserving_proto_field_name=False).encode("utf-8")


def normalize_content_type(raw: str | None) -> str:
    if raw is None:
        return ""
    return raw.split(";", 1)[0].strip().lower()
