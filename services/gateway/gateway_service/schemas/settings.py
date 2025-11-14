import typing

import pydantic


class RateLimits(pydantic.BaseModel):
    """Rate limiting configuration."""

    requests_per_minute: int = pydantic.Field(
        ...,
        description="Maximum requests allowed per minute",
        ge=0,
    )
    requests_per_hour: int = pydantic.Field(
        ...,
        description="Maximum requests allowed per hour",
        ge=0,
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "requests_per_minute": 1000,
                    "requests_per_hour": 50000,
                }
            ]
        }
    )


class Quotas(pydantic.BaseModel):
    """Daily usage quotas and current usage."""

    daily_quota: int = pydantic.Field(
        ...,
        description="Maximum logs allowed per day",
        ge=0,
    )
    daily_usage: int = pydantic.Field(
        ...,
        description="Number of logs ingested today",
        ge=0,
    )
    quota_remaining: int = pydantic.Field(
        ...,
        description="Remaining quota for today",
        ge=0,
    )
    quota_reset_at: str = pydantic.Field(
        ...,
        description="When the daily quota resets (midnight UTC, ISO 8601)",
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "daily_quota": 1000000,
                    "daily_usage": 45678,
                    "quota_remaining": 954322,
                    "quota_reset_at": "2024-01-16T00:00:00Z",
                }
            ]
        }
    )


class Constraints(pydantic.BaseModel):
    """Field length and validation constraints."""

    max_batch_size: int = pydantic.Field(
        ...,
        description="Maximum number of logs per batch request",
    )
    max_message_length: int = pydantic.Field(
        ...,
        description="Maximum length for log message field (characters)",
    )
    max_error_message_length: int = pydantic.Field(
        ...,
        description="Maximum length for error_message field (characters)",
    )
    max_stack_trace_length: int = pydantic.Field(
        ...,
        description="Maximum length for stack_trace field (characters)",
    )
    max_attributes_size_bytes: int = pydantic.Field(
        ...,
        description="Maximum size for attributes JSONB field (bytes)",
    )
    max_environment_length: int = pydantic.Field(
        ...,
        description="Maximum length for environment field (characters)",
    )
    max_release_length: int = pydantic.Field(
        ...,
        description="Maximum length for release field (characters)",
    )
    max_sdk_version_length: int = pydantic.Field(
        ...,
        description="Maximum length for sdk_version field (characters)",
    )
    max_platform_length: int = pydantic.Field(
        ...,
        description="Maximum length for platform field (characters)",
    )
    max_platform_version_length: int = pydantic.Field(
        ...,
        description="Maximum length for platform_version field (characters)",
    )
    max_error_type_length: int = pydantic.Field(
        ...,
        description="Maximum length for error_type field (characters)",
    )
    supported_log_levels: typing.List[str] = pydantic.Field(
        ...,
        description="Valid values for the 'level' field",
    )
    supported_log_types: typing.List[str] = pydantic.Field(
        ...,
        description="Valid values for the 'log_type' field",
    )
    supported_importance_levels: typing.List[str] = pydantic.Field(
        ...,
        description="Valid values for the 'importance' field",
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "max_batch_size": 1000,
                    "max_message_length": 10000,
                    "max_error_message_length": 5000,
                    "max_stack_trace_length": 50000,
                    "max_attributes_size_bytes": 102400,
                    "max_environment_length": 20,
                    "max_release_length": 100,
                    "max_sdk_version_length": 20,
                    "max_platform_length": 50,
                    "max_platform_version_length": 50,
                    "max_error_type_length": 255,
                    "supported_log_levels": [
                        "debug",
                        "info",
                        "warning",
                        "error",
                        "critical",
                    ],
                    "supported_log_types": ["console", "logger", "exception", "custom"],
                    "supported_importance_levels": ["low", "standard", "high"],
                }
            ]
        }
    )


class Features(pydantic.BaseModel):
    """Feature flags and capabilities."""

    batch_ingestion: bool = pydantic.Field(
        ...,
        description="Whether batch log ingestion is supported",
    )
    compression: bool = pydantic.Field(
        ...,
        description="Whether compressed request bodies are supported",
    )
    streaming: bool = pydantic.Field(
        ...,
        description="Whether streaming log ingestion is supported",
    )
    endpoint_monitoring: bool = pydantic.Field(
        ...,
        description="Whether endpoint/API monitoring is enabled",
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "batch_ingestion": True,
                    "compression": False,
                    "streaming": False,
                    "endpoint_monitoring": True,
                }
            ]
        }
    )


class ServerInfo(pydantic.BaseModel):
    """Server version and timestamp information."""

    version: str = pydantic.Field(
        ...,
        description="API version string (semver format)",
    )
    timestamp: str = pydantic.Field(
        ...,
        description="Current server time (ISO 8601 format)",
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "version": "1.0.0",
                    "timestamp": "2024-01-15T10:30:00Z",
                }
            ]
        }
    )


class SettingsResponse(pydantic.BaseModel):
    """
    Comprehensive project settings and configuration.

    Contains all information needed for SDK initialization and validation,
    including rate limits, quotas, field constraints, and feature flags.
    """

    project_id: int = pydantic.Field(..., description="Project identifier")
    project_name: str = pydantic.Field(..., description="Project display name")
    project_slug: str = pydantic.Field(..., description="Project slug")
    environment: str = pydantic.Field(
        ..., description="Environment (production, staging, dev)"
    )
    rate_limits: RateLimits = pydantic.Field(
        ..., description="Rate limiting configuration"
    )
    quotas: Quotas = pydantic.Field(..., description="Daily quotas and usage")
    constraints: Constraints = pydantic.Field(
        ..., description="Validation constraints and field limits"
    )
    features: Features = pydantic.Field(..., description="Enabled features")
    server_info: ServerInfo = pydantic.Field(..., description="Server information")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "project_id": 456,
                    "project_name": "My Production App",
                    "project_slug": "my-production-app",
                    "environment": "production",
                    "rate_limits": {
                        "requests_per_minute": 1000,
                        "requests_per_hour": 50000,
                    },
                    "quotas": {
                        "daily_quota": 1000000,
                        "daily_usage": 45678,
                        "quota_remaining": 954322,
                        "quota_reset_at": "2024-01-16T00:00:00Z",
                    },
                    "constraints": {
                        "max_batch_size": 1000,
                        "max_message_length": 10000,
                        "max_error_message_length": 5000,
                        "max_stack_trace_length": 50000,
                        "max_attributes_size_bytes": 102400,
                        "max_environment_length": 20,
                        "max_release_length": 100,
                        "max_sdk_version_length": 20,
                        "max_platform_length": 50,
                        "max_platform_version_length": 50,
                        "max_error_type_length": 255,
                        "supported_log_levels": [
                            "debug",
                            "info",
                            "warning",
                            "error",
                            "critical",
                        ],
                        "supported_log_types": [
                            "console",
                            "logger",
                            "exception",
                            "custom",
                        ],
                        "supported_importance_levels": ["low", "standard", "high"],
                    },
                    "features": {
                        "batch_ingestion": True,
                        "compression": False,
                        "streaming": False,
                        "endpoint_monitoring": True,
                    },
                    "server_info": {
                        "version": "1.0.0",
                        "timestamp": "2024-01-15T10:30:00Z",
                    },
                }
            ]
        }
    )
