import datetime
import json

import grpc

import query_service.proto.query_pb2 as query_pb2
import query_service.proto.query_pb2_grpc as query_pb2_grpc
import query_service.schemas as schemas
import query_service.services.log_query as log_query
import query_service.services.metrics as metrics_service


class QueryServiceServicer(query_pb2_grpc.QueryServiceServicer):
    async def QueryLogs(
        self, request: query_pb2.QueryLogsRequest, context: grpc.aio.ServicerContext
    ) -> query_pb2.QueryLogsResponse:
        try:
            filters = schemas.LogFilters(
                start_time=(
                    datetime.datetime.fromisoformat(request.start_time)
                    if request.start_time
                    else None
                ),
                end_time=(
                    datetime.datetime.fromisoformat(request.end_time)
                    if request.end_time
                    else None
                ),
                level=request.level if request.level else None,
                log_type=request.log_type if request.log_type else None,
                environment=request.environment if request.environment else None,
                error_fingerprint=(
                    request.error_fingerprint if request.error_fingerprint else None
                ),
            )

            pagination = schemas.Pagination(
                limit=request.limit if request.limit > 0 else 100,
                offset=request.offset if request.offset >= 0 else 0,
            )

            result = await log_query.query_logs(
                project_id=request.project_id, filters=filters, pagination=pagination
            )

            log_entries = []
            for log in result.logs:
                log_entries.append(
                    query_pb2.LogEntry(
                        id=log.id,
                        project_id=log.project_id,
                        timestamp=log.timestamp.isoformat(),
                        ingested_at=log.ingested_at.isoformat(),
                        level=log.level,
                        log_type=log.log_type,
                        importance=log.importance,
                        environment=log.environment or "",
                        release=log.release or "",
                        message=log.message or "",
                        error_type=log.error_type or "",
                        error_message=log.error_message or "",
                        stack_trace=log.stack_trace or "",
                        attributes=json.dumps(log.attributes) if log.attributes else "",
                        sdk_version=log.sdk_version or "",
                        platform=log.platform or "",
                        platform_version=log.platform_version or "",
                        processing_time_ms=log.processing_time_ms or 0,
                        error_fingerprint=log.error_fingerprint or "",
                    )
                )

            return query_pb2.QueryLogsResponse(
                logs=log_entries, total=result.total, has_more=result.has_more
            )

        except Exception as e:
            await context.abort(grpc.StatusCode.INTERNAL, f"Query failed: {str(e)}")

    async def SearchLogs(
        self, request: query_pb2.SearchLogsRequest, context: grpc.aio.ServicerContext
    ) -> query_pb2.SearchLogsResponse:
        try:
            pagination = schemas.Pagination(
                limit=request.limit if request.limit > 0 else 100,
                offset=request.offset if request.offset >= 0 else 0,
            )

            result = await log_query.search_logs(
                project_id=request.project_id,
                search_query=request.query,
                start_time=(
                    datetime.datetime.fromisoformat(request.start_time)
                    if request.start_time
                    else None
                ),
                end_time=(
                    datetime.datetime.fromisoformat(request.end_time)
                    if request.end_time
                    else None
                ),
                pagination=pagination,
            )

            log_entries = []
            for log in result.logs:
                log_entries.append(
                    query_pb2.LogEntry(
                        id=log.id,
                        project_id=log.project_id,
                        timestamp=log.timestamp.isoformat(),
                        ingested_at=log.ingested_at.isoformat(),
                        level=log.level,
                        log_type=log.log_type,
                        importance=log.importance,
                        environment=log.environment or "",
                        release=log.release or "",
                        message=log.message or "",
                        error_type=log.error_type or "",
                        error_message=log.error_message or "",
                        stack_trace=log.stack_trace or "",
                        attributes=json.dumps(log.attributes) if log.attributes else "",
                        sdk_version=log.sdk_version or "",
                        platform=log.platform or "",
                        platform_version=log.platform_version or "",
                        processing_time_ms=log.processing_time_ms or 0,
                        error_fingerprint=log.error_fingerprint or "",
                    )
                )

            return query_pb2.SearchLogsResponse(
                logs=log_entries, total=result.total, has_more=result.has_more
            )

        except Exception as e:
            await context.abort(grpc.StatusCode.INTERNAL, f"Search failed: {str(e)}")

    async def GetLog(
        self, request: query_pb2.GetLogRequest, context: grpc.aio.ServicerContext
    ) -> query_pb2.GetLogResponse:
        try:
            log = await log_query.get_log_by_id(
                log_id=request.log_id, project_id=request.project_id
            )

            if not log:
                return query_pb2.GetLogResponse(found=False)

            log_entry = query_pb2.LogEntry(
                id=log.id,
                project_id=log.project_id,
                timestamp=log.timestamp.isoformat(),
                ingested_at=log.ingested_at.isoformat(),
                level=log.level,
                log_type=log.log_type,
                importance=log.importance,
                environment=log.environment or "",
                release=log.release or "",
                message=log.message or "",
                error_type=log.error_type or "",
                error_message=log.error_message or "",
                stack_trace=log.stack_trace or "",
                attributes=json.dumps(log.attributes) if log.attributes else "",
                sdk_version=log.sdk_version or "",
                platform=log.platform or "",
                platform_version=log.platform_version or "",
                processing_time_ms=log.processing_time_ms or 0,
                error_fingerprint=log.error_fingerprint or "",
            )

            return query_pb2.GetLogResponse(log=log_entry, found=True)

        except Exception as e:
            await context.abort(grpc.StatusCode.INTERNAL, f"Get log failed: {str(e)}")

    async def GetErrorRate(
        self, request: query_pb2.GetErrorRateRequest, context: grpc.aio.ServicerContext
    ) -> query_pb2.GetErrorRateResponse:
        try:
            result = await metrics_service.get_error_rate(
                project_id=request.project_id,
                interval=request.interval if request.interval else "5min",
                start_time=(
                    datetime.datetime.fromisoformat(request.start_time)
                    if request.start_time
                    else None
                ),
                end_time=(
                    datetime.datetime.fromisoformat(request.end_time)
                    if request.end_time
                    else None
                ),
            )

            data_entries = [
                query_pb2.ErrorRateData(
                    timestamp=item.timestamp.isoformat(),
                    error_count=item.error_count,
                    critical_count=item.critical_count,
                )
                for item in result.data
            ]

            return query_pb2.GetErrorRateResponse(
                project_id=result.project_id,
                interval=result.interval,
                data=data_entries,
            )

        except Exception as e:
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get error rate failed: {str(e)}"
            )

    async def GetLogVolume(
        self, request: query_pb2.GetLogVolumeRequest, context: grpc.aio.ServicerContext
    ) -> query_pb2.GetLogVolumeResponse:
        try:
            result = await metrics_service.get_log_volume(
                project_id=request.project_id,
                interval=request.interval if request.interval else "1hour",
                start_time=(
                    datetime.datetime.fromisoformat(request.start_time)
                    if request.start_time
                    else None
                ),
                end_time=(
                    datetime.datetime.fromisoformat(request.end_time)
                    if request.end_time
                    else None
                ),
            )

            data_entries = [
                query_pb2.LogVolumeData(
                    timestamp=item.timestamp.isoformat(),
                    debug=item.debug,
                    info=item.info,
                    warning=item.warning,
                    error=item.error,
                    critical=item.critical,
                )
                for item in result.data
            ]

            return query_pb2.GetLogVolumeResponse(
                project_id=result.project_id,
                interval=result.interval,
                data=data_entries,
            )

        except Exception as e:
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get log volume failed: {str(e)}"
            )

    async def GetTopErrors(
        self, request: query_pb2.GetTopErrorsRequest, context: grpc.aio.ServicerContext
    ) -> query_pb2.GetTopErrorsResponse:
        try:
            result = await metrics_service.get_top_errors(
                project_id=request.project_id,
                limit=request.limit if request.limit > 0 else 10,
                start_time=(
                    datetime.datetime.fromisoformat(request.start_time)
                    if request.start_time
                    else None
                ),
                end_time=(
                    datetime.datetime.fromisoformat(request.end_time)
                    if request.end_time
                    else None
                ),
                status=request.status if request.status else None,
            )

            error_entries = [
                query_pb2.TopErrorData(
                    fingerprint=error.fingerprint,
                    error_type=error.error_type,
                    error_message=error.error_message or "",
                    occurrence_count=error.occurrence_count,
                    first_seen=error.first_seen.isoformat(),
                    last_seen=error.last_seen.isoformat(),
                    status=error.status,
                    sample_log_id=error.sample_log_id or 0,
                )
                for error in result.errors
            ]

            return query_pb2.GetTopErrorsResponse(
                project_id=result.project_id, errors=error_entries
            )

        except Exception as e:
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get top errors failed: {str(e)}"
            )

    async def GetUsageStats(
        self, request: query_pb2.GetUsageStatsRequest, context: grpc.aio.ServicerContext
    ) -> query_pb2.GetUsageStatsResponse:
        try:
            result = await metrics_service.get_usage_stats(
                project_id=request.project_id,
                start_date=(
                    datetime.date.fromisoformat(request.start_date)
                    if request.start_date
                    else None
                ),
                end_date=(
                    datetime.date.fromisoformat(request.end_date)
                    if request.end_date
                    else None
                ),
            )

            usage_entries = [
                query_pb2.UsageStatsData(
                    date=usage.date.isoformat(),
                    log_count=usage.log_count,
                    daily_quota=usage.daily_quota,
                    quota_used_percent=usage.quota_used_percent,
                )
                for usage in result.usage
            ]

            return query_pb2.GetUsageStatsResponse(
                project_id=result.project_id, usage=usage_entries
            )

        except Exception as e:
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get usage stats failed: {str(e)}"
            )
