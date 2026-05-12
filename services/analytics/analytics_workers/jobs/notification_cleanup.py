import time

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.notification_cleanup")


async def cleanup_expired_notifications() -> None:
    start = time.perf_counter()

    try:
        async with database.get_auth_session() as session:
            result = await session.execute(
                sa.text(
                    "DELETE FROM notifications WHERE expires_at <= NOW()"
                )
            )
            await session.commit()
            deleted = result.rowcount

        elapsed = time.perf_counter() - start
        logger.info(f"Notification cleanup done in {elapsed:.2f}s, deleted {deleted} rows")

    except Exception as e:
        logger.error(f"Notification cleanup failed: {e}", exc_info=True)
        raise
