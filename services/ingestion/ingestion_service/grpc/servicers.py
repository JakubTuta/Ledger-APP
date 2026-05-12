import datetime
import hashlib
import json
import logging
import re

import grpc
import sqlalchemy as sa

import ingestion_service.config as config
import ingestion_service.database as database
import ingestion_service.notifications as notifications
import ingestion_service.proto.ingestion_pb2 as ingestion_pb2
import ingestion_service.proto.ingestion_pb2_grpc as ingestion_pb2_grpc
import ingestion_service.schemas as schemas
import ingestion_service.services.enricher as enricher
import ingestion_service.services.queue_service as queue_service

logger = logging.getLogger(__name__)

_HEX32_RE = re.compile(r"^[0-9a-f]{32}$")
_HEX16_RE = re.compile(r"^[0-9a-f]{16}$")


class IngestionServicer(ingestion_pb2_grpc.IngestionServiceServicer):
    def __init__(self, redis_client=None):
        self.notification_publisher = None
        if redis_client and config.settings.NOTIFICATIONS_ENABLED:
            self.notification_publisher = notifications.NotificationPublisher(
                redis_client,
                enabled=config.settings.NOTIFICATIONS_ENABLED
            )
    async def IngestLog(
        self, request: ingestion_pb2.IngestLogRequest, context: grpc.aio.ServicerContext
    ) -> ingestion_pb2.IngestLogResponse:
        try:
            log_entry = _proto_to_log_entry(request.log)

            enriched_log = enricher.enrich_log_entry(log_entry, request.project_id)

            await queue_service.enqueue_log(enriched_log)

            if self.notification_publisher:
                log = enriched_log.log_entry
                if self.notification_publisher.should_notify(
                    log.level,
                    log.log_type,
                    config.settings.NOTIFICATIONS_PUBLISH_ERRORS,
                    config.settings.NOTIFICATIONS_PUBLISH_CRITICAL
                ):
                    notification = notifications.ErrorNotification(
                        project_id=enriched_log.project_id,
                        level=log.level,
                        log_type=log.log_type,
                        message=log.message[:500] if log.message else "",
                        error_type=log.error_type,
                        timestamp=log.timestamp,
                        error_fingerprint=enriched_log.error_fingerprint,
                        attributes=log.attributes or {},
                        sdk_version=log.sdk_version,
                        platform=log.platform
                    )
                    await self.notification_publisher.publish_error_notification(
                        enriched_log.project_id,
                        notification
                    )

            return ingestion_pb2.IngestLogResponse(
                success=True,
                message="Log accepted for processing",
            )

        except queue_service.QueueFullError as e:
            logger.warning(f"Queue full for project {request.project_id}: {e}")
            await context.abort(
                grpc.StatusCode.RESOURCE_EXHAUSTED,
                "Service temporarily unavailable - queue full",
            )

        except ValueError as e:
            logger.warning(f"Validation error for project {request.project_id}: {e}")
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Invalid log entry: {str(e)}",
            )

        except Exception as e:
            logger.error(f"Failed to ingest log: {e}", exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                "Failed to ingest log",
            )

    async def IngestLogBatch(
        self,
        request: ingestion_pb2.IngestLogBatchRequest,
        context: grpc.aio.ServicerContext,
    ) -> ingestion_pb2.IngestLogBatchResponse:
        queued = 0
        failed = 0
        error_messages = []

        try:
            enriched_logs = []

            for idx, proto_log in enumerate(request.logs):
                try:
                    log_entry = _proto_to_log_entry(proto_log)
                    enriched_log = enricher.enrich_log_entry(
                        log_entry, request.project_id
                    )
                    enriched_logs.append(enriched_log)
                    queued += 1

                except ValueError as e:
                    failed += 1
                    error_messages.append(f"Log {idx}: {str(e)}")
                    logger.warning(
                        f"Validation error for log {idx} in project {request.project_id}: {e}"
                    )

                except Exception as e:
                    failed += 1
                    error_messages.append(f"Log {idx}: {str(e)}")
                    logger.warning(
                        f"Failed to enrich log {idx} in project {request.project_id}: {e}"
                    )

            if enriched_logs:
                await queue_service.enqueue_logs_batch(enriched_logs)

                if self.notification_publisher:
                    for enriched_log in enriched_logs:
                        log = enriched_log.log_entry
                        if self.notification_publisher.should_notify(
                            log.level,
                            log.log_type,
                            config.settings.NOTIFICATIONS_PUBLISH_ERRORS,
                            config.settings.NOTIFICATIONS_PUBLISH_CRITICAL
                        ):
                            notification = notifications.ErrorNotification(
                                project_id=enriched_log.project_id,
                                level=log.level,
                                log_type=log.log_type,
                                message=log.message[:500] if log.message else "",
                                error_type=log.error_type,
                                timestamp=log.timestamp,
                                error_fingerprint=enriched_log.error_fingerprint,
                                attributes=log.attributes or {},
                                sdk_version=log.sdk_version,
                                platform=log.platform
                            )
                            await self.notification_publisher.publish_error_notification(
                                enriched_log.project_id,
                                notification
                            )

            error_str = "; ".join(error_messages) if error_messages else None

            return ingestion_pb2.IngestLogBatchResponse(
                success=True,
                queued=queued,
                failed=failed,
                error=error_str,
            )

        except queue_service.QueueFullError as e:
            logger.warning(f"Queue full for project {request.project_id}: {e}")
            await context.abort(
                grpc.StatusCode.RESOURCE_EXHAUSTED,
                "Service temporarily unavailable - queue full",
            )

        except Exception as e:
            logger.error(f"Failed to ingest batch: {e}", exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                "Failed to ingest batch",
            )

    async def GetQueueDepth(
        self,
        request: ingestion_pb2.QueueDepthRequest,
        context: grpc.aio.ServicerContext,
    ) -> ingestion_pb2.QueueDepthResponse:
        try:
            depth = await queue_service.get_queue_depth(request.project_id)
            return ingestion_pb2.QueueDepthResponse(depth=depth)

        except Exception as e:
            logger.error(f"Failed to get queue depth: {e}", exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                "Failed to get queue depth",
            )

    async def IngestSpansBatch(
        self,
        request: ingestion_pb2.IngestSpansBatchRequest,
        context: grpc.aio.ServicerContext,
    ) -> ingestion_pb2.IngestSpansBatchResponse:
        accepted = 0
        rejected = 0
        rows = []

        for span in request.spans:
            trace_id = span.trace_id.lower()
            span_id = span.span_id.lower()
            if not _HEX32_RE.match(trace_id) or not _HEX16_RE.match(span_id):
                rejected += 1
                continue

            start_dt = datetime.datetime.fromtimestamp(
                span.start_unix_nano / 1e9, tz=datetime.timezone.utc
            )
            end_dt = datetime.datetime.fromtimestamp(
                span.end_unix_nano / 1e9, tz=datetime.timezone.utc
            )
            duration_ns = span.end_unix_nano - span.start_unix_nano

            status_code = int(span.status)
            attrs_json = json.dumps(dict(span.attributes))
            events_json = json.dumps(
                [
                    {
                        "name": e.name,
                        "ts": e.ts_unix_nano,
                        "attrs": dict(e.attrs),
                    }
                    for e in span.events
                ]
            )

            error_fingerprint = None
            if status_code == 2:
                raw = f"{request.project_id}:{span.service_name}:{span.name}"
                error_fingerprint = hashlib.sha256(raw.encode()).hexdigest()[:16]

            rows.append(
                {
                    "span_id": span_id,
                    "trace_id": trace_id,
                    "parent_span_id": span.parent_span_id or None,
                    "project_id": request.project_id,
                    "service_name": span.service_name[:255],
                    "name": span.name[:255],
                    "kind": int(span.kind),
                    "start_time": start_dt,
                    "duration_ns": duration_ns,
                    "status_code": status_code,
                    "status_message": span.status_message[:500],
                    "attributes": attrs_json,
                    "events": events_json,
                    "error_fingerprint": error_fingerprint,
                }
            )
            accepted += 1

        if rows:
            try:
                async with database.get_session() as session:
                    await session.execute(
                        sa.text("""
                            INSERT INTO spans (
                                span_id, trace_id, parent_span_id, project_id,
                                service_name, name, kind, start_time, duration_ns,
                                status_code, status_message, attributes, events, error_fingerprint
                            ) VALUES (
                                :span_id, :trace_id, :parent_span_id, :project_id,
                                :service_name, :name, :kind, :start_time, :duration_ns,
                                :status_code, :status_message, :attributes, :events, :error_fingerprint
                            )
                            ON CONFLICT (span_id, start_time) DO NOTHING
                        """),
                        rows,
                    )
                    await session.commit()
            except Exception as e:
                logger.error(f"Failed to insert spans batch: {e}", exc_info=True)
                await context.abort(grpc.StatusCode.INTERNAL, "Failed to store spans")
                return

        return ingestion_pb2.IngestSpansBatchResponse(
            success=True, accepted=accepted, rejected=rejected
        )

    async def IngestMetricsBatch(
        self,
        request: ingestion_pb2.IngestMetricsBatchRequest,
        context: grpc.aio.ServicerContext,
    ) -> ingestion_pb2.IngestMetricsBatchResponse:
        accepted = 0
        rejected = 0
        rows = []

        for m in request.metrics:
            if not m.name:
                rejected += 1
                continue

            ts_dt = datetime.datetime.fromtimestamp(
                m.ts_unix_nano / 1e9, tz=datetime.timezone.utc
            )
            rows.append(
                {
                    "project_id": request.project_id,
                    "name": m.name[:255],
                    "tags": m.tags or "{}",
                    "ts": ts_dt,
                    "type": m.type,
                    "count": m.count,
                    "sum": m.sum,
                    "min_v": m.min_v,
                    "max_v": m.max_v,
                    "buckets": m.buckets or "{}",
                }
            )
            accepted += 1

        if rows:
            try:
                async with database.get_session() as session:
                    await session.execute(
                        sa.text("""
                            INSERT INTO custom_metrics (
                                project_id, name, tags, ts, type, count, sum, min_v, max_v, buckets
                            ) VALUES (
                                :project_id, :name, :tags, :ts, :type, :count, :sum, :min_v, :max_v, :buckets
                            )
                        """),
                        rows,
                    )
                    await session.commit()
            except Exception as e:
                logger.error(f"Failed to insert metrics batch: {e}", exc_info=True)
                await context.abort(grpc.StatusCode.INTERNAL, "Failed to store metrics")
                return

        return ingestion_pb2.IngestMetricsBatchResponse(
            success=True, accepted=accepted, rejected=rejected
        )


def _proto_to_log_entry(proto_log: ingestion_pb2.LogEntry) -> schemas.LogEntry:
    try:
        timestamp = datetime.datetime.fromisoformat(proto_log.timestamp.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"Invalid timestamp format: {proto_log.timestamp}")

    attributes = None
    if proto_log.HasField("attributes"):
        try:
            attributes = json.loads(proto_log.attributes)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON in attributes field")

    return schemas.LogEntry(
        timestamp=timestamp,
        level=proto_log.level,
        log_type=proto_log.log_type,
        importance=proto_log.importance,
        message=proto_log.message if proto_log.HasField("message") else None,
        error_type=proto_log.error_type if proto_log.HasField("error_type") else None,
        error_message=proto_log.error_message if proto_log.HasField("error_message") else None,
        stack_trace=proto_log.stack_trace if proto_log.HasField("stack_trace") else None,
        environment=proto_log.environment if proto_log.HasField("environment") else None,
        release=proto_log.release if proto_log.HasField("release") else None,
        sdk_version=proto_log.sdk_version if proto_log.HasField("sdk_version") else None,
        platform=proto_log.platform if proto_log.HasField("platform") else None,
        platform_version=proto_log.platform_version if proto_log.HasField("platform_version") else None,
        attributes=attributes,
    )
