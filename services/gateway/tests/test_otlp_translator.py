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


def _stored_attributes(log: ingestion_pb2.LogEntry) -> dict:
    """The JSONB a log row stores; the field is left unset when nothing remains."""
    return json.loads(log.attributes) if log.HasField("attributes") else {}


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
        spans = otlp_translator.otlp_spans_to_proto(request).items
        assert spans[0].trace_id == "a" * 32
        assert spans[0].span_id == "b" * 16

    def test_service_name_from_resource(self):
        request = self._build_request(trace_pb2.Span.SPAN_KIND_SERVER)
        spans = otlp_translator.otlp_spans_to_proto(request).items
        assert spans[0].service_name == "checkout"

    def test_missing_service_name_defaults(self):
        request = trace_service_pb2.ExportTraceServiceRequest()
        rs = request.resource_spans.add()
        ss = rs.scope_spans.add()
        span = ss.spans.add()
        span.trace_id = TRACE_ID
        span.span_id = SPAN_ID
        spans = otlp_translator.otlp_spans_to_proto(request).items
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
        spans = otlp_translator.otlp_spans_to_proto(request).items
        assert spans[0].kind == expected

    def test_status_passthrough(self):
        request = self._build_request(
            trace_pb2.Span.SPAN_KIND_SERVER, trace_pb2.Status.STATUS_CODE_ERROR
        )
        spans = otlp_translator.otlp_spans_to_proto(request).items
        assert spans[0].status == ingestion_pb2.ERROR

    def test_attribute_key_normalization(self):
        request = self._build_request(trace_pb2.Span.SPAN_KIND_SERVER)
        spans = otlp_translator.otlp_spans_to_proto(request).items
        assert spans[0].attributes["http.method"] == "GET"
        assert spans[0].attributes["http.status_code"] == "200"

    def test_events_translated(self):
        request = self._build_request(trace_pb2.Span.SPAN_KIND_SERVER)
        spans = otlp_translator.otlp_spans_to_proto(request).items
        assert len(spans[0].events) == 1
        assert spans[0].events[0].name == "exception"
        assert spans[0].events[0].attrs["exception.type"] == "ValueError"

    def test_raw_client_ip_truncated_defensively(self):
        # Simulates an old/buggy SDK still sending a raw, untruncated address
        # under the OTel-standard `client.address` key -- the gateway must
        # never let this reach storage as-is, regardless of SDK version.
        request = self._build_request(trace_pb2.Span.SPAN_KIND_SERVER)
        request.resource_spans[0].scope_spans[0].spans[0].attributes.append(
            _kv("client.address", _sv("203.0.113.42"))
        )
        spans = otlp_translator.otlp_spans_to_proto(request).items
        assert spans[0].attributes["http.client_ip"] == "203.0.113.0/24"

    def test_already_truncated_client_ip_left_equivalent(self):
        request = self._build_request(trace_pb2.Span.SPAN_KIND_SERVER)
        request.resource_spans[0].scope_spans[0].spans[0].attributes.append(
            _kv("client.address", _sv("203.0.113.0/24"))
        )
        spans = otlp_translator.otlp_spans_to_proto(request).items
        assert spans[0].attributes["http.client_ip"] == "203.0.113.0/24"

    def test_unparseable_client_ip_dropped(self):
        request = self._build_request(trace_pb2.Span.SPAN_KIND_SERVER)
        request.resource_spans[0].scope_spans[0].spans[0].attributes.append(
            _kv("client.address", _sv("not-an-ip"))
        )
        spans = otlp_translator.otlp_spans_to_proto(request).items
        assert "http.client_ip" not in spans[0].attributes


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
        spans = otlp_translator.otlp_spans_to_proto(decoded).items
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
        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert logs[0].level == expected_level

    @pytest.mark.parametrize(
        "severity_text,expected_level",
        [("warn", "warning"), ("fatal", "critical"), ("error", "error")],
    )
    def test_severity_text_fallback(self, severity_text, expected_level):
        request = self._build_log_record(severity_number=0, severity_text=severity_text)
        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert logs[0].level == expected_level

    def test_exception_log_type_inferred(self):
        request = self._build_log_record(
            attrs={"exception.type": "ValueError", "exception.message": "bad"}
        )
        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert logs[0].log_type == "exception"
        assert logs[0].error_type == "ValueError"
        assert logs[0].error_message == "bad"

    def test_exception_missing_fields_downgrades_to_custom(self):
        request = self._build_log_record(attrs={"exception.type": "ValueError"})
        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert logs[0].log_type == "custom"

    def test_database_log_type_inferred(self):
        request = self._build_log_record(attrs={"db.system": "postgresql"})
        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert logs[0].log_type == "database"

    def test_logger_log_type_inferred(self):
        request = self._build_log_record(attrs={"code.function": "handler"})
        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert logs[0].log_type == "logger"

    def test_default_log_type_custom(self):
        request = self._build_log_record()
        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert logs[0].log_type == "custom"

    def test_explicit_ledger_log_type_wins(self):
        request = self._build_log_record(attrs={"ledger.log_type": "console"})
        logs = otlp_translator.otlp_logs_to_proto(request).items
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
        logs = otlp_translator.otlp_logs_to_proto(request).items
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
        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert logs[0].log_type == "custom"

    def test_importance_derived_from_level(self):
        request = self._build_log_record(severity_number=21)
        logs = otlp_translator.otlp_logs_to_proto(request).items
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

        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert logs[0].environment == "production"
        assert logs[0].release == "1.2.3"
        assert logs[0].platform == "python"

    def test_trace_and_span_id_get_their_own_fields(self):
        request = self._build_log_record()
        request.resource_logs[0].scope_logs[0].log_records[0].trace_id = TRACE_ID
        request.resource_logs[0].scope_logs[0].log_records[0].span_id = SPAN_ID

        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert logs[0].trace_id == "a" * 32
        assert logs[0].span_id == "b" * 16
        assert "trace_id" not in _stored_attributes(logs[0])

    def test_message_truncated(self):
        request = self._build_log_record(body="x" * 20000)
        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert len(logs[0].message) == 10000

    def test_ledger_log_id_mapped_to_proto_field(self):
        request = self._build_log_record(attrs={"ledger.log_id": "abc123"})
        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert logs[0].log_id == "abc123"

    def test_missing_ledger_log_id_leaves_field_unset(self):
        request = self._build_log_record()
        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert not logs[0].HasField("log_id")

    def test_channel_and_country_promoted_to_typed_fields(self):
        request = self._build_log_record(
            attrs={"ledger.client.channel": "api_client", "ledger.client.country": "DE"}
        )
        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert logs[0].client_channel == "api_client"
        assert logs[0].client_country == "DE"

    def test_channel_and_country_not_in_json_attributes(self):
        request = self._build_log_record(
            attrs={"ledger.client.channel": "api_client", "ledger.client.country": "DE"}
        )
        logs = otlp_translator.otlp_logs_to_proto(request).items
        attributes = _stored_attributes(logs[0])
        assert "ledger.client.channel" not in attributes
        assert "ledger.client.country" not in attributes

    def test_other_client_fields_nested_under_client(self):
        request = self._build_log_record(
            attrs={
                "ledger.client.ip_prefix": "203.0.113.0/24",
                "ledger.client.browser_family": "Chrome",
            }
        )
        logs = otlp_translator.otlp_logs_to_proto(request).items
        attributes = json.loads(logs[0].attributes)
        assert attributes["client"]["ip_prefix"] == "203.0.113.0/24"
        assert attributes["client"]["browser_family"] == "Chrome"
        assert "ledger.client.ip_prefix" not in attributes

    def test_raw_ip_prefix_attribute_defensively_truncated(self):
        request = self._build_log_record(attrs={"ledger.client.ip_prefix": "203.0.113.42"})
        logs = otlp_translator.otlp_logs_to_proto(request).items
        attributes = json.loads(logs[0].attributes)
        assert attributes["client"]["ip_prefix"] == "203.0.113.0/24"

    def test_raw_client_address_attribute_truncated_on_log_path(self):
        # Old SDK behavior: raw client.address as a flat log attribute (not
        # under the ledger.client.* namespace at all).
        request = self._build_log_record(attrs={"client.address": "203.0.113.42"})
        logs = otlp_translator.otlp_logs_to_proto(request).items
        attributes = json.loads(logs[0].attributes)
        assert attributes["client.address"] == "203.0.113.0/24"

    def test_no_client_attrs_no_client_key(self):
        request = self._build_log_record()
        logs = otlp_translator.otlp_logs_to_proto(request).items
        assert "client" not in _stored_attributes(logs[0])


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
        logs = otlp_translator.otlp_logs_to_proto(decoded).items
        assert logs[0].trace_id == "a" * 32
        assert logs[0].span_id == "b" * 16

    def test_malformed_json_rejected(self):
        with pytest.raises(otlp_translator.TranslationError):
            otlp_translator.decode_logs_request(b"{not json", "application/json")


class TestResourceStoredOnce:
    def _request(self, records: int = 3) -> logs_service_pb2.ExportLogsServiceRequest:
        request = logs_service_pb2.ExportLogsServiceRequest()
        rl = request.resource_logs.add()
        rl.resource.attributes.append(_kv("service.name", _sv("checkout")))
        rl.resource.attributes.append(_kv("telemetry.sdk.language", _sv("python")))
        rl.resource.attributes.append(_kv("deployment.environment.name", _sv("production")))
        sl = rl.scope_logs.add()
        for i in range(records):
            record = sl.log_records.add()
            record.time_unix_nano = 1_700_000_000_000_000_000 + i
            record.severity_number = 9
            record.body.string_value = f"log {i}"
            record.attributes.append(_kv("code.function", _sv("handler")))
        return request

    def test_rows_reference_one_resource_instead_of_repeating_it(self):
        translated = otlp_translator.otlp_logs_to_proto(self._request())

        (resource_hash,) = translated.resources
        assert json.loads(translated.resources[resource_hash]) == {
            "deployment.environment.name": "production",
            "service.name": "checkout",
            "telemetry.sdk.language": "python",
        }
        for log in translated.items:
            assert log.resource_hash == resource_hash
            assert _stored_attributes(log) == {"code.function": "handler"}

    def test_resource_still_drives_promoted_columns(self):
        (log, *_) = otlp_translator.otlp_logs_to_proto(self._request()).items

        assert log.service_name == "checkout"
        assert log.environment == "production"
        assert log.platform == "python"

    def test_same_resource_hashes_the_same_across_exports(self):
        first = otlp_translator.otlp_logs_to_proto(self._request(records=1)).resources
        second = otlp_translator.otlp_logs_to_proto(self._request(records=5)).resources
        assert first.keys() == second.keys()

    def test_exception_fields_are_not_stored_twice(self):
        request = self._request(records=1)
        record = request.resource_logs[0].scope_logs[0].log_records[0]
        record.severity_number = 17
        for key, value in (
            ("exception.type", "ValueError"),
            ("exception.message", "bad input"),
            ("exception.stacktrace", "Traceback ..."),
        ):
            record.attributes.append(_kv(key, _sv(value)))

        (log,) = otlp_translator.otlp_logs_to_proto(request).items

        assert log.log_type == "exception"
        assert log.stack_trace == "Traceback ..."
        assert _stored_attributes(log) == {"code.function": "handler"}

    def test_exception_fields_stay_when_the_log_is_not_an_exception(self):
        request = self._request(records=1)
        record = request.resource_logs[0].scope_logs[0].log_records[0]
        record.attributes.append(_kv("exception.stacktrace", _sv("Traceback ...")))

        (log,) = otlp_translator.otlp_logs_to_proto(request).items

        assert log.log_type == "custom"
        assert _stored_attributes(log)["exception.stacktrace"] == "Traceback ..."


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
        points = otlp_translator.otlp_metrics_to_proto(request).items
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
        points = otlp_translator.otlp_metrics_to_proto(request).items
        assert len(points) == 1
        assert points[0].type == ingestion_pb2.SUM
        assert points[0].value == 7.0
        assert points[0].temporality == ingestion_pb2.TEMPORALITY_CUMULATIVE

    def test_delta_sum_records_delta_temporality(self):
        request = self._build_request(
            {
                "name": "requests.count",
                "sum": {
                    "dataPoints": [{"timeUnixNano": "1000000000", "asInt": "7"}],
                    "aggregationTemporality": "AGGREGATION_TEMPORALITY_DELTA",
                    "isMonotonic": True,
                },
            }
        )
        points = otlp_translator.otlp_metrics_to_proto(request).items
        assert points[0].temporality == ingestion_pb2.TEMPORALITY_DELTA

    def test_unset_temporality_stays_unspecified(self):
        request = self._build_request(
            {
                "name": "requests.count",
                "sum": {"dataPoints": [{"timeUnixNano": "1000000000", "asInt": "7"}]},
            }
        )
        points = otlp_translator.otlp_metrics_to_proto(request).items
        assert points[0].temporality == ingestion_pb2.TEMPORALITY_UNSPECIFIED

    def test_gauge_carries_no_temporality(self):
        request = self._build_request(
            {
                "name": "queue.depth",
                "gauge": {"dataPoints": [{"timeUnixNano": "1000000000", "asDouble": 1.0}]},
            }
        )
        points = otlp_translator.otlp_metrics_to_proto(request).items
        assert points[0].temporality == ingestion_pb2.TEMPORALITY_UNSPECIFIED

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
        points = otlp_translator.otlp_metrics_to_proto(request).items
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
        points = otlp_translator.otlp_metrics_to_proto(request).items
        assert len(points) == 2

    def test_name_truncated_to_255_chars(self):
        request = self._build_request(
            {
                "name": "x" * 300,
                "gauge": {"dataPoints": [{"timeUnixNano": "1000000000", "asDouble": 1.0}]},
            }
        )
        points = otlp_translator.otlp_metrics_to_proto(request).items
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
        points = otlp_translator.otlp_metrics_to_proto(decoded).items
        assert points[0].service_name == "unknown_service"

    def test_only_identifying_resource_keys_become_series_tags(self):
        data = {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": [
                            {"key": key, "value": {"stringValue": value}}
                            for key, value in (
                                ("service.name", "checkout"),
                                ("service.instance.id", "i-1"),
                                ("telemetry.sdk.version", "1.43.0"),
                                ("process.command_line", "python app.py --workers 4"),
                            )
                        ]
                    },
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "queue.depth",
                                    "gauge": {
                                        "dataPoints": [
                                            {
                                                "timeUnixNano": "1000000000",
                                                "asDouble": 1.0,
                                                "attributes": [
                                                    {"key": "queue", "value": {"stringValue": "a"}}
                                                ],
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        translated = otlp_translator.otlp_metrics_to_proto(
            otlp_translator.decode_metrics_request(json.dumps(data).encode(), "application/json")
        )

        (point,) = translated.items
        assert dict(point.tags) == {
            "service.name": "checkout",
            "service.instance.id": "i-1",
            "queue": "a",
        }
        assert json.loads(translated.resources[point.resource_hash])["telemetry.sdk.version"] == (
            "1.43.0"
        )

    def test_exponential_histogram_point_translated(self):
        request = self._build_request(
            {
                "name": "request.duration",
                "exponentialHistogram": {
                    "aggregationTemporality": "AGGREGATION_TEMPORALITY_DELTA",
                    "dataPoints": [
                        {
                            "timeUnixNano": "1000000000",
                            "count": "6",
                            "sum": 21.0,
                            "scale": 1,
                            "zeroCount": "1",
                            "positive": {"offset": 2, "bucketCounts": ["2", "3"]},
                        }
                    ],
                },
            }
        )
        (point,) = otlp_translator.otlp_metrics_to_proto(request).items

        assert point.type == ingestion_pb2.EXPONENTIAL_HISTOGRAM
        assert point.temporality == ingestion_pb2.TEMPORALITY_DELTA
        assert (point.count, point.sum, point.scale, point.zero_count) == (6, 21.0, 1, 1)
        assert point.positive_offset == 2
        assert list(point.positive_counts) == [2, 3]
        assert list(point.negative_counts) == []

    def test_summary_point_translated_as_cumulative(self):
        request = self._build_request(
            {
                "name": "gc.pause",
                "summary": {
                    "dataPoints": [
                        {
                            "timeUnixNano": "1000000000",
                            "count": "40",
                            "sum": 12.5,
                            "quantileValues": [
                                {"quantile": 0.5, "value": 0.2},
                                {"quantile": 0.99, "value": 1.4},
                            ],
                        }
                    ]
                },
            }
        )
        (point,) = otlp_translator.otlp_metrics_to_proto(request).items

        assert point.type == ingestion_pb2.SUMMARY
        assert point.temporality == ingestion_pb2.TEMPORALITY_CUMULATIVE
        assert (point.count, point.sum) == (40, 12.5)
        assert list(point.quantiles) == [0.5, 0.99]
        assert list(point.quantile_values) == [0.2, 1.4]

    def test_exemplars_linking_a_trace_are_kept(self):
        request = self._build_request(
            {
                "name": "request.duration",
                "histogram": {
                    "dataPoints": [
                        {
                            "timeUnixNano": "1000000000",
                            "count": "1",
                            "bucketCounts": ["1"],
                            "exemplars": [
                                {
                                    "timeUnixNano": "1000000000",
                                    "asDouble": 812.0,
                                    "traceId": "a" * 32,
                                    "spanId": "b" * 16,
                                },
                                {"timeUnixNano": "1000000000", "asDouble": 3.0},
                            ],
                        }
                    ]
                },
            }
        )
        (point,) = otlp_translator.otlp_metrics_to_proto(request).items

        (exemplar,) = point.exemplars
        assert (exemplar.value, exemplar.trace_id, exemplar.span_id) == (812.0, "a" * 32, "b" * 16)


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
