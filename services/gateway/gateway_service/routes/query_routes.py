import datetime
import json
import logging
from typing import Literal, Optional

import fastapi
import gateway_service.proto.query_pb2 as query_pb2
import gateway_service.schemas as schemas
import grpc
from pydantic import field_validator

router = fastapi.APIRouter(tags=["Query"])
logger = logging.getLogger(__name__)


@router.get(
    "/logs/{log_id}",
    status_code=200,
    summary="Get log by ID",
    description="Retrieve detailed information for a specific log entry by its ID. Returns complete log data including metadata, error information, and custom attributes.",
    response_description="Complete log entry details",
    response_model=schemas.LogEntryResponse,
    responses={
        404: {
            "description": "Log not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Log not found or access denied"}
                }
            },
        },
        400: {
            "description": "Invalid log ID",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid log ID format"}
                }
            },
        },
        500: {
            "description": "Server error",
            "content": {
                "application/json": {"example": {"detail": "Failed to retrieve log"}}
            },
        },
    },
)
async def get_log_by_id(
    log_id: int,
    request: fastapi.Request,
    project_id: int = fastapi.Query(
        ...,
        description="The project ID to retrieve the log from",
        gt=0,
    ),
) -> schemas.LogEntryResponse:
    """
    Retrieve a complete log entry by its unique ID.

    Returns all available information for the specified log, including:
    - Temporal data (timestamp, ingestion time)
    - Classification (level, type, importance)
    - Content (message, error details, stack trace)
    - Metadata (environment, release, SDK info, platform)
    - Custom attributes (JSON object)
    - Error tracking (fingerprint for grouping similar errors)

    ## Path Parameters

    - **log_id** (integer, required): The unique identifier of the log entry

    ## Query Parameters

    - **project_id** (integer, required): The project ID to retrieve the log from

    ## Authorization

    Requires session token authentication via `Authorization: Bearer <token>` header.

    ## Response

    Returns a complete `LogEntryResponse` object with all fields populated
    according to what was captured during log ingestion.

    ## Use Cases

    - **Error investigation**: View full stack traces and error context
    - **Audit trails**: Retrieve specific log entries for compliance
    - **Debugging**: Access detailed metadata and custom attributes
    - **Context expansion**: Get full details from log list or search results

    ## Example Response

    ```json
    {
      "id": 123456,
      "project_id": 1,
      "timestamp": "2025-11-21T14:30:00Z",
      "ingested_at": "2025-11-21T14:30:01Z",
      "level": "error",
      "log_type": "exception",
      "importance": "high",
      "environment": "production",
      "release": "v1.2.3",
      "message": "Database connection failed",
      "error_type": "psycopg2.OperationalError",
      "error_message": "could not connect to server",
      "stack_trace": "Traceback (most recent call last):\\n  File ...",
      "attributes": {
        "user_id": 42,
        "request_id": "abc123",
        "endpoint": "/api/users"
      },
      "sdk_version": "1.0.0",
      "platform": "Python",
      "platform_version": "3.12.0",
      "processing_time_ms": 5,
      "error_fingerprint": "a3f8b9c2d1e4f5a6b7c8d9e0f1a2b3c4..."
    }
    ```

    Requires session token authentication via `Authorization: Bearer <token>` header.
    """
    grpc_pool = request.app.state.grpc_pool

    try:
        async with grpc_pool.get_query_stub() as stub:
            response = await stub.GetLog(
                query_pb2.GetLogRequest(log_id=log_id, project_id=project_id),
                timeout=5.0,
            )

        if not response.found:
            raise fastapi.HTTPException(
                status_code=404,
                detail="Log not found or access denied",
            )

        log_entry = _proto_to_pydantic_log(response.log)
        return log_entry

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=404,
                detail="Log not found or access denied",
            )
        elif e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=400,
                detail="Invalid log ID format",
            )
        else:
            logger.error(f"gRPC error retrieving log: {e.code()} - {e.details()}")
            raise fastapi.HTTPException(
                status_code=500,
                detail="Failed to retrieve log",
            )

    except fastapi.HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to retrieve log: {e}", exc_info=True)
        raise fastapi.HTTPException(
            status_code=500,
            detail="Failed to retrieve log",
        )


@router.get(
    "/metrics/aggregated",
    status_code=200,
    summary="Get aggregated metrics",
    description="Retrieve pre-aggregated metrics (exceptions or endpoints) for analysis and visualization. Returns hourly data for single-day periods, daily data for multi-day periods.",
    response_description="Aggregated metrics data",
    response_model=schemas.AggregatedMetricsResponse,
    responses={
        400: {
            "description": "Invalid parameters",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_type": {
                            "summary": "Invalid metric type",
                            "value": {
                                "detail": "type must be 'exception', 'endpoint', or 'log_volume'"
                            },
                        },
                        "missing_period": {
                            "summary": "Missing period parameters",
                            "value": {
                                "detail": "Either 'period' or both 'periodFrom' and 'periodTo' must be provided"
                            },
                        },
                        "invalid_period": {
                            "summary": "Invalid period value",
                            "value": {
                                "detail": "period must be one of: today, last7days, last30days, currentWeek, currentMonth, currentYear"
                            },
                        },
                        "future_date": {
                            "summary": "Future dates not allowed",
                            "value": {"detail": "Dates cannot be in the future"},
                        },
                        "invalid_date_format": {
                            "summary": "Invalid date format",
                            "value": {
                                "detail": "periodFrom must be in ISO 8601 format (YYYY-MM-DD)"
                            },
                        },
                    }
                }
            },
        },
        500: {
            "description": "Server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to retrieve aggregated metrics"}
                }
            },
        },
    },
)
async def get_aggregated_metrics(
    request: fastapi.Request,
    project_id: int = fastapi.Query(
        ...,
        description="The project ID to retrieve metrics for",
        gt=0,
    ),
    type: Literal["exception", "endpoint", "log_volume"] = fastapi.Query(
        ...,
        description="Metric type to retrieve (exception for error tracking, endpoint for API monitoring, log_volume for log volume metrics)",
    ),
    period: Optional[
        Literal[
            "today",
            "last7days",
            "last30days",
            "currentWeek",
            "currentMonth",
            "currentYear",
        ]
    ] = fastapi.Query(
        None,
        description="Predefined time period. Mutually exclusive with periodFrom/periodTo.",
    ),
    periodFrom: Optional[str] = fastapi.Query(
        None,
        description="Start date in ISO 8601 format (YYYY-MM-DD). Must be used with periodTo.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    periodTo: Optional[str] = fastapi.Query(
        None,
        description="End date in ISO 8601 format (YYYY-MM-DD). Must be used with periodFrom.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    endpointPath: Optional[str] = fastapi.Query(
        None,
        description="Filter by specific endpoint path (e.g., /api/users). Only applicable when type=endpoint.",
    ),
) -> schemas.AggregatedMetricsResponse:
    """
    Retrieve aggregated metrics for a project.

    This endpoint returns pre-aggregated hourly metrics computed by analytics workers.
    The data granularity is automatically determined based on the time range:
    - **Single day** (e.g., "today"): Returns hourly breakdown (0-23 hours)
    - **Multiple days**: Returns daily aggregated totals

    ## Query Parameters

    ### Required
    - **project_id** (integer): The project ID to retrieve metrics for
    - **type** (string): Metric type to retrieve
      - `exception`: Exception/error logs (all errors regardless of status)
      - `endpoint`: API endpoint monitoring (HTTP requests with performance metrics)
      - `log_volume`: General log volume metrics (grouped by log level and type)

    - **Period selection** (one required):
      - **period** (string): Predefined time period
        - `today`: Current day (returns hourly data)
        - `last7days`: Last 7 days including today
        - `last30days`: Last 30 days including today
        - `currentWeek`: From Monday to today
        - `currentMonth`: From 1st of month to today
        - `currentYear`: From January 1st to today
      - **OR**
      - **periodFrom** + **periodTo** (string): Custom date range in ISO 8601 format (YYYY-MM-DD)

    ## Response Fields

    ### For Exception Metrics
    - `log_count`: Total number of exception logs
    - `error_count`: Same as log_count (all exceptions are errors)
    - Duration fields: `null` (not applicable)

    ### For Endpoint Metrics
    - `log_count`: Total number of API requests
    - `error_count`: Number of requests with status >= 400
    - `endpoint_method`: HTTP method (GET, POST, PUT, DELETE, etc.)
    - `endpoint_path`: Endpoint path template
    - `avg_duration_ms`: Average response time
    - `min_duration_ms`: Minimum response time
    - `max_duration_ms`: Maximum response time
    - `p95_duration_ms`: 95th percentile response time
    - `p99_duration_ms`: 99th percentile response time

    ### For Log Volume Metrics
    - `log_count`: Total number of logs
    - `error_count`: Number of logs with error/critical level
    - `log_level`: Log severity level (debug, info, warning, error, critical)
    - `log_type`: Type of log (console, logger, exception, network, database, endpoint, custom)
    - Duration fields: `null` (not applicable)

    ## Validation Rules

    1. **Period validation**:
       - Either `period` OR both `periodFrom` and `periodTo` must be provided
       - Cannot use both predefined period and custom dates

    2. **Date validation**:
       - Dates must be in ISO 8601 format (YYYY-MM-DD)
       - Dates cannot be in the future
       - `periodFrom` must be <= `periodTo`
       - Hours/minutes/seconds are ignored (always treated as full days)

    3. **Type validation**:
       - Must be exactly "exception", "endpoint", or "log_volume" (case-sensitive)

    ## Examples

    ### Today's hourly exception breakdown
    ```
    GET /api/v1/metrics/aggregated?type=exception&period=today
    ```

    ### Last 30 days of endpoint performance (daily aggregation)
    ```
    GET /api/v1/metrics/aggregated?type=endpoint&period=last30days
    ```

    ### Custom date range
    ```
    GET /api/v1/metrics/aggregated?type=endpoint&periodFrom=2025-11-01&periodTo=2025-11-21
    ```

    ### Log volume by level and type (today, hourly breakdown)
    ```
    GET /api/v1/metrics/aggregated?type=log_volume&period=today
    ```

    ## Use Cases

    - **Error tracking dashboards**: Monitor exception trends over time
    - **API performance monitoring**: Track endpoint latency and error rates
    - **Log volume analysis**: Track log patterns by level and type
    - **Capacity planning**: Analyze request and log volume patterns
    - **SLA monitoring**: Ensure response times meet targets
    - **Trend analysis**: Identify performance degradation or unusual log patterns

    Requires session token authentication via `Authorization: Bearer <token>` header.
    """
    grpc_pool = request.app.state.grpc_pool

    if not period and not (periodFrom and periodTo):
        raise fastapi.HTTPException(
            status_code=400,
            detail="Either 'period' or both 'periodFrom' and 'periodTo' must be provided",
        )

    if period and (periodFrom or periodTo):
        raise fastapi.HTTPException(
            status_code=400,
            detail="Cannot use both 'period' and 'periodFrom'/'periodTo' parameters",
        )

    period_from_date = None
    period_to_date = None

    if periodFrom:
        try:
            period_from_date = datetime.date.fromisoformat(periodFrom)
            today = datetime.date.today()
            if period_from_date > today:
                raise fastapi.HTTPException(
                    status_code=400, detail="periodFrom cannot be in the future"
                )
        except ValueError:
            raise fastapi.HTTPException(
                status_code=400,
                detail="periodFrom must be in ISO 8601 format (YYYY-MM-DD)",
            )

    if periodTo:
        try:
            period_to_date = datetime.date.fromisoformat(periodTo)
            today = datetime.date.today()
            if period_to_date > today:
                raise fastapi.HTTPException(
                    status_code=400, detail="periodTo cannot be in the future"
                )
        except ValueError:
            raise fastapi.HTTPException(
                status_code=400,
                detail="periodTo must be in ISO 8601 format (YYYY-MM-DD)",
            )

    if period_from_date and period_to_date and period_from_date > period_to_date:
        raise fastapi.HTTPException(
            status_code=400, detail="periodFrom must be before or equal to periodTo"
        )

    try:
        async with grpc_pool.get_query_stub() as stub:
            response = await stub.GetAggregatedMetrics(
                query_pb2.GetAggregatedMetricsRequest(
                    project_id=project_id,
                    metric_type=type,
                    period=period if period else "",
                    period_from=(
                        period_from_date.isoformat() if period_from_date else ""
                    ),
                    period_to=period_to_date.isoformat() if period_to_date else "",
                    endpoint_path=endpointPath if endpointPath else "",
                ),
                timeout=10.0,
            )

        data = [
            schemas.AggregatedMetricDataResponse(
                date=item.date,
                hour=item.hour if item.hour > 0 else None,
                endpoint_method=item.endpoint_method if item.endpoint_method else None,
                endpoint_path=item.endpoint_path if item.endpoint_path else None,
                log_level=item.log_level if item.log_level else None,
                log_type=item.log_type if item.log_type else None,
                log_count=item.log_count,
                error_count=item.error_count,
                avg_duration_ms=(
                    item.avg_duration_ms if item.avg_duration_ms > 0 else None
                ),
                min_duration_ms=(
                    item.min_duration_ms if item.min_duration_ms > 0 else None
                ),
                max_duration_ms=(
                    item.max_duration_ms if item.max_duration_ms > 0 else None
                ),
                p95_duration_ms=(
                    item.p95_duration_ms if item.p95_duration_ms > 0 else None
                ),
                p99_duration_ms=(
                    item.p99_duration_ms if item.p99_duration_ms > 0 else None
                ),
            )
            for item in response.data
        ]

        return schemas.AggregatedMetricsResponse(
            project_id=response.project_id,
            metric_type=response.metric_type,
            granularity=response.granularity,
            start_date=response.start_date,
            end_date=response.end_date,
            data=data,
        )

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=400,
                detail=e.details(),
            )
        else:
            logger.error(
                f"gRPC error retrieving aggregated metrics: {e.code()} - {e.details()}"
            )
            raise fastapi.HTTPException(
                status_code=500,
                detail="Failed to retrieve aggregated metrics",
            )

    except fastapi.HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to retrieve aggregated metrics: {e}", exc_info=True)
        raise fastapi.HTTPException(
            status_code=500,
            detail="Failed to retrieve aggregated metrics",
        )


def _proto_to_pydantic_log(proto_log: query_pb2.LogEntry) -> schemas.LogEntryResponse:
    """
    Convert protobuf LogEntry to Pydantic LogEntryResponse.

    Handles deserialization of datetime and JSON fields from protobuf format.
    """
    attributes = None
    if proto_log.attributes:
        try:
            attributes = json.loads(proto_log.attributes)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse attributes JSON for log {proto_log.id}")
            attributes = None

    return schemas.LogEntryResponse(
        id=proto_log.id,
        project_id=proto_log.project_id,
        timestamp=proto_log.timestamp,
        ingested_at=proto_log.ingested_at,
        level=proto_log.level,
        log_type=proto_log.log_type,
        importance=proto_log.importance,
        environment=proto_log.environment if proto_log.environment else None,
        release=proto_log.release if proto_log.release else None,
        message=proto_log.message if proto_log.message else None,
        error_type=proto_log.error_type if proto_log.error_type else None,
        error_message=proto_log.error_message if proto_log.error_message else None,
        stack_trace=proto_log.stack_trace if proto_log.stack_trace else None,
        attributes=attributes,
        sdk_version=proto_log.sdk_version if proto_log.sdk_version else None,
        platform=proto_log.platform if proto_log.platform else None,
        platform_version=(
            proto_log.platform_version if proto_log.platform_version else None
        ),
        processing_time_ms=(
            proto_log.processing_time_ms if proto_log.processing_time_ms else None
        ),
        error_fingerprint=(
            proto_log.error_fingerprint if proto_log.error_fingerprint else None
        ),
    )
