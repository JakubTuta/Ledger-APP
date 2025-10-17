import datetime

import grpc
import pytest

import ingestion_service.proto.ingestion_pb2 as ingestion_pb2

from .helpers import create_proto_log
from .test_base import BaseIngestionTest


@pytest.mark.asyncio
class TestValidation(BaseIngestionTest):
    """Test request validation for log ingestion."""

    async def test_valid_single_log(self):
        """Test valid single log entry passes validation."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "console",
            "importance": "standard",
            "message": "Test log message",
            "environment": "production",
            "sdk_version": "1.0.0",
            "platform": "python",
            "platform_version": "3.12.0",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Valid single log accepted")

    async def test_missing_required_fields(self):
        """Test that missing required fields are rejected."""
        log_dict = {
            "timestamp": "",
            "level": "info",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        with pytest.raises(grpc.RpcError) as exc_info:
            await self.stub.IngestLog(request)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        print("✅ Missing required fields rejected")

    async def test_invalid_level(self):
        """Test that invalid log level is rejected."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "invalid_level",
            "log_type": "console",
            "importance": "standard",
            "message": "Test",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        with pytest.raises(grpc.RpcError) as exc_info:
            await self.stub.IngestLog(request)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        assert "level" in str(exc_info.value.details()).lower()
        print("✅ Invalid level rejected")

    async def test_invalid_log_type(self):
        """Test that invalid log type is rejected."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "invalid_type",
            "importance": "standard",
            "message": "Test",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        with pytest.raises(grpc.RpcError) as exc_info:
            await self.stub.IngestLog(request)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        print("✅ Invalid log type rejected")

    async def test_invalid_importance(self):
        """Test that invalid importance is rejected."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "console",
            "importance": "invalid_importance",
            "message": "Test",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        with pytest.raises(grpc.RpcError) as exc_info:
            await self.stub.IngestLog(request)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        print("✅ Invalid importance rejected")

    async def test_future_timestamp_within_tolerance(self):
        """Test that future timestamps within tolerance are accepted."""
        future_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=2)

        log_dict = {
            "timestamp": future_time.isoformat(),
            "level": "info",
            "log_type": "console",
            "importance": "standard",
            "message": "Future timestamp test",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Future timestamp within tolerance accepted")

    async def test_future_timestamp_beyond_tolerance(self):
        """Test that future timestamps beyond tolerance are rejected."""
        future_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)

        log_dict = {
            "timestamp": future_time.isoformat(),
            "level": "info",
            "log_type": "console",
            "importance": "standard",
            "message": "Far future timestamp test",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        with pytest.raises(grpc.RpcError) as exc_info:
            await self.stub.IngestLog(request)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        assert "timestamp" in str(exc_info.value.details()).lower() or "future" in str(exc_info.value.details()).lower()
        print("✅ Future timestamp beyond tolerance rejected")

    async def test_message_too_long(self):
        """Test that message exceeding max length is rejected."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "console",
            "importance": "standard",
            "message": "x" * 15000,
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        with pytest.raises(grpc.RpcError) as exc_info:
            await self.stub.IngestLog(request)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        print("✅ Message too long rejected")

    async def test_attributes_too_large(self):
        """Test that attributes exceeding max size are rejected."""
        large_attributes = {f"key_{i}": "x" * 1000 for i in range(150)}

        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "console",
            "importance": "standard",
            "message": "Test",
            "attributes": large_attributes,
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        with pytest.raises(grpc.RpcError) as exc_info:
            await self.stub.IngestLog(request)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        print("✅ Attributes too large rejected")

    async def test_exception_fields_validation(self):
        """Test exception log with all required fields."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "error",
            "log_type": "exception",
            "importance": "high",
            "message": "Division by zero",
            "error_type": "ZeroDivisionError",
            "error_message": "division by zero",
            "stack_trace": "Traceback (most recent call last):\n  File test.py line 10",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Exception log with all fields accepted")

    async def test_exception_missing_fields(self):
        """Test exception log missing required exception fields."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "error",
            "log_type": "exception",
            "importance": "high",
            "message": "Error occurred",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        with pytest.raises(grpc.RpcError) as exc_info:
            await self.stub.IngestLog(request)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        print("✅ Exception missing required fields rejected")

    async def test_batch_validation_all_valid(self):
        """Test batch with all valid logs."""
        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "console",
                "importance": "standard",
                "message": f"Log {i}",
            }
            for i in range(10)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 10
        print("✅ Batch with all valid logs accepted")

    async def test_batch_validation_one_invalid(self):
        """Test batch with one invalid log still processes valid ones."""
        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "console",
                "importance": "standard",
                "message": "Valid log",
            },
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "invalid_level",
                "log_type": "console",
                "importance": "standard",
                "message": "Invalid log",
            },
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        assert response.queued == 1
        assert response.failed == 1
        print("✅ Batch with one invalid log processed valid ones")

    async def test_batch_exceeds_max_logs(self):
        """Test batch with many logs."""
        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "console",
                "importance": "standard",
                "message": f"Log {i}",
            }
            for i in range(2000)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        response = await self.stub.IngestLogBatch(request)
        assert response.success is True
        print("✅ Large batch processed")

    async def test_empty_batch(self):
        """Test empty batch."""
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=[])

        response = await self.stub.IngestLogBatch(request)
        assert response.queued == 0
        print("✅ Empty batch handled")

    async def test_optional_fields(self):
        """Test log with optional fields."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "warning",
            "log_type": "network",
            "importance": "high",
            "message": "Network request failed",
            "environment": "staging",
            "release": "v1.2.3",
            "sdk_version": "2.0.0",
            "platform": "nodejs",
            "platform_version": "20.0.0",
            "attributes": {
                "request_id": "req_123",
                "url": "https://api.example.com",
                "status_code": 500,
            },
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Log with optional fields accepted")

    async def test_minimal_log(self):
        """Test minimal log with only required fields."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "debug",
            "log_type": "custom",
            "importance": "low",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Minimal log with only required fields accepted")

    async def test_stack_trace_too_long(self):
        """Test that stack trace exceeding max length is rejected."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "error",
            "log_type": "exception",
            "importance": "high",
            "message": "Error",
            "error_type": "TestError",
            "error_message": "Test error",
            "stack_trace": "x" * 60000,
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        with pytest.raises(grpc.RpcError) as exc_info:
            await self.stub.IngestLog(request)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        print("✅ Stack trace too long rejected")

    async def test_all_log_levels(self):
        """Test all valid log levels."""
        levels = ["debug", "info", "warning", "error", "critical"]

        for level in levels:
            log_dict = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": level,
                "log_type": "logger",
                "importance": "standard",
                "message": f"Test {level} log",
            }

            proto_log = create_proto_log(log_dict)
            request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

            response = await self.stub.IngestLog(request)
            assert response.success is True

        print("✅ All log levels accepted")

    async def test_all_log_types(self):
        """Test all valid log types."""
        log_types = ["console", "logger", "exception", "network", "database", "custom"]

        for log_type in log_types:
            log_dict = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": log_type,
                "importance": "standard",
                "message": f"Test {log_type} log",
            }

            if log_type == "exception":
                log_dict["error_type"] = "TestError"
                log_dict["error_message"] = "Test error"
                log_dict["stack_trace"] = "Test stack trace"

            proto_log = create_proto_log(log_dict)
            request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

            response = await self.stub.IngestLog(request)
            assert response.success is True

        print("✅ All log types accepted")

    async def test_all_importance_levels(self):
        """Test all valid importance levels."""
        importance_levels = ["critical", "high", "standard", "low"]

        for importance in importance_levels:
            log_dict = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "console",
                "importance": importance,
                "message": f"Test {importance} importance",
            }

            proto_log = create_proto_log(log_dict)
            request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

            response = await self.stub.IngestLog(request)
            assert response.success is True

        print("✅ All importance levels accepted")
