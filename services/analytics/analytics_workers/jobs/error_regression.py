import datetime
import json
import time

import analytics_workers.database as database
import analytics_workers.redis_client as redis_client
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.error_regression")

_SELECT_REGRESSED = sa.text(
    """
    SELECT id, project_id, fingerprint, error_type, error_message,
           occurrence_count, last_seen, resolved_at, resolved_in_release
    FROM error_groups
    WHERE status = 'resolved'
      AND resolved_at IS NOT NULL
      AND last_seen > resolved_at
    """
)

_REOPEN_REGRESSED = sa.text(
    """
    UPDATE error_groups
    SET status = 'unresolved', resolved_at = NULL, updated_at = NOW()
    WHERE id IN :ids
      AND status = 'resolved'
      AND resolved_at IS NOT NULL
      AND last_seen > resolved_at
    """
).bindparams(sa.bindparam("ids", expanding=True))


async def detect_error_regressions() -> None:
    """
    Scan resolved error groups for regressions: a group is considered
    regressed when new occurrences (last_seen bumped by the ingestion
    worker's _upsert_error_groups_batch) arrive after it was marked
    resolved. Flips the group back to 'unresolved' and notifies project
    members via in-app notifications + the existing SSE error channel.
    """
    start = time.perf_counter()

    try:
        async with database.get_logs_session() as logs_session:
            result = await logs_session.execute(_SELECT_REGRESSED)
            regressed = result.fetchall()

            if not regressed:
                elapsed = time.perf_counter() - start
                logger.info(f"Error regression scan done in {elapsed:.2f}s, 0 regressions")
                return

            regressed_ids = [row.id for row in regressed]
            await logs_session.execute(_REOPEN_REGRESSED, {"ids": regressed_ids})
            await logs_session.commit()

        await _notify_regressions(regressed)

        elapsed = time.perf_counter() - start
        logger.info(
            f"Error regression scan done in {elapsed:.2f}s, "
            f"{len(regressed)} regressions detected and reopened"
        )

    except Exception as e:
        logger.error(f"Error regression detection failed: {e}", exc_info=True)
        raise


async def _notify_regressions(regressed: list) -> None:
    by_project: dict[int, list] = {}
    for row in regressed:
        by_project.setdefault(row.project_id, []).append(row)

    now = datetime.datetime.now(datetime.timezone.utc)
    redis = redis_client.get_redis()

    async with database.get_auth_session() as auth_session:
        for project_id, groups in by_project.items():
            members_result = await auth_session.execute(
                sa.text("SELECT account_id FROM project_members WHERE project_id = :pid"),
                {"pid": project_id},
            )
            member_ids = [row[0] for row in members_result.fetchall()]

            for group in groups:
                payload = {
                    "error_group_id": group.id,
                    "fingerprint": group.fingerprint,
                    "error_type": group.error_type,
                    "error_message": group.error_message,
                    "occurrence_count": group.occurrence_count,
                    "last_seen": group.last_seen.isoformat(),
                    "resolved_in_release": group.resolved_in_release,
                    "regressed_at": now.isoformat(),
                }

                for account_id in member_ids:
                    await auth_session.execute(
                        sa.text(
                            """
                            INSERT INTO notifications
                                (user_id, project_id, kind, severity, payload)
                            VALUES
                                (:user_id, :project_id, 'error', 'warning', CAST(:payload AS jsonb))
                            """
                        ),
                        {
                            "user_id": account_id,
                            "project_id": project_id,
                            "payload": json.dumps(payload),
                        },
                    )

                await _publish_regression(redis, project_id, group, now)

        await auth_session.commit()


async def _publish_regression(redis, project_id: int, group, now: datetime.datetime) -> None:
    release_note = (
        f" (previously resolved in {group.resolved_in_release})"
        if group.resolved_in_release
        else ""
    )
    notification = {
        "project_id": project_id,
        "level": "error",
        "log_type": "error_regression",
        "message": (
            f"Error regressed: {group.error_type}{release_note} — "
            f"{group.occurrence_count} total occurrences"
        ),
        "error_type": group.error_type,
        "error_fingerprint": group.fingerprint,
        "timestamp": now.isoformat(),
        "severity": "warning",
    }

    try:
        published = await redis.publish(
            f"notifications:errors:{project_id}", json.dumps(notification)
        )
        logger.info(
            f"Published error regression to {published} SSE subscribers "
            f"(project {project_id}, group {group.id})"
        )
    except Exception as e:
        logger.warning(f"Failed to publish error regression notification: {e}")
