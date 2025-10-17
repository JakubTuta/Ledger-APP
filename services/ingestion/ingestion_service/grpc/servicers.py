import datetime
import json
import logging

import grpc

import ingestion_service.proto.ingestion_pb2 as ingestion_pb2
import ingestion_service.proto.ingestion_pb2_grpc as ingestion_pb2_grpc
import ingestion_service.schemas as schemas
import ingestion_service.services.enricher as enricher
import ingestion_service.services.queue_service as queue_service

logger = logging.getLogger(__name__)


class IngestionServicer(ingestion_pb2_grpc.IngestionServiceServicer):
    async def IngestLog(
        self, request: ingestion_pb2.IngestLogRequest, context: grpc.aio.ServicerContext
    ) -> ingestion_pb2.IngestLogResponse:
        try:
            log_entry = _proto_to_log_entry(request.log)

            enriched_log = enricher.enrich_log_entry(log_entry, request.project_id)

            await queue_service.enqueue_log(enriched_log)

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
