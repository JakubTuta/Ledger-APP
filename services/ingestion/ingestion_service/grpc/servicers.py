import datetime
import hashlib
import json
import logging
import re
import typing

import grpc

import ingestion_service.config as config
import ingestion_service.notifications as notifications
import ingestion_service.proto.ingestion_pb2 as ingestion_pb2
import ingestion_service.proto.ingestion_pb2_grpc as ingestion_pb2_grpc
import ingestion_service.schemas as schemas
import ingestion_service.services.enricher as enricher
import ingestion_service.services.queue_service as queue_service

logger = logging.getLogger(__name__)

_HEX32_RE = re.compile(r"^[0-9a-f]{32}$")
_HEX16_RE = re.compile(r"^[0-9a-f]{16}$")
_MAX_SPAN_DURATION_NS = config.settings.MAX_SPAN_DURATION_SECONDS * 1_000_000_000
_MAX_RESOURCE_JSON_BYTES = 64 * 1024


def _valid_resources(resources: typing.Mapping[int, str]) -> dict[int, str]:
    """The batch's resources that are JSON objects of a sane size.

    A dropped resource only costs the records that point at it their resource
    attributes; they are still stored.
    """
    valid: dict[int, str] = {}
    for resource_hash, attributes_json in resources.items():
        if len(attributes_json) > _MAX_RESOURCE_JSON_BYTES:
            continue
        try:
            parsed = json.loads(attributes_json)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            valid[resource_hash] = attributes_json
    return valid


def _build_error_notification(enriched_log) -> notifications.ErrorNotification:
    log = enriched_log.log_entry
    return notifications.ErrorNotification(
        project_id=enriched_log.project_id,
        level=log.level,
        log_type=log.log_type,
        message=log.message[:500] if log.message else "",
        error_type=log.error_type,
        timestamp=log.timestamp,
        error_fingerprint=enriched_log.error_fingerprint,
        attributes=log.attributes or {},
        sdk_version=log.sdk_version,
        platform=log.platform,
    )


def _compute_tags_hash(tags: dict) -> str:
    # Canonicalize (sorted keys, no whitespace) before hashing so the same tag
    # map always yields the same fixed-width key, regardless of insertion
    # order. blake2b with digest_size=8 gives a 16-char hex string, short
    # enough to embed in the primary key / partition locality without the
    # fragility of using raw tags JSONB in a composite PK (see migration 014).
    canonical = json.dumps(tags, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode(), digest_size=8).hexdigest()


class IngestionServicer(ingestion_pb2_grpc.IngestionServiceServicer):
    def __init__(self, redis_client=None):
        self.notification_publisher = None
        if redis_client and config.settings.NOTIFICATIONS_ENABLED:
            self.notification_publisher = notifications.NotificationPublisher(
                redis_client, enabled=config.settings.NOTIFICATIONS_ENABLED
            )

    async def IngestLog(
        self, request: ingestion_pb2.IngestLogRequest, context: grpc.aio.ServicerContext
    ) -> ingestion_pb2.IngestLogResponse:
        try:
            log_entry = _proto_to_log_entry(request.log, resources={})

            enriched_log = enricher.enrich_log_entry(log_entry, request.project_id)

            await queue_service.enqueue_log(enriched_log)

            if self.notification_publisher:
                log = enriched_log.log_entry
                if self.notification_publisher.should_notify(
                    log.level,
                    log.log_type,
                    config.settings.NOTIFICATIONS_PUBLISH_ERRORS,
                    config.settings.NOTIFICATIONS_PUBLISH_CRITICAL,
                ):
                    notification = _build_error_notification(enriched_log)
                    await self.notification_publisher.publish_error_notification(
                        enriched_log.project_id, notification
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
            resources = _valid_resources(request.resources)

            for idx, proto_log in enumerate(request.logs):
                try:
                    log_entry = _proto_to_log_entry(proto_log, resources)
                    enriched_log = enricher.enrich_log_entry(log_entry, request.project_id)
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
                await queue_service.enqueue_logs_batch(enriched_logs, resources)

                if self.notification_publisher:
                    await self.notification_publisher.publish_error_notifications(
                        request.project_id,
                        [
                            _build_error_notification(enriched_log)
                            for enriched_log in enriched_logs
                            if self.notification_publisher.should_notify(
                                enriched_log.log_entry.level,
                                enriched_log.log_entry.log_type,
                                config.settings.NOTIFICATIONS_PUBLISH_ERRORS,
                                config.settings.NOTIFICATIONS_PUBLISH_CRITICAL,
                            )
                        ],
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

    async def IngestSpansBatch(
        self,
        request: ingestion_pb2.IngestSpansBatchRequest,
        context: grpc.aio.ServicerContext,
    ) -> ingestion_pb2.IngestSpansBatchResponse:
        accepted = 0
        rejected = 0
        rows = []
        resources = _valid_resources(request.resources)

        for span in request.spans:
            trace_id = span.trace_id.lower()
            span_id = span.span_id.lower()
            parent_span_id = span.parent_span_id.lower() or None
            # Every id must fit its CHAR column: one oversized value fails the
            # COPY for every project's spans that share the worker's batch.
            if (
                not _HEX32_RE.match(trace_id)
                or not _HEX16_RE.match(span_id)
                or (parent_span_id is not None and not _HEX16_RE.match(parent_span_id))
            ):
                rejected += 1
                continue

            # Guard unix_nano parsing: a malformed/out-of-range timestamp from a
            # single bad span must only reject that span, not blow up the whole
            # batch (fromtimestamp raises ValueError/OverflowError/OSError on
            # out-of-range or nonsensical values).
            try:
                start_dt = datetime.datetime.fromtimestamp(
                    span.start_unix_nano / 1e9, tz=datetime.timezone.utc
                )
                duration_ns = span.end_unix_nano - span.start_unix_nano
            except (ValueError, OverflowError, OSError, TypeError) as e:
                rejected += 1
                logger.warning(f"Invalid span timestamp for project {request.project_id}: {e}")
                continue

            if (
                schemas.timestamp_window_error(start_dt) is not None
                or not 0 <= duration_ns <= _MAX_SPAN_DURATION_NS
            ):
                rejected += 1
                continue

            status_code = int(span.status)

            error_fingerprint = None
            if status_code == 2:
                raw = f"{request.project_id}:{span.service_name}:{span.name}"
                error_fingerprint = hashlib.sha256(raw.encode()).hexdigest()[:16]

            rows.append(
                {
                    "span_id": span_id,
                    "trace_id": trace_id,
                    "parent_span_id": parent_span_id,
                    "service_name": span.service_name[:255],
                    "name": span.name[:255],
                    "kind": int(span.kind),
                    "start_time": start_dt.isoformat(),
                    "duration_ns": duration_ns,
                    "status_code": status_code,
                    "status_message": span.status_message[:500],
                    "attributes": dict(span.attributes),
                    "events": [
                        {
                            "name": e.name,
                            "ts": e.ts_unix_nano,
                            "attrs": dict(e.attrs),
                        }
                        for e in span.events
                    ],
                    "error_fingerprint": error_fingerprint,
                    "resource_hash": _known_resource(span, resources),
                }
            )
            accepted += 1

        if rows:
            try:
                await queue_service.enqueue_spans_envelope(request.project_id, rows, resources)
            except queue_service.QueueFullError as e:
                logger.warning(f"Spans queue full for project {request.project_id}: {e}")
                await context.abort(
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    "Service temporarily unavailable - queue full",
                )
                return
            except Exception as e:
                logger.error(f"Failed to enqueue spans batch: {e}", exc_info=True)
                await context.abort(grpc.StatusCode.INTERNAL, "Failed to store spans")
                return

        return ingestion_pb2.IngestSpansBatchResponse(
            success=True, accepted=accepted, rejected=rejected
        )

    async def IngestMetricPointsBatch(
        self,
        request: ingestion_pb2.IngestMetricPointsBatchRequest,
        context: grpc.aio.ServicerContext,
    ) -> ingestion_pb2.IngestMetricPointsBatchResponse:
        accepted = 0
        rejected = 0
        rows = []
        resources = _valid_resources(request.resources)

        for point in request.points:
            name = point.name.strip()[:255]
            if not name:
                rejected += 1
                continue

            # Guard timestamp parsing: a malformed timestamp from a single bad
            # point must only reject that point, not blow up the whole batch.
            try:
                ts = datetime.datetime.fromisoformat(point.timestamp.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                rejected += 1
                logger.warning(
                    f"Invalid metric point timestamp for project {request.project_id}: "
                    f"{point.timestamp!r}"
                )
                continue
            if schemas.timestamp_window_error(ts) is not None:
                rejected += 1
                continue

            point_type = int(point.type)
            tags = dict(point.tags)

            rows.append(
                {
                    "name": name,
                    "type": point_type,
                    "ts": ts.isoformat(),
                    "value": point.value if point.HasField("value") else None,
                    "count": point.count if point.HasField("count") else None,
                    "sum": point.sum if point.HasField("sum") else None,
                    "bucket_counts": list(point.bucket_counts) or None,
                    "explicit_bounds": list(point.explicit_bounds) or None,
                    "tags": tags,
                    "tags_hash": _compute_tags_hash(tags),
                    "service_name": point.service_name[:255] if point.service_name else None,
                    "temporality": int(point.temporality) or None,
                    "resource_hash": _known_resource(point, resources),
                    **_distribution_fields(point),
                }
            )
            accepted += 1

        if rows:
            try:
                await queue_service.enqueue_metrics_envelope(request.project_id, rows, resources)
            except queue_service.QueueFullError as e:
                logger.warning(f"Metrics queue full for project {request.project_id}: {e}")
                await context.abort(
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    "Service temporarily unavailable - queue full",
                )
                return
            except Exception as e:
                logger.error(f"Failed to enqueue metric points batch: {e}", exc_info=True)
                await context.abort(grpc.StatusCode.INTERNAL, "Failed to store metric points")
                return

        return ingestion_pb2.IngestMetricPointsBatchResponse(
            success=True, accepted=accepted, rejected=rejected
        )


def _known_resource(item, resources: dict[int, str]) -> int | None:
    """The item's resource_hash, if the batch carried that resource."""
    if item.HasField("resource_hash") and item.resource_hash in resources:
        return item.resource_hash
    return None


def _valid_hex_id(item, field: str, pattern: re.Pattern) -> str | None:
    """A malformed id is dropped rather than failing the record: an oversized
    value would fail the COPY for every row sharing the worker's batch."""
    if not item.HasField(field):
        return None
    value = getattr(item, field).lower()
    return value if pattern.match(value) else None


def _distribution_fields(point: ingestion_pb2.MetricPoint) -> dict:
    """Exponential-histogram, summary and exemplar data of a metric point."""
    fields: dict = {"exp_histogram": None, "quantiles": None, "exemplars": None}
    if point.type == ingestion_pb2.EXPONENTIAL_HISTOGRAM:
        fields["exp_histogram"] = {
            "scale": point.scale,
            "zero_count": point.zero_count,
            "positive": {"offset": point.positive_offset, "counts": list(point.positive_counts)},
            "negative": {"offset": point.negative_offset, "counts": list(point.negative_counts)},
        }
    elif point.type == ingestion_pb2.SUMMARY:
        fields["quantiles"] = [
            [quantile, value] for quantile, value in zip(point.quantiles, point.quantile_values)
        ]
    exemplars = [
        {"v": e.value, "ts": e.timestamp, "trace_id": e.trace_id, "span_id": e.span_id}
        for e in point.exemplars
        if _HEX32_RE.match(e.trace_id)
    ]
    if exemplars:
        fields["exemplars"] = exemplars
    return fields


def _proto_to_log_entry(
    proto_log: ingestion_pb2.LogEntry, resources: dict[int, str]
) -> schemas.LogEntry:
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
        platform_version=proto_log.platform_version
        if proto_log.HasField("platform_version")
        else None,
        attributes=attributes,
        log_id=proto_log.log_id if proto_log.HasField("log_id") else None,
        client_channel=proto_log.client_channel if proto_log.HasField("client_channel") else None,
        client_country=proto_log.client_country if proto_log.HasField("client_country") else None,
        resource_hash=_known_resource(proto_log, resources),
        service_name=proto_log.service_name[:255] if proto_log.HasField("service_name") else None,
        trace_id=_valid_hex_id(proto_log, "trace_id", _HEX32_RE),
        span_id=_valid_hex_id(proto_log, "span_id", _HEX16_RE),
    )
