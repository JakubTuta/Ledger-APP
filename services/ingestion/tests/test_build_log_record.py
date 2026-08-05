"""
Pure unit tests for StorageWorker._build_log_record (a @staticmethod, no DB
needed) - the endpoint/network attribute extraction, status_code/duration_ms
coercion, and client_country resolution branches.
"""

import datetime
import unittest.mock

from ingestion_service.worker import StorageWorker


def _base_log_data(**overrides) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc)
    data = {
        "project_id": 1,
        "timestamp": now.isoformat(),
        "ingested_at": now.isoformat(),
        "level": "info",
        "log_type": "console",
        "importance": "standard",
        "message": "hello",
    }
    data.update(overrides)
    return data


class TestEndpointNetworkGate:
    def test_console_log_type_does_not_extract_endpoint_fields(self):
        log_data = _base_log_data(
            log_type="console",
            attributes={"endpoint": {"method": "GET", "path": "/x", "status_code": 200}},
        )
        record, _ = StorageWorker._build_log_record(log_data)
        assert record["method"] is None
        assert record["path"] is None
        assert record["status_code"] is None
        assert record["duration_ms"] is None

    def test_endpoint_log_type_extracts_fields(self):
        log_data = _base_log_data(
            log_type="endpoint",
            attributes={
                "endpoint": {
                    "method": "POST",
                    "path": "/api/v1/orders",
                    "status_code": 201,
                    "duration_ms": 42,
                }
            },
        )
        record, _ = StorageWorker._build_log_record(log_data)
        assert record["method"] == "POST"
        assert record["path"] == "/api/v1/orders"
        assert record["status_code"] == 201
        assert record["duration_ms"] == 42

    def test_network_log_type_extracts_fields(self):
        log_data = _base_log_data(
            log_type="network",
            attributes={"endpoint": {"method": "GET", "path": "/health", "status_code": 200}},
        )
        record, _ = StorageWorker._build_log_record(log_data)
        assert record["method"] == "GET"
        assert record["status_code"] == 200

    def test_endpoint_log_type_without_attributes_leaves_fields_none(self):
        log_data = _base_log_data(log_type="endpoint", attributes=None)
        record, _ = StorageWorker._build_log_record(log_data)
        assert record["method"] is None
        assert record["status_code"] is None

    def test_endpoint_log_type_with_empty_endpoint_dict(self):
        log_data = _base_log_data(log_type="endpoint", attributes={"endpoint": {}})
        record, _ = StorageWorker._build_log_record(log_data)
        assert record["method"] is None
        assert record["path"] is None
        assert record["status_code"] is None
        assert record["duration_ms"] is None


class TestStatusCodeCoercion:
    def test_non_numeric_status_code_becomes_none(self):
        log_data = _base_log_data(
            log_type="endpoint", attributes={"endpoint": {"status_code": "not-a-number"}}
        )
        record, _ = StorageWorker._build_log_record(log_data)
        assert record["status_code"] is None

    def test_none_status_code_stays_none(self):
        log_data = _base_log_data(
            log_type="endpoint", attributes={"endpoint": {"status_code": None}}
        )
        record, _ = StorageWorker._build_log_record(log_data)
        assert record["status_code"] is None

    def test_string_numeric_status_code_is_coerced_to_int(self):
        log_data = _base_log_data(
            log_type="endpoint", attributes={"endpoint": {"status_code": "404"}}
        )
        record, _ = StorageWorker._build_log_record(log_data)
        assert record["status_code"] == 404
        assert isinstance(record["status_code"], int)


class TestDurationMsCoercion:
    def test_float_duration_ms_is_rounded_to_int(self):
        log_data = _base_log_data(
            log_type="endpoint", attributes={"endpoint": {"duration_ms": 42.6}}
        )
        record, _ = StorageWorker._build_log_record(log_data)
        assert record["duration_ms"] == 43
        assert isinstance(record["duration_ms"], int)

    def test_non_numeric_duration_ms_becomes_none(self):
        log_data = _base_log_data(
            log_type="endpoint", attributes={"endpoint": {"duration_ms": "slow"}}
        )
        record, _ = StorageWorker._build_log_record(log_data)
        assert record["duration_ms"] is None


class TestClientCountry:
    def test_already_set_client_country_skips_lookup(self):
        log_data = _base_log_data(
            client_country="US",
            attributes={"client": {"ip_prefix": "1.2.3."}},
        )
        with unittest.mock.patch(
            "ingestion_service.worker.ip_country.get_lookup"
        ) as mock_get_lookup:
            record, _ = StorageWorker._build_log_record(log_data)

        mock_get_lookup.assert_not_called()
        assert record["client_country"] == "US"

    def test_ip_prefix_present_triggers_lookup(self):
        log_data = _base_log_data(attributes={"client": {"ip_prefix": "1.2.3."}})
        mock_lookup = unittest.mock.Mock()
        mock_lookup.lookup.return_value = "DE"
        with unittest.mock.patch(
            "ingestion_service.worker.ip_country.get_lookup", return_value=mock_lookup
        ):
            record, _ = StorageWorker._build_log_record(log_data)

        mock_lookup.lookup.assert_called_once_with("1.2.3.")
        assert record["client_country"] == "DE"

    def test_no_ip_prefix_skips_lookup(self):
        log_data = _base_log_data(attributes={"client": {}})
        with unittest.mock.patch(
            "ingestion_service.worker.ip_country.get_lookup"
        ) as mock_get_lookup:
            record, _ = StorageWorker._build_log_record(log_data)

        mock_get_lookup.assert_not_called()
        assert record["client_country"] is None


class TestLogIdFallback:
    def test_present_log_id_skips_fallback_generation(self):
        log_data = _base_log_data(log_id="client-supplied-id")
        record, _ = StorageWorker._build_log_record(log_data)
        assert record["log_id"] == "client-supplied-id"

    def test_absent_log_id_uses_deterministic_fallback(self):
        log_data = _base_log_data(log_id=None)
        record, _ = StorageWorker._build_log_record(log_data)
        assert record["log_id"] is not None
        # blake2b/digest_size=8 -> 16 hex chars (64 bits) - see _fallback_log_id.
        assert len(record["log_id"]) == 16

    def test_fallback_id_is_pinned_for_a_known_input(self):
        """Pins the exact fallback digest for a fixed input so a later change
        to _fallback_log_id's source string can't silently churn ids for
        redelivered/duplicate messages without this test catching it."""
        log_data = _base_log_data(
            project_id=42,
            timestamp="2026-01-01T00:00:00+00:00",
            message="pinned message",
            log_id=None,
        )
        record, _ = StorageWorker._build_log_record(log_data)
        assert record["log_id"] == "b3877aa808963afd"
