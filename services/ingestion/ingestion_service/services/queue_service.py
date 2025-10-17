import msgpack

import ingestion_service.config as config
import ingestion_service.schemas as schemas
import ingestion_service.services.redis_client as redis_client


class QueueFullError(Exception):
    pass


async def enqueue_log(enriched_log: schemas.EnrichedLogEntry) -> None:
    redis = redis_client.get_redis_client()
    queue_key = f"queue:logs:{enriched_log.project_id}"

    current_depth = await redis.llen(queue_key)
    if current_depth >= config.settings.QUEUE_MAX_DEPTH:
        raise QueueFullError(
            f"Queue for project {enriched_log.project_id} is full (depth: {current_depth})"
        )

    payload = {
        "project_id": enriched_log.project_id,
        "timestamp": enriched_log.log_entry.timestamp.isoformat(),
        "ingested_at": enriched_log.ingested_at.isoformat(),
        "level": enriched_log.log_entry.level,
        "log_type": enriched_log.log_entry.log_type,
        "importance": enriched_log.log_entry.importance,
        "environment": enriched_log.log_entry.environment,
        "release": enriched_log.log_entry.release,
        "message": enriched_log.log_entry.message,
        "error_type": enriched_log.log_entry.error_type,
        "error_message": enriched_log.log_entry.error_message,
        "stack_trace": enriched_log.log_entry.stack_trace,
        "attributes": enriched_log.log_entry.attributes,
        "sdk_version": enriched_log.log_entry.sdk_version,
        "platform": enriched_log.log_entry.platform,
        "platform_version": enriched_log.log_entry.platform_version,
        "error_fingerprint": enriched_log.error_fingerprint,
    }

    packed_payload = msgpack.packb(payload, use_bin_type=True)

    await redis.lpush(queue_key, packed_payload)


async def enqueue_logs_batch(enriched_logs: list[schemas.EnrichedLogEntry]) -> None:
    if not enriched_logs:
        return

    redis = redis_client.get_redis_client()

    projects_map: dict[int, list[schemas.EnrichedLogEntry]] = {}
    for log in enriched_logs:
        if log.project_id not in projects_map:
            projects_map[log.project_id] = []
        projects_map[log.project_id].append(log)

    pipe = redis.pipeline()

    for project_id, logs in projects_map.items():
        queue_key = f"queue:logs:{project_id}"

        current_depth = await redis.llen(queue_key)
        if current_depth >= config.settings.QUEUE_MAX_DEPTH:
            raise QueueFullError(
                f"Queue for project {project_id} is full (depth: {current_depth})"
            )

        for log in logs:
            payload = {
                "project_id": log.project_id,
                "timestamp": log.log_entry.timestamp.isoformat(),
                "ingested_at": log.ingested_at.isoformat(),
                "level": log.log_entry.level,
                "log_type": log.log_entry.log_type,
                "importance": log.log_entry.importance,
                "environment": log.log_entry.environment,
                "release": log.log_entry.release,
                "message": log.log_entry.message,
                "error_type": log.log_entry.error_type,
                "error_message": log.log_entry.error_message,
                "stack_trace": log.log_entry.stack_trace,
                "attributes": log.log_entry.attributes,
                "sdk_version": log.log_entry.sdk_version,
                "platform": log.log_entry.platform,
                "platform_version": log.log_entry.platform_version,
                "error_fingerprint": log.error_fingerprint,
            }

            packed_payload = msgpack.packb(payload, use_bin_type=True)
            pipe.lpush(queue_key, packed_payload)

    await pipe.execute()


async def get_queue_depth(project_id: int) -> int:
    redis = redis_client.get_redis_client()
    queue_key = f"queue:logs:{project_id}"
    return await redis.llen(queue_key)


async def dequeue_logs_batch(
    project_id: int, batch_size: int = None
) -> list[dict]:
    if batch_size is None:
        batch_size = config.settings.QUEUE_BATCH_SIZE

    redis = redis_client.get_redis_client()
    queue_key = f"queue:logs:{project_id}"

    pipe = redis.pipeline()
    for _ in range(batch_size):
        pipe.rpop(queue_key)

    results = await pipe.execute()

    logs = []
    for result in results:
        if result is None:
            break

        try:
            payload = msgpack.unpackb(result, raw=False)
            logs.append(payload)
        except Exception as e:
            continue

    return logs
