import json

import pytest
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

import gateway_service.proto.ingestion_pb2 as ingestion_pb2
import gateway_service.services.otlp_translator as otlp_translator

TRACE_ID = bytes.fromhex("a" * 32)
SPAN_ID = bytes.fromhex("b" * 16)


def _kv(key: str, value: common_pb2.AnyValue) -> common_pb2.KeyValue:
    return common_pb2.KeyValue(key=key, value=value)


def _sv(value: str) -> common_pb2.AnyValue:
    return common_pb2.AnyValue(string_value=value)


class TestAnyValueToPython:
    def test_string_value(self):
        assert otlp_translator.any_value_to_python(_sv("hello")) == "hello"

    def test_bool_value(self):
        value = common_pb2.AnyValue(bool_value=True)
        assert otlp_translator.any_value_to_python(value) is True

    def test_int_value(self):
        value = common_pb2.AnyValue(int_value=42)
        assert otlp_translator.any_value_to_python(value) == 42

    def test_double_value(self):
        value = common_pb2.AnyValue(double_value=1.5)
        assert otlp_translator.any_value_to_python(value) == 1.5

    def test_bytes_value(self):
        value = common_pb2.AnyValue(bytes_value=b"abc")
        result = otlp_translator.any_value_to_python(value)
        assert result == "YWJj"

    def test_array_value(self):
        value = common_pb2.AnyValue(array_value=common_pb2.ArrayValue(values=[_sv("a"), _sv("b")]))
        assert otlp_translator.any_value_to_python(value) == ["a", "b"]

    def test_kvlist_value(self):
        value = common_pb2.AnyValue(
            kvlist_value=common_pb2.KeyValueList(values=[_kv("k", _sv("v"))])
        )
        assert otlp_translator.any_value_to_python(value) == {"k": "v"}

    def test_unset_value(self):
        assert otlp_translator.any_value_to_python(common_pb2.AnyValue()) is None


class TestSpanTranslation:
    def _build_request(self, kind, status_code=trace_pb2.Status.STATUS_CODE_OK):
        request = trace_service_pb2.ExportTraceServiceRequest()
        rs = request.resource_spans.add()
        rs.resource.attributes.append(_kv("service.name", _sv("checkout")))
        ss = rs.scope_spans.add()
        span = ss.spans.add()
        span.trace_id = TRACE_ID
        span.span_id = SPAN_ID
        span.name = "GET /users"
        span.kind = kind
        span.start_time_unix_nano = 1_000_000_000
        span.end_time_unix_nano = 1_000_500_000
        span.status.code = status_code
        span.attributes.append(_kv("http.request.method", _sv("GET")))
        span.attributes.append(_kv("http.response.status_code", common_pb2.AnyValue(int_value=200)))
        event = span.events.add()
        event.name = "exception"
        event.time_unix_nano = 1_000_100_000
        event.attributes.append(_kv("exception.type", _sv("ValueError")))
        return request

    def test_ids_hex_encoded(self):
        request = self._build_request(trace_pb2.Span.SPAN_KIND_SERVER)
        spans = otlp_translator.otlp_spans_to_proto(request)
        assert spans[0].trace_id == "a" * 32
        assert spans[0].span_id == "b" * 16

    def test_service_name_from_resource(self):
        request = self._build_request(trace_pb2.Span.SPAN_KIND_SERVER)
        spans = otlp_translator.otlp_spans_to_proto(request)
        assert spans[0].service_name == "checkout"

    def test_missing_service_name_defaults(self):
        request = trace_service_pb2.ExportTraceServiceRequest()
        rs = request.resource_spans.add()
        ss = rs.scope_spans.add()
        span = ss.spans.add()
        span.trace_id = TRACE_ID
        span.span_id = SPAN_ID
        spans = otlp_translator.otlp_spans_to_proto(request)
        assert spans[0].service_name == "unknown_service"

    @pytest.mark.parametrize(
        "otlp_kind,expected",
        [
            (trace_pb2.Span.SPAN_KIND_UNSPECIFIED, ingestion_pb2.INTERNAL),
            (trace_pb2.Span.SPAN_KIND_INTERNAL, ingestion_pb2.INTERNAL),
            (trace_pb2.Span.SPAN_KIND_SERVER, ingestion_pb2.SERVER),
            (trace_pb2.Span.SPAN_KIND_CLIENT, ingestion_pb2.CLIENT),
            (trace_pb2.Span.SPAN_KIND_PRODUCER, ingestion_pb2.PRODUCER),
            (trace_pb2.Span.SPAN_KIND_CONSUMER, ingestion_pb2.CONSUMER),
        ],
    )
    def test_kind_mapping(self, otlp_kind, expected):
        request = self._build_request(otlp_kind)
        spans = otlp_translator.otlp_spans_to_proto(request)
        assert spans[0].kind == expected

    def test_status_passthrough(self):
        request = self._build_request(
            trace_pb2.Span.SPAN_KIND_SERVER, trace_pb2.Status.STATUS_CODE_ERROR
        )
        spans = otlp_translator.otlp_spans_to_proto(request)
        assert spans[0].status == ingestion_pb2.ERROR

    def test_attribute_key_normalization(self):
        request = self._build_request(trace_pb2.Span.SPAN_KIND_SERVER)
        spans = otlp_translator.otlp_spans_to_proto(request)
        assert spans[0].attributes["http.method"] == "GET"
        assert spans[0].attributes["http.status_code"] == "200"

    def test_events_translated(self):
        request = self._build_request(trace_pb2.Span.SPAN_KIND_SERVER)
        spans = otlp_translator.otlp_spans_to_proto(request)
        assert len(spans[0].events) == 1
        assert spans[0].events[0].name == "exception"
        assert spans[0].events[0].attrs["exception.type"] == "ValueError"


class TestDecodeTraceRequest:
    def test_protobuf_round_trip(self):
        request = trace_service_pb2.ExportTraceServiceRequest()
        rs = request.resource_spans.add()
        rs.resource.attributes.append(_kv("service.name", _sv("svc")))
        ss = rs.scope_spans.add()
        span = ss.spans.add()
        span.trace_id = TRACE_ID
        span.span_id = SPAN_ID
        span.name = "op"

        decoded = otlp_translator.decode_trace_request(
            request.SerializeToString(), "application/x-protobuf"
        )
        assert decoded.resource_spans[0].scope_spans[0].spans[0].name == "op"

    def test_json_hex_ids_decoded(self):
        data = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [{"key": "service.name", "value": {"stringValue": "svc"}}]
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "traceId": "a" * 32,
                                    "spanId": "b" * 16,
                                    "name": "POST /x",
                                    "kind": "SPAN_KIND_CLIENT",
                                    "startTimeUnixNano": "1000000000",
                                    "endTimeUnixNano": "1000500000",
                                    "status": {"code": "STATUS_CODE_ERROR", "message": "boom"},
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        body = json.dumps(data).encode()
        decoded = otlp_translator.decode_trace_request(body, "application/json")
        spans = otlp_translator.otlp_spans_to_proto(decoded)
        assert spans[0].trace_id == "a" * 32
        assert spans[0].span_id == "b" * 16
        assert spans[0].kind == ingestion_pb2.CLIENT
        assert spans[0].status == ingestion_pb2.ERROR
        assert spans[0].status_message == "boom"

    def test_malformed_json_rejected(self):
        with pytest.raises(otlp_translator.TranslationError):
            otlp_translator.decode_trace_request(b"{not json", "application/json")

    def test_malformed_protobuf_rejected(self):
        with pytest.raises(otlp_translator.TranslationError):
            otlp_translator.decode_trace_request(b"\xff\xff\xff", "application/x-protobuf")

    def test_invalid_hex_id_rejected(self):
        data = {
            "resourceSpans": [
                {"scopeSpans": [{"spans": [{"traceId": "not-hex", "spanId": "b" * 16}]}]}
            ]
        }
        with pytest.raises(otlp_translator.TranslationError):
            otlp_translator.decode_trace_request(json.dumps(data).encode(), "application/json")


class TestLogTranslation:
    def _build_log_record(self, severity_number=9, severity_text="", attrs=None, body="hello"):
        request = logs_service_pb2.ExportLogsServiceRequest()
        rl = request.resource_logs.add()
        rl.resource.attributes.append(_kv("service.name", _sv("checkout")))
        sl = rl.scope_logs.add()
        record = sl.log_records.add()
        record.time_unix_nano = 1_700_000_000_000_000_000
        record.severity_number = severity_number
        record.severity_text = severity_text
        if body is not None:
            record.body.string_value = body
        for key, value in (attrs or {}).items():
            record.attributes.append(_kv(key, _sv(value)))
        return request

    @pytest.mark.parametrize(
        "severity_number,expected_level",
        [
            (1, "debug"),
            (8, "debug"),
            (9, "info"),
            (12, "info"),
            (13, "warning"),
            (16, "warning"),
            (17, "error"),
            (20, "error"),
            (21, "critical"),
            (24, "critical"),
        ],
    )
    def test_severity_number_mapping(self, severity_number, expected_level):
        request = self._build_log_record(severity_number=severity_number)
        logs = otlp_translator.otlp_logs_to_proto(request)
        assert logs[0].level == expected_level

    @pytest.mark.parametrize(
        "severity_text,expected_level",
        [("warn", "warning"), ("fatal", "critical"), ("error", "error")],
    )
    def test_severity_text_fallback(self, severity_text, expected_level):
        request = self._build_log_record(severity_number=0, severity_text=severity_text)
        logs = otlp_translator.otlp_logs_to_proto(request)
        assert logs[0].level == expected_level

    def test_exception_log_type_inferred(self):
        request = self._build_log_record(
            attrs={"exception.type": "ValueError", "exception.message": "bad"}
        )
        logs = otlp_translator.otlp_logs_to_proto(request)
        assert logs[0].log_type == "exception"
        assert logs[0].error_type == "ValueError"
        assert logs[0].error_message == "bad"

    def test_exception_missing_fields_downgrades_to_custom(self):
        request = self._build_log_record(attrs={"exception.type": "ValueError"})
        logs = otlp_translator.otlp_logs_to_proto(request)
        assert logs[0].log_type == "custom"

    def test_database_log_type_inferred(self):
        request = self._build_log_record(attrs={"db.system": "postgresql"})
        logs = otlp_translator.otlp_logs_to_proto(request)
        assert logs[0].log_type == "database"

    def test_logger_log_type_inferred(self):
        request = self._build_log_record(attrs={"code.function": "handler"})
        logs = otlp_translator.otlp_logs_to_proto(request)
        assert logs[0].log_type == "logger"

    def test_default_log_type_custom(self):
        request = self._build_log_record()
        logs = otlp_translator.otlp_logs_to_proto(request)
        assert logs[0].log_type == "custom"

    def test_explicit_ledger_log_type_wins(self):
        request = self._build_log_record(attrs={"ledger.log_type": "console"})
        logs = otlp_translator.otlp_logs_to_proto(request)
        assert logs[0].log_type == "console"

    def test_endpoint_synthesis_complete(self):
        request = self._build_log_record(
            attrs={
                "http.request.method": "GET",
                "http.route": "/users/:id",
                "http.response.status_code": "200",
                "ledger.duration_ms": "12.5",
            }
        )
        logs = otlp_translator.otlp_logs_to_proto(request)
        assert logs[0].log_type == "endpoint"
        attributes = json.loads(logs[0].attributes)
        assert attributes["endpoint"]["method"] == "GET"
        assert attributes["endpoint"]["path"] == "/users/:id"
        assert attributes["endpoint"]["status_code"] == "200"
        assert attributes["endpoint"]["duration_ms"] == "12.5"

    def test_endpoint_missing_fields_downgrades_to_custom(self):
        request = self._build_log_record(
            attrs={"http.request.method": "GET", "http.response.status_code": "200"}
        )
        logs = otlp_translator.otlp_logs_to_proto(request)
        assert logs[0].log_type == "custom"

    def test_importance_derived_from_level(self):
        request = self._build_log_record(severity_number=21)
        logs = otlp_translator.otlp_logs_to_proto(request)
        assert logs[0].importance == "critical"

    def test_resource_metadata_mapped(self):
        request = logs_service_pb2.ExportLogsServiceRequest()
        rl = request.resource_logs.add()
        rl.resource.attributes.append(_kv("service.name", _sv("svc")))
        rl.resource.attributes.append(_kv("service.version", _sv("1.2.3")))
        rl.resource.attributes.append(_kv("deployment.environment.name", _sv("production")))
        rl.resource.attributes.append(_kv("telemetry.sdk.language", _sv("python")))
        sl = rl.scope_logs.add()
        record = sl.log_records.add()
        record.severity_number = 9
        record.body.string_value = "hi"

        logs = otlp_translator.otlp_logs_to_proto(request)
        assert logs[0].environment == "production"
        assert logs[0].release == "1.2.3"
        assert logs[0].platform == "python"

    def test_trace_and_span_id_added_to_attributes(self):
        request = self._build_log_record()
        request.resource_logs[0].scope_logs[0].log_records[0].trace_id = TRACE_ID
        request.resource_logs[0].scope_logs[0].log_records[0].span_id = SPAN_ID

        logs = otlp_translator.otlp_logs_to_proto(request)
        attributes = json.loads(logs[0].attributes)
        assert attributes["trace_id"] == "a" * 32
        assert attributes["span_id"] == "b" * 16

    def test_message_truncated(self):
        request = self._build_log_record(body="x" * 20000)
        logs = otlp_translator.otlp_logs_to_proto(request)
        assert len(logs[0].message) == 10000

    def test_ledger_log_id_mapped_to_proto_field(self):
        request = self._build_log_record(attrs={"ledger.log_id": "abc123"})
        logs = otlp_translator.otlp_logs_to_proto(request)
        assert logs[0].log_id == "abc123"

    def test_missing_ledger_log_id_leaves_field_unset(self):
        request = self._build_log_record()
        logs = otlp_translator.otlp_logs_to_proto(request)
        assert not logs[0].HasField("log_id")


class TestDecodeLogsRequest:
    def test_json_hex_ids_decoded(self):
        data = {
            "resourceLogs": [
                {
                    "scopeLogs": [
                        {
                            "logRecords": [
                                {
                                    "traceId": "a" * 32,
                                    "spanId": "b" * 16,
                                    "severityNumber": 9,
                                    "body": {"stringValue": "hi"},
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        body = json.dumps(data).encode()
        decoded = otlp_translator.decode_logs_request(body, "application/json")
        logs = otlp_translator.otlp_logs_to_proto(decoded)
        attributes = json.loads(logs[0].attributes)
        assert attributes["trace_id"] == "a" * 32
        assert attributes["span_id"] == "b" * 16

    def test_malformed_json_rejected(self):
        with pytest.raises(otlp_translator.TranslationError):
            otlp_translator.decode_logs_request(b"{not json", "application/json")


class TestMetricTranslation:
    def _build_request(self, metric: dict) -> metrics_service_pb2.ExportMetricsServiceRequest:
        data = {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "checkout"}}
                        ]
                    },
                    "scopeMetrics": [{"metrics": [metric]}],
                }
            ]
        }
        request = metrics_service_pb2.ExportMetricsServiceRequest()
        json_format_body = json.dumps(data).encode()
        return otlp_translator.decode_metrics_request(json_format_body, "application/json")

    def test_gauge_point_translated(self):
        request = self._build_request(
            {
                "name": "queue.depth",
                "gauge": {
                    "dataPoints": [
                        {
                            "timeUnixNano": "1000000000",
                            "asDouble": 42.5,
                            "attributes": [{"key": "region", "value": {"stringValue": "us"}}],
                        }
                    ]
                },
            }
        )
        points = otlp_translator.otlp_metrics_to_proto(request)
        assert len(points) == 1
        assert points[0].name == "queue.depth"
        assert points[0].type == ingestion_pb2.GAUGE
        assert points[0].value == 42.5
        assert points[0].service_name == "checkout"
        assert points[0].tags["region"] == "us"
        assert points[0].tags["service.name"] == "checkout"

    def test_sum_point_translated(self):
        request = self._build_request(
            {
                "name": "requests.count",
                "sum": {
                    "dataPoints": [{"timeUnixNano": "1000000000", "asInt": "7"}],
                    "aggregationTemporality": "AGGREGATION_TEMPORALITY_CUMULATIVE",
                    "isMonotonic": True,
                },
            }
        )
        points = otlp_translator.otlp_metrics_to_proto(request)
        assert len(points) == 1
        assert points[0].type == ingestion_pb2.SUM
        assert points[0].value == 7.0

    def test_histogram_point_translated(self):
        request = self._build_request(
            {
                "name": "request.duration",
                "histogram": {
                    "dataPoints": [
                        {
                            "timeUnixNano": "1000000000",
                            "count": "10",
                            "sum": 55.0,
                            "bucketCounts": ["2", "5", "3"],
                            "explicitBounds": [1.0, 5.0],
                        }
                    ],
                    "aggregationTemporality": "AGGREGATION_TEMPORALITY_CUMULATIVE",
                },
            }
        )
        points = otlp_translator.otlp_metrics_to_proto(request)
        assert len(points) == 1
        point = points[0]
        assert point.type == ingestion_pb2.HISTOGRAM
        assert point.count == 10
        assert point.sum == 55.0
        assert list(point.bucket_counts) == [2.0, 5.0, 3.0]
        assert list(point.explicit_bounds) == [1.0, 5.0]

    def test_multiple_data_points_produce_multiple_proto_points(self):
        request = self._build_request(
            {
                "name": "queue.depth",
                "gauge": {
                    "dataPoints": [
                        {"timeUnixNano": "1000000000", "asDouble": 1.0},
                        {"timeUnixNano": "2000000000", "asDouble": 2.0},
                    ]
                },
            }
        )
        points = otlp_translator.otlp_metrics_to_proto(request)
        assert len(points) == 2

    def test_name_truncated_to_255_chars(self):
        request = self._build_request(
            {
                "name": "x" * 300,
                "gauge": {"dataPoints": [{"timeUnixNano": "1000000000", "asDouble": 1.0}]},
            }
        )
        points = otlp_translator.otlp_metrics_to_proto(request)
        assert len(points[0].name) == 255

    def test_missing_service_name_defaults_to_unknown(self):
        data = {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "queue.depth",
                                    "gauge": {
                                        "dataPoints": [
                                            {"timeUnixNano": "1000000000", "asDouble": 1.0}
                                        ]
                                    },
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        decoded = otlp_translator.decode_metrics_request(
            json.dumps(data).encode(), "application/json"
        )
        points = otlp_translator.otlp_metrics_to_proto(decoded)
        assert points[0].service_name == "unknown_service"


class TestDecodeMetricsRequest:
    def test_protobuf_round_trip(self):
        request = metrics_service_pb2.ExportMetricsServiceRequest()
        rm = request.resource_metrics.add()
        rm.resource.attributes.append(_kv("service.name", _sv("svc")))
        sm = rm.scope_metrics.add()
        metric = sm.metrics.add()
        metric.name = "queue.depth"
        dp = metric.gauge.data_points.add()
        dp.time_unix_nano = 1_000_000_000
        dp.as_double = 3.0

        decoded = otlp_translator.decode_metrics_request(
            request.SerializeToString(), "application/x-protobuf"
        )
        assert decoded.resource_metrics[0].scope_metrics[0].metrics[0].name == "queue.depth"

    def test_malformed_json_rejected(self):
        with pytest.raises(otlp_translator.TranslationError):
            otlp_translator.decode_metrics_request(b"{not json", "application/json")

    def test_malformed_protobuf_rejected(self):
        with pytest.raises(otlp_translator.TranslationError):
            otlp_translator.decode_metrics_request(b"\xff\xff\xff", "application/x-protobuf")
