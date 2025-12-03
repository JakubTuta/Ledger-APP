import datetime
import json
import logging
import typing

import fastapi
import gateway_service.proto.query_pb2 as query_pb2
import gateway_service.schemas as schemas
import grpc
from pydantic import field_validator

router = fastapi.APIRouter(tags=["Query"])
logger = logging.getLogger(__name__)


def _calculate_granularity_for_period(
    period: str,
) -> typing.Literal["hourly", "daily", "weekly", "monthly"]:
    """
    Calculate the appropriate granularity for predefined periods.

    Rules:
    - today: hourly
    - last7days: daily
    - last30days: daily
    - currentWeek: daily
    - currentMonth: daily
    - currentYear: monthly
    """
    granularity_map: dict[
        str, typing.Literal["hourly", "daily", "weekly", "monthly"]
    ] = {
        "today": "hourly",
        "last7days": "daily",
        "last30days": "daily",
        "currentWeek": "daily",
        "currentMonth": "daily",
        "currentYear": "monthly",
    }
    result = granularity_map.get(period)
    if result is None:
        return "daily"
    return result


def _calculate_granularity_for_date_range(
    start_date: datetime.date, end_date: datetime.date
) -> typing.Literal["hourly", "daily", "weekly", "monthly"]:
    """
    Calculate the appropriate granularity based on date range duration.

    Rules:
    - 0 to 1 day: hourly
    - 1 day to 1 month (30 days): daily
    - 1 month to 6 months (180 days): weekly
    - Above 6 months: monthly
    """
    delta = (end_date - start_date).days

    if delta <= 1:
        return "hourly"
    elif delta <= 30:
        return "daily"
    elif delta <= 180:
        return "weekly"
    else:
        return "monthly"


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
                "application/json": {"example": {"detail": "Invalid log ID format"}}
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
    type: typing.Literal["exception", "endpoint", "log_volume"] = fastapi.Query(
        ...,
        description="Metric type to retrieve (exception for error tracking, endpoint for API monitoring, log_volume for log volume metrics)",
    ),
    period: typing.Optional[
        typing.Literal[
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
    periodFrom: typing.Optional[str] = fastapi.Query(
        None,
        description="Start date in ISO 8601 format (YYYY-MM-DD). Must be used with periodTo.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    periodTo: typing.Optional[str] = fastapi.Query(
        None,
        description="End date in ISO 8601 format (YYYY-MM-DD). Must be used with periodFrom.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    endpointPath: typing.Optional[str] = fastapi.Query(
        None,
        description="Filter by specific endpoint path (e.g., /api/users). Only applicable when type=endpoint.",
    ),
) -> schemas.AggregatedMetricsResponse:
    """
    Retrieve aggregated metrics for a project.

    This endpoint returns pre-aggregated metrics computed by analytics workers.
    The data granularity is **automatically determined** based on the time range for optimal visualization:

    ### Granularity for Predefined Periods
    - **today**: Hourly breakdown (24 data points, 0-23 hours)
    - **last7days**: Daily breakdown (7 data points)
    - **last30days**: Daily breakdown (30 data points)
    - **currentWeek**: Daily breakdown (up to 7 data points)
    - **currentMonth**: Daily breakdown (up to 31 data points)
    - **currentYear**: Monthly breakdown (up to 12 data points)

    ### Granularity for Custom Date Ranges (periodFrom/periodTo)
    - **0-1 day**: Hourly breakdown (up to 24 hours)
    - **1 day - 30 days**: Daily breakdown
    - **30 days - 180 days**: Weekly breakdown
    - **Above 180 days**: Monthly breakdown

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

    ## Response Structure

    The response includes a `granularity` field indicating the time bucket size:
    - `"hourly"`: Data grouped by hour (includes `hour` field: 0-23)
    - `"daily"`: Data grouped by day (includes `date` field only)
    - `"weekly"`: Data grouped by week (includes `date` field for week start)
    - `"monthly"`: Data grouped by month (includes `date` field for month start)

    ## Response Fields

    ### Common Fields (All Metric Types)
    - `date`: Date in ISO 8601 format (YYYY-MM-DD)
    - `hour`: Hour of day (0-23) - only present for hourly granularity
    - `log_count`: Total number of logs in this time bucket
    - `error_count`: Number of error-level logs in this time bucket

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

    ### Today's hourly exception breakdown (24 hourly buckets)
    ```
    GET /api/v1/metrics/aggregated?project_id=1&type=exception&period=today
    Response granularity: "hourly"
    ```

    ### Last 30 days of endpoint performance (30 daily buckets)
    ```
    GET /api/v1/metrics/aggregated?project_id=1&type=endpoint&period=last30days
    Response granularity: "daily"
    ```

    ### Current year endpoint metrics (monthly aggregation, up to 12 buckets)
    ```
    GET /api/v1/metrics/aggregated?project_id=1&type=endpoint&period=currentYear
    Response granularity: "monthly"
    ```

    ### Custom date range - 2 weeks (daily aggregation, 14 buckets)
    ```
    GET /api/v1/metrics/aggregated?project_id=1&type=endpoint&periodFrom=2025-11-01&periodTo=2025-11-14
    Response granularity: "daily"
    ```

    ### Custom date range - 3 months (weekly aggregation, ~12-13 buckets)
    ```
    GET /api/v1/metrics/aggregated?project_id=1&type=endpoint&periodFrom=2025-08-01&periodTo=2025-11-01
    Response granularity: "weekly"
    ```

    ### Custom date range - 1 year (monthly aggregation, 12 buckets)
    ```
    GET /api/v1/metrics/aggregated?project_id=1&type=endpoint&periodFrom=2024-11-01&periodTo=2025-11-01
    Response granularity: "monthly"
    ```

    ### Log volume by level and type (today, hourly breakdown)
    ```
    GET /api/v1/metrics/aggregated?project_id=1&type=log_volume&period=today
    Response granularity: "hourly"
    ```

    ## Use Cases

    - **Error tracking dashboards**: Monitor exception trends with appropriate granularity
    - **API performance monitoring**: Track endpoint latency and error rates at scale
    - **Log volume analysis**: Track log patterns by level and type over time
    - **Capacity planning**: Analyze request and log volume patterns with weekly/monthly trends
    - **SLA monitoring**: Ensure response times meet targets with hourly precision
    - **Trend analysis**: Identify performance degradation with multi-granularity analysis
    - **Executive reporting**: Monthly/yearly summaries for high-level insights

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

    granularity: typing.Literal["hourly", "daily", "weekly", "monthly"]
    if period:
        granularity = _calculate_granularity_for_period(period)
    elif period_from_date and period_to_date:
        granularity = _calculate_granularity_for_date_range(
            period_from_date, period_to_date
        )
    else:
        granularity = "daily"

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
                    granularity=granularity,
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


@router.get(
    "/errors/list",
    status_code=200,
    summary="Get error list for dashboard panel",
    description="Retrieve individual error/critical log entries for a specified time period. Returns error data matching the SSE notification format for dashboard panels.",
    response_description="List of error entries",
    response_model=schemas.ErrorListResponse,
    responses={
        400: {
            "description": "Invalid parameters",
            "content": {
                "application/json": {
                    "examples": {
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
                    }
                }
            },
        },
        500: {
            "description": "Server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to retrieve error list"}
                }
            },
        },
    },
)
async def get_error_list(
    request: fastapi.Request,
    project_id: int = fastapi.Query(
        ...,
        description="The project ID to retrieve errors from",
        gt=0,
    ),
    period: typing.Optional[
        typing.Literal[
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
    periodFrom: typing.Optional[str] = fastapi.Query(
        None,
        description="Start date in ISO 8601 format (YYYY-MM-DD). Must be used with periodTo.",
        pattern=r"^\\d{4}-\\d{2}-\\d{2}$",
    ),
    periodTo: typing.Optional[str] = fastapi.Query(
        None,
        description="End date in ISO 8601 format (YYYY-MM-DD). Must be used with periodFrom.",
        pattern=r"^\\d{4}-\\d{2}-\\d{2}$",
    ),
    limit: int = fastapi.Query(
        100,
        description="Maximum number of errors to return",
        ge=1,
        le=1000,
    ),
    offset: int = fastapi.Query(
        0,
        description="Number of errors to skip for pagination",
        ge=0,
    ),
) -> schemas.ErrorListResponse:
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

    try:
        async with grpc_pool.get_query_stub() as stub:
            response = await stub.GetErrorList(
                query_pb2.GetErrorListRequest(
                    project_id=project_id,
                    period=period if period else "",
                    period_from=periodFrom if periodFrom else "",
                    period_to=periodTo if periodTo else "",
                    limit=limit,
                    offset=offset,
                ),
                timeout=10.0,
            )

        errors = []
        for error in response.errors:
            attributes = None
            if error.attributes:
                try:
                    attributes = json.loads(error.attributes)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Failed to parse attributes JSON for error {error.log_id}"
                    )
                    attributes = None

            errors.append(
                schemas.ErrorListEntryResponse(
                    log_id=error.log_id,
                    project_id=error.project_id,
                    level=error.level,
                    log_type=error.log_type,
                    message=error.message,
                    error_type=error.error_type if error.error_type else None,
                    timestamp=error.timestamp,
                    error_fingerprint=(
                        error.error_fingerprint if error.error_fingerprint else None
                    ),
                    attributes=attributes,
                    sdk_version=error.sdk_version if error.sdk_version else None,
                    platform=error.platform if error.platform else None,
                )
            )

        return schemas.ErrorListResponse(
            project_id=response.project_id,
            errors=errors,
            total=response.total,
            has_more=response.has_more,
        )

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise fastapi.HTTPException(
                status_code=400,
                detail=e.details(),
            )
        else:
            logger.error(
                f"gRPC error retrieving error list: {e.code()} - {e.details()}"
            )
            raise fastapi.HTTPException(
                status_code=500,
                detail="Failed to retrieve error list",
            )

    except fastapi.HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to retrieve error list: {e}", exc_info=True)
        raise fastapi.HTTPException(
            status_code=500,
            detail="Failed to retrieve error list",
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
