import base64
import binascii
import datetime
import hashlib
import ipaddress
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

_VALID_LOG_TYPES = {"console", "logger", "exception", "network", "database", "endpoint", "custom"}
_VALID_IMPORTANCE = {"critical", "high", "standard", "low"}
_HTTP_METHOD_KEYS = ("http.request.method", "http.method")
_HTTP_ROUTE_KEYS = ("http.route", "url.path")
_HTTP_STATUS_KEYS = ("http.response.status_code", "http.status_code")

# Any attribute key that might carry a client IP, from any SDK version. Every
# one of these is defensively re-truncated (or dropped) here regardless of
# what the SDK already did -- the gateway is the last point before storage,
# so it is the one place a raw address is guaranteed not to slip through.
_RAW_IP_ATTR_KEYS = ("client.address", "http.client_ip", "ledger.client.ip_prefix")

_CLIENT_ATTR_PREFIX = "ledger.client."

# Record attributes copied into their own log columns, per the log type that
# promotes them; keeping them in the JSONB as well stored stack traces twice.
_PROMOTED_LOG_ATTR_KEYS = ("ledger.log_id", "ledger.log_type", "ledger.importance")
_PROMOTED_LOG_ATTR_KEYS_BY_TYPE = {
    "exception": ("exception.type", "exception.message", "exception.stacktrace"),
    "endpoint": ("ledger.duration_ms",),
}

# Resource attributes that identify a metric series: OTel's service identity
# (service.instance.id keeps two processes' cumulative counters apart) plus
# the placement users group by. Everything else on a resource (SDK, process,
# OS details) describes the producer and is stored once in `resources`
# instead of in every point's tags.
_SERIES_IDENTITY_RESOURCE_KEYS = frozenset(
    {
        "service.name",
        "service.namespace",
        "service.version",
        "service.instance.id",
        "deployment.environment",
        "deployment.environment.name",
        "host.name",
        "k8s.namespace.name",
        "k8s.deployment.name",
        "k8s.pod.name",
        "cloud.region",
    }
)

_MAX_EXEMPLARS_PER_POINT = 5


class Translated(typing.NamedTuple):
    """Items for the ingestion service plus the resources they reference."""

    items: list
    # resource_hash -> canonical JSON of the resource attributes
    resources: dict[int, str]


def _register_resource(resources: dict[int, str], attrs: dict[str, typing.Any]) -> int | None:
    """Add `attrs` to `resources` under a stable 64-bit key and return the key.

    The key is derived from the canonical JSON, so every export of the same
    resource (from any gateway worker) maps to the same stored row.
    """
    if not attrs:
        return None
    canonical = json.dumps(attrs, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.blake2b(canonical.encode(), digest_size=8).digest()
    resource_hash = int.from_bytes(digest, "big", signed=True)
    resources[resource_hash] = canonical
    return resource_hash


def _truncate_ip_value(value: str) -> str | None:
    """Truncate an IP (raw, or already a CIDR prefix) to /24 (IPv4) / /48 (IPv6).

    Accepts an already-truncated `"1.2.3.0/24"`-shaped value too (re-truncating
    it is a no-op) so this is safe to apply unconditionally to any attribute
    that might hold either raw or pre-truncated client IP data. Returns None
    for anything that isn't a parseable address, so the caller can drop the
    attribute rather than store unrecognized garbage.
    """
    address_part = value.split("/", 1)[0]
    try:
        addr = ipaddress.ip_address(address_part)
    except ValueError:
        return None
    prefix_len = 24 if isinstance(addr, ipaddress.IPv4Address) else 48
    network = ipaddress.ip_network(f"{addr}/{prefix_len}", strict=False)
    return str(network)


def _sanitize_client_ip_attrs(attrs: dict[str, typing.Any]) -> None:
    for key in _RAW_IP_ATTR_KEYS:
        value = attrs.get(key)
        if not isinstance(value, str):
            continue
        truncated = _truncate_ip_value(value)
        if truncated is None:
            del attrs[key]
        else:
            attrs[key] = truncated


def _extract_client_data(
    attrs: dict[str, typing.Any],
) -> tuple[dict[str, typing.Any], str | None, str | None]:
    """Pop every `ledger.client.*` key out of `attrs` (mutating it) and split
    them into (nested client dict, channel, country). `channel`/`country` are
    promoted to typed `LogEntry` fields by the caller; everything else stays
    JSONB-only, nested under `attributes["client"]`.
    """
    client: dict[str, typing.Any] = {}
    channel: str | None = None
    country: str | None = None

    for key in list(attrs.keys()):
        if not key.startswith(_CLIENT_ATTR_PREFIX):
            continue
        value = attrs.pop(key)
        suffix = key[len(_CLIENT_ATTR_PREFIX) :]
        if suffix == "channel":
            channel = value if isinstance(value, str) else None
        elif suffix == "country":
            country = value if isinstance(value, str) else None
        else:
            client[suffix] = value

    return client, channel, country


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


def _hex_ids_to_base64(item: dict, id_keys: tuple[str, ...]) -> None:
    """OTLP/JSON writes trace/span ids as hex; protobuf's ParseDict expects base64."""
    for id_key in id_keys:
        raw = item.get(id_key)
        if not raw:
            continue
        try:
            item[id_key] = base64.b64encode(bytes.fromhex(raw)).decode("ascii")
        except (ValueError, binascii.Error):
            raise TranslationError(f"Invalid hex id for {id_key}: {raw}")


def _hexify_ids_in_json(data: dict) -> None:
    for resource_key in ("resourceSpans", "resourceLogs"):
        for resource_entry in data.get(resource_key, []):
            scope_key = "scopeSpans" if resource_key == "resourceSpans" else "scopeLogs"
            item_key = "spans" if resource_key == "resourceSpans" else "logRecords"
            for scope_entry in resource_entry.get(scope_key, []):
                for item in scope_entry.get(item_key, []):
                    _hex_ids_to_base64(item, _HEX_ID_KEYS)


_METRIC_DATA_KEYS = ("sum", "gauge", "histogram", "exponentialHistogram")


def _hexify_exemplar_ids_in_json(data: dict) -> None:
    for resource_entry in data.get("resourceMetrics", []):
        for scope_entry in resource_entry.get("scopeMetrics", []):
            for metric in scope_entry.get("metrics", []):
                for data_key in _METRIC_DATA_KEYS:
                    for point in (metric.get(data_key) or {}).get("dataPoints", []):
                        for exemplar in point.get("exemplars", []):
                            _hex_ids_to_base64(exemplar, ("traceId", "spanId"))


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

    _hexify_exemplar_ids_in_json(data)

    try:
        json_format.ParseDict(data, request, ignore_unknown_fields=True)
    except json_format.ParseError as e:
        raise TranslationError(f"Malformed OTLP/JSON metrics payload: {e}")

    return request


def otlp_spans_to_proto(request: trace_service_pb2.ExportTraceServiceRequest) -> Translated:
    spans: list[ingestion_pb2.Span] = []
    resources: dict[int, str] = {}

    for resource_spans in request.resource_spans:
        resource_attrs = _attributes_to_dict(resource_spans.resource.attributes)
        _sanitize_client_ip_attrs(resource_attrs)
        resource_hash = _register_resource(resources, resource_attrs)
        service_name = resource_attrs.get("service.name") or "unknown_service"

        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                spans.append(_translate_span(span, str(service_name), resource_hash))

    return Translated(spans, resources)


def _translate_span(span, service_name: str, resource_hash: int | None) -> ingestion_pb2.Span:
    attrs = _attributes_to_dict(span.attributes)
    proto_attrs: dict[str, str] = {}
    for key, value in attrs.items():
        proto_attrs[_SPAN_ATTRIBUTE_KEY_MAP.get(key, key)] = _stringify(value)

    if "http.client_ip" in proto_attrs:
        truncated = _truncate_ip_value(proto_attrs["http.client_ip"])
        if truncated is None:
            del proto_attrs["http.client_ip"]
        else:
            proto_attrs["http.client_ip"] = truncated

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

    translated = ingestion_pb2.Span(
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
    if resource_hash is not None:
        translated.resource_hash = resource_hash
    return translated


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


def otlp_logs_to_proto(request: logs_service_pb2.ExportLogsServiceRequest) -> Translated:
    logs: list[ingestion_pb2.LogEntry] = []
    resources: dict[int, str] = {}

    for resource_logs in request.resource_logs:
        resource_attrs = _attributes_to_dict(resource_logs.resource.attributes)
        _sanitize_client_ip_attrs(resource_attrs)
        resource_hash = _register_resource(resources, resource_attrs)

        for scope_logs in resource_logs.scope_logs:
            for log_record in scope_logs.log_records:
                logs.append(_translate_log_record(log_record, resource_attrs, resource_hash))

    return Translated(logs, resources)


def _translate_log_record(
    log_record, resource_attrs: dict[str, typing.Any], resource_hash: int | None
) -> ingestion_pb2.LogEntry:
    """Translate one record; its row keeps only record-level attributes.

    Resource attributes still drive the inferred and promoted fields (they
    are merged under the record's), but are stored once per resource and
    merged back in on read.
    """
    record_attrs = _attributes_to_dict(log_record.attributes)
    _sanitize_client_ip_attrs(record_attrs)
    client_data, client_channel, client_country = _extract_client_data(record_attrs)
    merged_attrs = {**resource_attrs, **record_attrs}

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

    attrs_out = dict(record_attrs)

    if log_type == "endpoint":
        endpoint = _build_endpoint_attributes(merged_attrs)
        if endpoint is None:
            log_type = "custom"
        else:
            attrs_out["endpoint"] = endpoint

    if client_data:
        attrs_out["client"] = client_data

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
    service_name = _truncate(_as_str_or_none(merged_attrs.get("service.name")), 255)

    _drop_promoted_attrs(attrs_out, log_type)

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
    if client_channel is not None:
        log_entry.client_channel = client_channel
    if client_country is not None:
        log_entry.client_country = client_country
    if service_name is not None:
        log_entry.service_name = service_name
    if resource_hash is not None:
        log_entry.resource_hash = resource_hash
    if log_record.trace_id:
        log_entry.trace_id = log_record.trace_id.hex()
    if log_record.span_id:
        log_entry.span_id = log_record.span_id.hex()
    if attrs_out:
        log_entry.attributes = json.dumps(attrs_out)

    return log_entry


def _drop_promoted_attrs(attrs: dict[str, typing.Any], log_type: str) -> None:
    """Remove record attributes that were moved into their own columns.

    Type-specific keys are only promoted for that final log type (an
    exception log missing its message is downgraded to custom, and then the
    attribute is the only copy), so only those are dropped.
    """
    for key in _PROMOTED_LOG_ATTR_KEYS + _PROMOTED_LOG_ATTR_KEYS_BY_TYPE.get(log_type, ()):
        attrs.pop(key, None)


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


class _SeriesOrigin(typing.NamedTuple):
    """What every data point of one ResourceMetrics shares."""

    identity_tags: dict[str, str]
    service_name: str
    resource_hash: int | None


def otlp_metrics_to_proto(request: metrics_service_pb2.ExportMetricsServiceRequest) -> Translated:
    points: list[ingestion_pb2.MetricPoint] = []
    resources: dict[int, str] = {}

    for resource_metrics in request.resource_metrics:
        resource_attrs = _attributes_to_dict(resource_metrics.resource.attributes)
        origin = _SeriesOrigin(
            identity_tags={
                key: _stringify(value)
                for key, value in resource_attrs.items()
                if key in _SERIES_IDENTITY_RESOURCE_KEYS
            },
            service_name=str(resource_attrs.get("service.name") or "unknown_service"),
            resource_hash=_register_resource(resources, resource_attrs),
        )
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                points.extend(_translate_metric(metric, origin))

    return Translated(points, resources)


def _translate_metric(metric, origin: _SeriesOrigin) -> list[ingestion_pb2.MetricPoint]:
    data_kind = metric.WhichOneof("data")
    if data_kind == "sum":
        temporality = _map_temporality(metric.sum.aggregation_temporality)
        return [
            _number_point(origin, metric.name, ingestion_pb2.SUM, dp, temporality)
            for dp in metric.sum.data_points
        ]
    if data_kind == "gauge":
        return [
            _number_point(
                origin, metric.name, ingestion_pb2.GAUGE, dp, ingestion_pb2.TEMPORALITY_UNSPECIFIED
            )
            for dp in metric.gauge.data_points
        ]
    if data_kind == "histogram":
        temporality = _map_temporality(metric.histogram.aggregation_temporality)
        return [
            _histogram_point(origin, metric.name, dp, temporality)
            for dp in metric.histogram.data_points
        ]
    if data_kind == "exponential_histogram":
        temporality = _map_temporality(metric.exponential_histogram.aggregation_temporality)
        return [
            _exponential_histogram_point(origin, metric.name, dp, temporality)
            for dp in metric.exponential_histogram.data_points
        ]
    if data_kind == "summary":
        return [_summary_point(origin, metric.name, dp) for dp in metric.summary.data_points]
    return []


def _map_temporality(otlp_temporality: int) -> int:
    # OTLP AggregationTemporality uses the same numbering as the internal enum
    # (1 delta, 2 cumulative); anything else means the exporter left it unset.
    if otlp_temporality == 1:
        return ingestion_pb2.TEMPORALITY_DELTA
    if otlp_temporality == 2:
        return ingestion_pb2.TEMPORALITY_CUMULATIVE
    return ingestion_pb2.TEMPORALITY_UNSPECIFIED


def _new_point(
    origin: _SeriesOrigin, name: str, metric_type: int, dp, temporality: int
) -> ingestion_pb2.MetricPoint:
    point_tags = {
        key: _stringify(value) for key, value in _attributes_to_dict(dp.attributes).items()
    }
    point = ingestion_pb2.MetricPoint(
        name=name[:255],
        type=metric_type,
        timestamp=_nano_to_iso(dp.time_unix_nano),
        tags={**origin.identity_tags, **point_tags},
        service_name=origin.service_name[:255],
        temporality=temporality,
    )
    if origin.resource_hash is not None:
        point.resource_hash = origin.resource_hash
    return point


def _exemplars(exemplars) -> list[ingestion_pb2.Exemplar]:
    """Exemplars that link to a trace; unsampled ones have nothing to open."""
    linked = []
    for exemplar in exemplars:
        if not exemplar.trace_id:
            continue
        value_kind = exemplar.WhichOneof("value")
        linked.append(
            ingestion_pb2.Exemplar(
                value=exemplar.as_double if value_kind == "as_double" else float(exemplar.as_int),
                timestamp=_nano_to_iso(exemplar.time_unix_nano),
                trace_id=exemplar.trace_id.hex(),
                span_id=exemplar.span_id.hex(),
            )
        )
        if len(linked) == _MAX_EXEMPLARS_PER_POINT:
            break
    return linked


def _number_point(
    origin: _SeriesOrigin, name: str, metric_type: int, dp, temporality: int
) -> ingestion_pb2.MetricPoint:
    point = _new_point(origin, name, metric_type, dp, temporality)
    point.value = dp.as_double if dp.WhichOneof("value") == "as_double" else float(dp.as_int)
    point.exemplars.extend(_exemplars(dp.exemplars))
    return point


def _histogram_point(
    origin: _SeriesOrigin, name: str, dp, temporality: int
) -> ingestion_pb2.MetricPoint:
    point = _new_point(origin, name, ingestion_pb2.HISTOGRAM, dp, temporality)
    point.bucket_counts.extend(float(c) for c in dp.bucket_counts)
    point.explicit_bounds.extend(dp.explicit_bounds)
    point.count = dp.count
    if dp.HasField("sum"):
        point.sum = dp.sum
    point.exemplars.extend(_exemplars(dp.exemplars))
    return point


def _exponential_histogram_point(
    origin: _SeriesOrigin, name: str, dp, temporality: int
) -> ingestion_pb2.MetricPoint:
    point = _new_point(origin, name, ingestion_pb2.EXPONENTIAL_HISTOGRAM, dp, temporality)
    point.count = dp.count
    if dp.HasField("sum"):
        point.sum = dp.sum
    point.scale = dp.scale
    point.zero_count = dp.zero_count
    point.positive_offset = dp.positive.offset
    point.positive_counts.extend(dp.positive.bucket_counts)
    point.negative_offset = dp.negative.offset
    point.negative_counts.extend(dp.negative.bucket_counts)
    point.exemplars.extend(_exemplars(dp.exemplars))
    return point


def _summary_point(origin: _SeriesOrigin, name: str, dp) -> ingestion_pb2.MetricPoint:
    # A summary's count and sum are running totals since process start by
    # definition (the data model has no temporality field), so they are
    # differenced like any cumulative series.
    point = _new_point(
        origin, name, ingestion_pb2.SUMMARY, dp, ingestion_pb2.TEMPORALITY_CUMULATIVE
    )
    point.count = dp.count
    point.sum = dp.sum
    point.quantiles.extend(q.quantile for q in dp.quantile_values)
    point.quantile_values.extend(q.value for q in dp.quantile_values)
    return point


def encode_export_response(message, content_type: str) -> bytes:
    if content_type == "application/x-protobuf":
        return message.SerializeToString()
    return json_format.MessageToJson(message, preserving_proto_field_name=False).encode("utf-8")


def normalize_content_type(raw: str | None) -> str:
    if raw is None:
        return ""
    return raw.split(";", 1)[0].strip().lower()
