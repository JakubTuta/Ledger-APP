import datetime
import typing

import pydantic


class LogEntry(pydantic.BaseModel):
    """
    Log entry model for ingestion API.

    Represents a single log event with temporal data, classification,
    content, and metadata fields.
    """

    timestamp: datetime.datetime = pydantic.Field(
        ...,
        description="Log timestamp in ISO 8601 format (e.g., '2025-01-15T10:30:45.123Z'). Must not be more than 5 minutes in the future.",
        examples=["2025-01-15T10:30:45.123Z"],
    )

    level: typing.Literal["debug", "info", "warning", "error", "critical"] = (
        pydantic.Field(
            ...,
            description="Log severity level. Determines how the log is classified and filtered.",
            examples=["error"],
        )
    )

    log_type: typing.Literal[
        "console", "logger", "exception", "network", "database", "endpoint", "custom"
    ] = pydantic.Field(
        default="logger",
        description=(
            "Type of log source:\n"
            "- `console`: stdout/stderr output\n"
            "- `logger`: structured logging framework output\n"
            "- `exception`: caught exceptions with stack traces\n"
            "- `network`: HTTP/API requests and responses\n"
            "- `database`: database queries and operations\n"
            "- `endpoint`: API endpoint monitoring metrics (requires attributes.endpoint)\n"
            "- `custom`: application-specific logs"
        ),
        examples=["exception"],
    )

    importance: typing.Literal["critical", "high", "standard", "low"] = pydantic.Field(
        default="standard",
        description=(
            "Business importance level (orthogonal to technical severity):\n"
            "- `critical`: requires immediate attention (e.g., payment failures)\n"
            "- `high`: important but not urgent (e.g., slow queries)\n"
            "- `standard`: normal operational logs\n"
            "- `low`: debug or trace information"
        ),
        examples=["high"],
    )

    message: str | None = pydantic.Field(
        None,
        max_length=10000,
        description="Log message or console output. Maximum 10,000 characters.",
        examples=["Payment processing failed for transaction txn_abc"],
    )

    error_type: str | None = pydantic.Field(
        None,
        max_length=255,
        description="Exception class name (e.g., 'ValueError', 'DatabaseConnectionError'). Required when log_type is 'exception'.",
        examples=["PaymentGatewayError"],
    )

    error_message: str | None = pydantic.Field(
        None,
        max_length=5000,
        description="Human-readable error description. Maximum 5,000 characters. Required when log_type is 'exception'.",
        examples=["Gateway timeout after 30 seconds"],
    )

    stack_trace: str | None = pydantic.Field(
        None,
        max_length=50000,
        description="Full exception stack trace. Maximum 50,000 characters.",
        examples=[
            "Traceback (most recent call last):\n  File '/app/payment.py', line 45, in process\n    ..."
        ],
    )

    environment: str | None = pydantic.Field(
        None,
        max_length=20,
        description="Environment name (e.g., 'production', 'staging', 'dev'). Maximum 20 characters.",
        examples=["production"],
    )

    release: str | None = pydantic.Field(
        None,
        max_length=100,
        description="Release version or git commit SHA (e.g., 'v1.2.3', '7f3b9a2'). Maximum 100 characters.",
        examples=["v1.2.3"],
    )

    attributes: dict[str, typing.Any] | None = pydantic.Field(
        None,
        description=(
            "Custom key-value pairs for additional context. Stored as JSONB. Maximum 100KB when serialized.\n\n"
            "**Special requirements:**\n"
            "- When log_type is 'endpoint', must include an 'endpoint' object with: method, path, status_code, duration_ms"
        ),
        examples=[
            {
                "user_id": "usr_123",
                "transaction_id": "txn_abc",
                "amount": 99.99,
                "currency": "USD",
                "retry_count": 3,
            }
        ],
    )

    sdk_version: str | None = pydantic.Field(
        None,
        max_length=20,
        description="SDK version used to generate this log (e.g., '1.0.0'). Maximum 20 characters.",
        examples=["1.0.0"],
    )

    platform: str | None = pydantic.Field(
        None,
        max_length=50,
        description="Runtime platform or language (e.g., 'python', 'node.js', 'java'). Maximum 50 characters.",
        examples=["python"],
    )

    platform_version: str | None = pydantic.Field(
        None,
        max_length=50,
        description="Runtime version (e.g., '3.12', '20.10.0'). Maximum 50 characters.",
        examples=["3.12"],
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "timestamp": "2025-01-15T10:30:45.123Z",
                    "level": "error",
                    "log_type": "exception",
                    "importance": "high",
                    "message": "Payment processing failed",
                    "error_type": "PaymentGatewayError",
                    "error_message": "Gateway timeout after 30 seconds",
                    "stack_trace": "Traceback (most recent call last):\n  File '/app/payment.py', line 45, in process\n    ...",
                    "environment": "production",
                    "release": "v1.2.3",
                    "attributes": {
                        "user_id": "usr_123",
                        "transaction_id": "txn_abc",
                        "amount": 99.99,
                        "currency": "USD",
                    },
                    "sdk_version": "1.0.0",
                    "platform": "python",
                    "platform_version": "3.12",
                },
                {
                    "timestamp": "2025-01-15T10:30:45.123Z",
                    "level": "info",
                    "log_type": "endpoint",
                    "message": "GET /api/v1/users/123",
                    "attributes": {
                        "endpoint": {
                            "method": "GET",
                            "path": "/api/v1/users/123",
                            "status_code": 200,
                            "duration_ms": 45.2,
                        },
                        "user_agent": "Mozilla/5.0",
                        "ip_address": "203.0.113.42",
                    },
                    "environment": "production",
                    "release": "v1.2.3",
                },
                {
                    "timestamp": "2025-01-15T10:30:45.123Z",
                    "level": "debug",
                    "log_type": "logger",
                    "importance": "low",
                    "message": "Cache hit for key: user:123",
                    "attributes": {
                        "cache_key": "user:123",
                        "ttl_seconds": 300,
                    },
                },
            ]
        }
    )


class BatchLogRequest(pydantic.BaseModel):
    """
    Batch log ingestion request.

    Contains multiple log entries for efficient bulk processing.
    """

    logs: list[LogEntry] = pydantic.Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Array of log entries. Minimum 1, maximum 1000 logs per batch request.",
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "logs": [
                        {
                            "timestamp": "2025-01-15T10:30:45.123Z",
                            "level": "info",
                            "log_type": "logger",
                            "message": "User login successful",
                            "attributes": {
                                "user_id": "usr_123",
                                "session_id": "sess_abc",
                            },
                        },
                        {
                            "timestamp": "2025-01-15T10:30:46.456Z",
                            "level": "error",
                            "log_type": "exception",
                            "error_type": "DatabaseError",
                            "error_message": "Connection timeout",
                            "stack_trace": "Traceback...",
                            "attributes": {
                                "query": "SELECT * FROM users WHERE id = 123"
                            },
                        },
                        {
                            "timestamp": "2025-01-15T10:30:47.789Z",
                            "level": "warning",
                            "log_type": "logger",
                            "message": "Slow query detected",
                            "attributes": {"duration_ms": 1523, "query_type": "SELECT"},
                        },
                    ]
                }
            ]
        }
    )


class IngestResponse(pydantic.BaseModel):
    """
    Response from log ingestion operations.

    Indicates how many logs were accepted/rejected and provides
    error details for rejected logs.
    """

    accepted: int = pydantic.Field(
        ...,
        description="Number of logs successfully queued for processing",
        ge=0,
    )

    rejected: int = pydantic.Field(
        default=0,
        description="Number of logs that failed validation",
        ge=0,
    )

    message: str | None = pydantic.Field(
        None,
        description="Human-readable status message",
    )

    errors: list[str] | None = pydantic.Field(
        None,
        description="Array of error messages for rejected logs (if any). Each entry indicates which log failed and why.",
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "accepted": 1,
                    "rejected": 0,
                    "message": "Log queued successfully",
                },
                {
                    "accepted": 998,
                    "rejected": 2,
                    "errors": [
                        "Log 45: Timestamp too far in future",
                        "Log 123: Attributes JSONB exceeds 100KB",
                    ],
                },
            ]
        }
    )


class QueueDepthResponse(pydantic.BaseModel):
    """
    Response from queue depth query.

    Provides information about the current ingestion queue status.
    """

    project_id: int = pydantic.Field(
        ...,
        description="Project ID",
    )

    queue_depth: int = pydantic.Field(
        ...,
        description="Number of logs currently waiting in the queue to be processed",
        ge=0,
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "project_id": 456,
                    "queue_depth": 1234,
                }
            ]
        }
    )
