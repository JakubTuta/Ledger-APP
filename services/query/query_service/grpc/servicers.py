import datetime
import json

import grpc

import query_service.proto.query_pb2 as query_pb2
import query_service.proto.query_pb2_grpc as query_pb2_grpc
import query_service.schemas as schemas
import query_service.services.aggregated_metrics as aggregated_metrics_service
import query_service.services.bottleneck_metrics as bottleneck_metrics_service
import query_service.services.custom_metrics as custom_metrics_service
import query_service.services.health_summary as health_summary_service
import query_service.services.log_query as log_query
import query_service.services.metrics as metrics_service
import query_service.services.tracing as tracing_service


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
                status_class=list(request.status_class) if request.status_class else None,
                search=request.search if request.search else None,
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
                entry = query_pb2.LogEntry(
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
                if log.method is not None:
                    entry.method = log.method
                if log.path is not None:
                    entry.path = log.path
                if log.status_code is not None:
                    entry.status_code = log.status_code
                if log.duration_ms is not None:
                    entry.duration_ms = log.duration_ms
                log_entries.append(entry)

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
                entry = query_pb2.LogEntry(
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
                if log.method is not None:
                    entry.method = log.method
                if log.path is not None:
                    entry.path = log.path
                if log.status_code is not None:
                    entry.status_code = log.status_code
                if log.duration_ms is not None:
                    entry.duration_ms = log.duration_ms
                log_entries.append(entry)

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
            if log.method is not None:
                log_entry.method = log.method
            if log.path is not None:
                log_entry.path = log.path
            if log.status_code is not None:
                log_entry.status_code = log.status_code
            if log.duration_ms is not None:
                log_entry.duration_ms = log.duration_ms

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

    async def GetAggregatedMetrics(
        self,
        request: query_pb2.GetAggregatedMetricsRequest,
        context: grpc.aio.ServicerContext,
    ) -> query_pb2.GetAggregatedMetricsResponse:
        try:
            period_from = None
            period_to = None

            if request.period_from:
                period_from = datetime.date.fromisoformat(request.period_from)
            if request.period_to:
                period_to = datetime.date.fromisoformat(request.period_to)

            granularity = request.granularity if request.granularity else "daily"

            result = await aggregated_metrics_service.get_aggregated_metrics(
                project_id=request.project_id,
                metric_type=request.metric_type,
                period=request.period if request.period else None,
                period_from=period_from,
                period_to=period_to,
                endpoint_path=request.endpoint_path if request.endpoint_path else None,
                granularity=granularity,
            )

            start_date, end_date = aggregated_metrics_service._parse_period(
                period=request.period if request.period else None,
                period_from=period_from,
                period_to=period_to,
            )

            data_entries = [
                query_pb2.AggregatedMetricData(
                    date=item.date,
                    hour=item.hour if item.hour is not None else 0,
                    endpoint_method=item.endpoint_method or "",
                    endpoint_path=item.endpoint_path or "",
                    log_level=item.log_level or "",
                    log_type=item.log_type or "",
                    log_count=item.log_count,
                    error_count=item.error_count,
                    avg_duration_ms=item.avg_duration_ms or 0.0,
                    min_duration_ms=item.min_duration_ms or 0,
                    max_duration_ms=item.max_duration_ms or 0,
                    p95_duration_ms=item.p95_duration_ms or 0,
                    p99_duration_ms=item.p99_duration_ms or 0,
                )
                for item in result
            ]

            return query_pb2.GetAggregatedMetricsResponse(
                project_id=request.project_id,
                metric_type=request.metric_type,
                granularity=granularity,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                data=data_entries,
            )

        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

        except Exception as e:
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get aggregated metrics failed: {str(e)}"
            )

    async def GetErrorList(
        self,
        request: query_pb2.GetErrorListRequest,
        context: grpc.aio.ServicerContext,
    ) -> query_pb2.GetErrorListResponse:
        try:
            period_from = None
            period_to = None

            if request.period_from:
                period_from = datetime.datetime.fromisoformat(request.period_from)
            if request.period_to:
                period_to = datetime.datetime.fromisoformat(request.period_to)

            pagination = schemas.Pagination(
                limit=request.limit if request.limit > 0 else 100,
                offset=request.offset if request.offset >= 0 else 0,
            )

            result = await log_query.get_error_list(
                project_id=request.project_id,
                period=request.period if request.period else None,
                period_from=period_from,
                period_to=period_to,
                search=request.search if request.HasField("search") else None,
                pagination=pagination,
            )

            error_entries = []
            for error in result.errors:
                entry_kwargs = dict(
                    log_id=error.log_id,
                    project_id=error.project_id,
                    level=error.level,
                    log_type=error.log_type,
                    message=error.message,
                    error_type=error.error_type or "",
                    timestamp=error.timestamp.isoformat(),
                    error_fingerprint=error.error_fingerprint or "",
                    attributes=json.dumps(error.attributes) if error.attributes else "",
                    sdk_version=error.sdk_version or "",
                    platform=error.platform or "",
                    occurrence_count=error.occurrence_count,
                    first_seen=error.first_seen.isoformat() if error.first_seen else error.timestamp.isoformat(),
                    last_seen=error.last_seen.isoformat() if error.last_seen else error.timestamp.isoformat(),
                    latest_log_id=error.latest_log_id if error.latest_log_id is not None else error.log_id,
                )
                if error.group_key is not None:
                    entry_kwargs["group_key"] = error.group_key
                if error.status_code is not None:
                    entry_kwargs["status_code"] = error.status_code
                if error.path is not None:
                    entry_kwargs["path"] = error.path
                if error.stack_trace is not None:
                    entry_kwargs["stack_trace"] = error.stack_trace
                error_entries.append(query_pb2.ErrorListEntry(**entry_kwargs))

            return query_pb2.GetErrorListResponse(
                project_id=result.project_id,
                errors=error_entries,
                total=result.total,
                has_more=result.has_more,
            )

        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

        except Exception as e:
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get error list failed: {str(e)}"
            )

    async def GetBottleneckMetrics(
        self,
        request: query_pb2.GetBottleneckMetricsRequest,
        context: grpc.aio.ServicerContext,
    ) -> query_pb2.GetBottleneckMetricsResponse:
        await context.abort(
            grpc.StatusCode.UNIMPLEMENTED,
            "Bottleneck chart metrics removed; use GetBottleneckList",
        )

    async def GetBottleneckList(
        self,
        request: query_pb2.GetBottleneckListRequest,
        context: grpc.aio.ServicerContext,
    ) -> query_pb2.GetBottleneckListResponse:
        try:
            valid_statistics = ["min", "max", "avg", "median"]
            if request.statistic not in valid_statistics:
                await context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    f"Invalid statistic. Must be one of: {', '.join(valid_statistics)}",
                )

            valid_sorts = ["asc", "desc"]
            if request.sort not in valid_sorts:
                await context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    f"Invalid sort. Must be one of: {', '.join(valid_sorts)}",
                )

            period_from = None
            period_to = None
            if request.HasField("period_from"):
                period_from = datetime.date.fromisoformat(request.period_from)
            if request.HasField("period_to"):
                period_to = datetime.date.fromisoformat(request.period_to)

            result = await bottleneck_metrics_service.get_bottleneck_list(
                project_id=request.project_id,
                statistic=request.statistic,
                sort=request.sort,
                period=request.period if request.HasField("period") else None,
                period_from=period_from,
                period_to=period_to,
                limit=request.limit if request.limit > 0 else 25,
                offset=request.offset,
                search=request.search if request.HasField("search") else None,
            )

            entries = []
            for e in result.entries:
                entry_kwargs = dict(
                    route=e.route,
                    value=e.value,
                    request_count=e.request_count,
                )
                if e.min_value is not None:
                    entry_kwargs["min_value"] = e.min_value
                if e.max_value is not None:
                    entry_kwargs["max_value"] = e.max_value
                if e.avg_value is not None:
                    entry_kwargs["avg_value"] = e.avg_value
                if e.median_value is not None:
                    entry_kwargs["median_value"] = e.median_value
                entries.append(query_pb2.BottleneckListEntry(**entry_kwargs))

            return query_pb2.GetBottleneckListResponse(
                project_id=result.project_id,
                statistic=result.statistic,
                sort=result.sort,
                start_date=result.start_date,
                end_date=result.end_date,
                max_value=result.max_value,
                entries=entries,
                total=result.total,
                has_more=result.has_more,
            )

        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

        except Exception as e:
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get bottleneck list failed: {str(e)}"
            )

    async def GetHealthSummary(
        self,
        request: query_pb2.GetHealthSummaryRequest,
        context: grpc.aio.ServicerContext,
    ) -> query_pb2.GetHealthSummaryResponse:
        try:
            project_ids = [int(pid) for pid in request.project_ids]
            period = request.period if request.period else "today"

            summaries = await health_summary_service.get_health_summaries(
                project_ids=project_ids,
                period=period,
            )

            summary_messages = [
                query_pb2.HealthSummary(
                    project_id=s["project_id"],
                    error_rate=s["error_rate"],
                    p95_ms=s["p95_ms"],
                    rps=s["rps"],
                    status=s["status"],
                    sparkline=s["sparkline"],
                    thresholds=query_pb2.HealthThresholds(
                        error_rate_warn=s["thresholds"]["error_rate_warn"],
                        error_rate_crit=s["thresholds"]["error_rate_crit"],
                        p95_warn_ms=s["thresholds"]["p95_warn_ms"],
                        p95_crit_ms=s["thresholds"]["p95_crit_ms"],
                    ),
                    generated_at=s["generated_at"],
                )
                for s in summaries
            ]

            return query_pb2.GetHealthSummaryResponse(summaries=summary_messages)

        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

        except Exception as e:
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get health summary failed: {str(e)}"
            )

    # ==================== Distributed Tracing ====================

    async def GetTrace(
        self,
        request: query_pb2.GetTraceRequest,
        context: grpc.aio.ServicerContext,
    ) -> query_pb2.GetTraceResponse:
        try:
            trace = await tracing_service.get_trace(
                project_id=request.project_id, trace_id=request.trace_id
            )
            if not trace:
                return query_pb2.GetTraceResponse(found=False)
            spans = [
                query_pb2.SpanData(
                    span_id=s["span_id"],
                    trace_id=s["trace_id"],
                    parent_span_id=s["parent_span_id"],
                    project_id=s["project_id"],
                    service_name=s["service_name"],
                    name=s["name"],
                    kind=s["kind"],
                    start_time=s["start_time"],
                    duration_ns=s["duration_ns"],
                    status_code=s["status_code"],
                    status_message=s["status_message"],
                    attributes=s["attributes"],
                    events=s["events"],
                    error_fingerprint=s["error_fingerprint"],
                )
                for s in trace["spans"]
            ]
            return query_pb2.GetTraceResponse(
                trace_id=trace["trace_id"],
                spans=spans,
                duration_ms=trace["duration_ms"],
                services=trace["services"],
                root_span_id=trace["root_span_id"],
                found=True,
            )
        except Exception as e:
            await context.abort(grpc.StatusCode.INTERNAL, f"GetTrace failed: {str(e)}")

    async def ListTraces(
        self,
        request: query_pb2.ListTracesRequest,
        context: grpc.aio.ServicerContext,
    ) -> query_pb2.ListTracesResponse:
        try:
            result = await tracing_service.list_traces(
                project_id=request.project_id,
                service=request.service if request.HasField("service") else None,
                name=request.name if request.HasField("name") else None,
                min_duration_ms=request.min_duration_ms
                if request.HasField("min_duration_ms")
                else None,
                has_error=request.has_error if request.HasField("has_error") else None,
                from_time=request.from_time if request.HasField("from_time") else None,
                to_time=request.to_time if request.HasField("to_time") else None,
                limit=request.limit if request.limit > 0 else 50,
                offset=request.offset if request.offset >= 0 else 0,
            )
            traces = [
                query_pb2.TraceSummary(
                    trace_id=t["trace_id"],
                    root_span_id=t["root_span_id"],
                    root_name=t["root_name"],
                    service_name=t["service_name"],
                    start_time=t["start_time"],
                    duration_ms=t["duration_ms"],
                    span_count=t["span_count"],
                    has_error=t["has_error"],
                )
                for t in result["traces"]
            ]
            return query_pb2.ListTracesResponse(
                traces=traces, total=result["total"], has_more=result["has_more"]
            )
        except Exception as e:
            await context.abort(
                grpc.StatusCode.INTERNAL, f"ListTraces failed: {str(e)}"
            )

    async def GetSpanLatency(
        self,
        request: query_pb2.GetSpanLatencyRequest,
        context: grpc.aio.ServicerContext,
    ) -> query_pb2.GetSpanLatencyResponse:
        try:
            buckets = await tracing_service.get_span_latency(
                project_id=request.project_id,
                service=request.service if request.HasField("service") else None,
                name=request.name if request.HasField("name") else None,
                from_time=request.from_time if request.HasField("from_time") else None,
                to_time=request.to_time if request.HasField("to_time") else None,
            )
            data = [
                query_pb2.SpanLatencyBucket(
                    service_name=b["service_name"],
                    name=b["name"],
                    bucket=b["bucket"],
                    calls=b["calls"],
                    p50_ns=b["p50_ns"],
                    p95_ns=b["p95_ns"],
                    p99_ns=b["p99_ns"],
                    errors=b["errors"],
                )
                for b in buckets
            ]
            return query_pb2.GetSpanLatencyResponse(
                project_id=request.project_id, data=data
            )
        except Exception as e:
            await context.abort(
                grpc.StatusCode.INTERNAL, f"GetSpanLatency failed: {str(e)}"
            )

    # ==================== Custom Metrics ====================

    async def QueryCustomMetrics(
        self,
        request: query_pb2.QueryCustomMetricsRequest,
        context: grpc.aio.ServicerContext,
    ) -> query_pb2.QueryCustomMetricsResponse:
        try:
            agg = request.agg if request.HasField("agg") else "sum"
            step = request.step_seconds if request.HasField("step_seconds") else 300
            points = await custom_metrics_service.query_custom_metrics(
                project_id=request.project_id,
                name=request.name,
                tags=request.tags,
                from_time=request.from_time if request.HasField("from_time") else None,
                to_time=request.to_time if request.HasField("to_time") else None,
                agg=agg,
                step_seconds=step,
            )
            data = [
                query_pb2.CustomMetricDataPoint(bucket=p["bucket"], value=p["value"])
                for p in points
            ]
            return query_pb2.QueryCustomMetricsResponse(
                project_id=request.project_id,
                name=request.name,
                agg=agg,
                data=data,
            )
        except Exception as e:
            await context.abort(
                grpc.StatusCode.INTERNAL, f"QueryCustomMetrics failed: {str(e)}"
            )

    async def ListCustomMetricNames(
        self,
        request: query_pb2.ListCustomMetricNamesRequest,
        context: grpc.aio.ServicerContext,
    ) -> query_pb2.ListCustomMetricNamesResponse:
        try:
            names = await custom_metrics_service.list_metric_names(
                project_id=request.project_id,
                prefix=request.prefix if request.HasField("prefix") else None,
            )
            return query_pb2.ListCustomMetricNamesResponse(names=names)
        except Exception as e:
            await context.abort(
                grpc.StatusCode.INTERNAL, f"ListCustomMetricNames failed: {str(e)}"
            )

    async def ListCustomMetricTags(
        self,
        request: query_pb2.ListCustomMetricTagsRequest,
        context: grpc.aio.ServicerContext,
    ) -> query_pb2.ListCustomMetricTagsResponse:
        try:
            tag_entries = await custom_metrics_service.list_metric_tags(
                project_id=request.project_id, name=request.name
            )
            tags = [
                query_pb2.CustomMetricTagEntry(key=t["key"], values=t["values"])
                for t in tag_entries
            ]
            return query_pb2.ListCustomMetricTagsResponse(tags=tags)
        except Exception as e:
            await context.abort(
                grpc.StatusCode.INTERNAL, f"ListCustomMetricTags failed: {str(e)}"
            )
