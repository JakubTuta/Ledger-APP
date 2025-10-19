import datetime
import json
import typing

import pydantic

import ingestion_service.config as config


class LogEntry(pydantic.BaseModel):
    timestamp: datetime.datetime = pydantic.Field(
        ...,
        description="Log timestamp (ISO 8601 format)",
    )

    level: typing.Literal["debug", "info", "warning", "error", "critical"] = (
        pydantic.Field(
            ...,
            description="Log severity level",
        )
    )

    log_type: typing.Literal[
        "console", "logger", "exception", "network", "database", "endpoint", "custom"
    ] = pydantic.Field(
        default="logger",
        description="Type of log source",
    )

    importance: typing.Literal["critical", "high", "standard", "low"] = pydantic.Field(
        default="standard",
        description="Business importance",
    )

    message: str | None = pydantic.Field(
        None,
        max_length=config.settings.MAX_LOG_MESSAGE_LENGTH,
        description="Log message or console output",
    )

    error_type: str | None = pydantic.Field(
        None,
        max_length=255,
        description="Exception class name",
    )

    error_message: str | None = pydantic.Field(
        None,
        max_length=config.settings.MAX_ERROR_MESSAGE_LENGTH,
        description="Error description",
    )

    stack_trace: str | None = pydantic.Field(
        None,
        max_length=config.settings.MAX_STACK_TRACE_LENGTH,
        description="Full stack trace",
    )

    environment: str | None = pydantic.Field(
        None,
        max_length=20,
        description="Environment name",
    )

    release: str | None = pydantic.Field(
        None,
        max_length=100,
        description="Release version or git SHA",
    )

    attributes: dict[str, typing.Any] | None = pydantic.Field(
        None,
        description="Custom key-value pairs",
    )

    sdk_version: str | None = pydantic.Field(
        None,
        max_length=20,
        description="SDK version",
    )

    platform: str | None = pydantic.Field(
        None,
        max_length=50,
        description="Runtime platform",
    )

    platform_version: str | None = pydantic.Field(
        None,
        max_length=50,
        description="Runtime version",
    )

    @pydantic.field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: datetime.datetime) -> datetime.datetime:
        max_future = datetime.datetime.now(
            datetime.timezone.utc
        ) + datetime.timedelta(
            minutes=config.settings.TIMESTAMP_FUTURE_TOLERANCE_MINUTES
        )
        if v > max_future:
            raise ValueError(
                f"Timestamp cannot be more than {config.settings.TIMESTAMP_FUTURE_TOLERANCE_MINUTES} minutes in the future"
            )
        return v

    @pydantic.field_validator("attributes")
    @classmethod
    def validate_attributes_size(
        cls, v: dict[str, typing.Any] | None
    ) -> dict[str, typing.Any] | None:
        if v is None:
            return v

        json_size = len(json.dumps(v))
        if json_size > config.settings.MAX_ATTRIBUTES_SIZE:
            raise ValueError(
                f"Attributes JSONB cannot exceed {config.settings.MAX_ATTRIBUTES_SIZE} bytes"
            )

        return v

    @pydantic.model_validator(mode="after")
    def validate_exception_fields(self) -> "LogEntry":
        if self.log_type == "exception":
            if not self.error_type:
                raise ValueError("error_type is required when log_type is 'exception'")
            if not self.error_message:
                raise ValueError(
                    "error_message is required when log_type is 'exception'"
                )
        return self

    @pydantic.model_validator(mode="after")
    def validate_endpoint_fields(self) -> "LogEntry":
        if self.log_type == "endpoint":
            if not self.attributes:
                raise ValueError("attributes field is required when log_type is 'endpoint'")

            endpoint_data = self.attributes.get("endpoint")
            if not endpoint_data:
                raise ValueError(
                    "attributes.endpoint is required when log_type is 'endpoint'. "
                    "Must include: method, path, status_code, duration_ms"
                )

            required_fields = ["method", "path", "status_code", "duration_ms"]
            missing_fields = [f for f in required_fields if f not in endpoint_data]
            if missing_fields:
                raise ValueError(
                    f"attributes.endpoint missing required fields: {', '.join(missing_fields)}"
                )
        return self

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2025-01-15T10:30:45.123Z",
                "level": "error",
                "log_type": "exception",
                "importance": "high",
                "message": "Payment processing failed",
                "error_type": "PaymentGatewayError",
                "error_message": "Gateway timeout after 30s",
                "stack_trace": "Traceback (most recent call last):\n  File ...",
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
            }
        }
    )


class BatchLogRequest(pydantic.BaseModel):
    logs: list[LogEntry] = pydantic.Field(
        ...,
        min_length=1,
        max_length=config.settings.MAX_BATCH_LOGS,
        description=f"Batch of log entries (max {config.settings.MAX_BATCH_LOGS} per request)",
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "logs": [
                    {
                        "timestamp": "2025-01-15T10:30:45.123Z",
                        "level": "info",
                        "log_type": "logger",
                        "message": "User login successful",
                        "attributes": {"user_id": "usr_123"},
                    },
                    {
                        "timestamp": "2025-01-15T10:30:46.456Z",
                        "level": "error",
                        "log_type": "exception",
                        "error_type": "DatabaseError",
                        "error_message": "Connection timeout",
                        "attributes": {"query": "SELECT ..."},
                    },
                ]
            }
        }
    )


class IngestResponse(pydantic.BaseModel):
    accepted: int = pydantic.Field(..., description="Number of logs accepted")
    rejected: int = pydantic.Field(default=0, description="Number of logs rejected")
    errors: list[str] | None = pydantic.Field(
        None, description="Error messages if any rejections"
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "accepted": 998,
                "rejected": 2,
                "errors": [
                    "Log 45: Timestamp too far in future",
                    "Log 123: Attributes JSONB exceeds 100KB",
                ],
            }
        }
    )


class EnrichedLogEntry(pydantic.BaseModel):
    project_id: int
    log_entry: LogEntry
    ingested_at: datetime.datetime
    error_fingerprint: str | None = None

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)
