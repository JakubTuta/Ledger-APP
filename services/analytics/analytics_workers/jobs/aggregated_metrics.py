import datetime

import analytics_workers.database as database
import analytics_workers.utils.logging as logging
import sqlalchemy as sa

logger = logging.get_logger("jobs.aggregated_metrics")


async def aggregate_hourly_metrics() -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    current_hour_start = now.replace(minute=0, second=0, microsecond=0)
    previous_hour_start = current_hour_start - datetime.timedelta(hours=1)
    previous_hour_end = current_hour_start

    date_str = previous_hour_start.strftime("%Y%m%d")
    hour = previous_hour_start.hour

    logger.info(
        f"Starting hourly aggregation for {date_str} hour {hour} "
        f"({previous_hour_start} to {previous_hour_end})"
    )

    try:
        await _aggregate_endpoint_metrics(
            date_str, hour, previous_hour_start, previous_hour_end
        )

        await _aggregate_exception_metrics(
            date_str, hour, previous_hour_start, previous_hour_end
        )

        await _aggregate_log_volume_metrics(
            date_str, hour, previous_hour_start, previous_hour_end
        )

    except Exception as e:
        logger.error(f"Hourly metrics aggregation failed: {e}", exc_info=True)
        raise


async def _aggregate_endpoint_metrics(
    date_str: str,
    hour: int,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
) -> None:
    logger.info(f"Aggregating endpoint metrics for {date_str} hour {hour}")
    async with database.get_logs_session() as session:
        query = sa.text(
            """
            INSERT INTO aggregated_metrics (
                project_id,
                date,
                hour,
                metric_type,
                endpoint_method,
                endpoint_path,
                log_level,
                log_type,
                log_count,
                error_count,
                avg_duration_ms,
                min_duration_ms,
                max_duration_ms,
                p95_duration_ms,
                p99_duration_ms
            )
            SELECT
                project_id,
                :date_str AS date,
                :hour AS hour,
                'endpoint' AS metric_type,
                (attributes->'endpoint'->>'method')::VARCHAR AS endpoint_method,
                (attributes->'endpoint'->>'path')::VARCHAR AS endpoint_path,
                NULL AS log_level,
                NULL AS log_type,
                COUNT(*) AS log_count,
                COUNT(*) FILTER (
                    WHERE (attributes->'endpoint'->>'status_code')::INTEGER >= 400
                ) AS error_count,
                AVG((attributes->'endpoint'->>'duration_ms')::FLOAT) AS avg_duration_ms,
                ROUND(MIN((attributes->'endpoint'->>'duration_ms')::FLOAT))::INTEGER AS min_duration_ms,
                ROUND(MAX((attributes->'endpoint'->>'duration_ms')::FLOAT))::INTEGER AS max_duration_ms,
                ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (
                    ORDER BY (attributes->'endpoint'->>'duration_ms')::FLOAT
                ))::INTEGER AS p95_duration_ms,
                ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (
                    ORDER BY (attributes->'endpoint'->>'duration_ms')::FLOAT
                ))::INTEGER AS p99_duration_ms
            FROM logs
            WHERE
                log_type = 'endpoint'
                AND timestamp >= :start_time
                AND timestamp < :end_time
                AND attributes->'endpoint'->>'method' IS NOT NULL
                AND attributes->'endpoint'->>'path' IS NOT NULL
            GROUP BY
                project_id,
                attributes->'endpoint'->>'method',
                attributes->'endpoint'->>'path'
            ON CONFLICT (
                project_id,
                date,
                hour,
                metric_type,
                COALESCE(endpoint_method, ''),
                COALESCE(endpoint_path, ''),
                COALESCE(log_level, ''),
                COALESCE(log_type, '')
            )
            DO UPDATE SET
                log_count = EXCLUDED.log_count,
                error_count = EXCLUDED.error_count,
                avg_duration_ms = EXCLUDED.avg_duration_ms,
                min_duration_ms = EXCLUDED.min_duration_ms,
                max_duration_ms = EXCLUDED.max_duration_ms,
                p95_duration_ms = EXCLUDED.p95_duration_ms,
                p99_duration_ms = EXCLUDED.p99_duration_ms,
                updated_at = NOW()
        """
        )

        result = await session.execute(
            query,
            {
                "date_str": date_str,
                "hour": hour,
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        await session.commit()

        logger.info(
            f"Aggregated endpoint metrics for {date_str} hour {hour}: "
            f"{result.rowcount} rows affected"
        )


async def _aggregate_exception_metrics(
    date_str: str,
    hour: int,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
) -> None:
    logger.info(f"Aggregating exception metrics for {date_str} hour {hour}")
    async with database.get_logs_session() as session:
        query = sa.text(
            """
            INSERT INTO aggregated_metrics (
                project_id,
                date,
                hour,
                metric_type,
                endpoint_method,
                endpoint_path,
                log_level,
                log_type,
                log_count,
                error_count
            )
            SELECT
                project_id,
                :date_str AS date,
                :hour AS hour,
                'exception' AS metric_type,
                NULL AS endpoint_method,
                NULL AS endpoint_path,
                NULL AS log_level,
                NULL AS log_type,
                COUNT(*) AS log_count,
                COUNT(*) AS error_count
            FROM logs
            WHERE
                log_type = 'exception'
                AND timestamp >= :start_time
                AND timestamp < :end_time
            GROUP BY
                project_id
            ON CONFLICT (
                project_id,
                date,
                hour,
                metric_type,
                COALESCE(endpoint_method, ''),
                COALESCE(endpoint_path, ''),
                COALESCE(log_level, ''),
                COALESCE(log_type, '')
            )
            DO UPDATE SET
                log_count = EXCLUDED.log_count,
                error_count = EXCLUDED.error_count,
                updated_at = NOW()
        """
        )

        result = await session.execute(
            query,
            {
                "date_str": date_str,
                "hour": hour,
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        await session.commit()

        logger.info(
            f"Aggregated exception metrics for {date_str} hour {hour}: "
            f"{result.rowcount} rows affected"
        )


async def _aggregate_log_volume_metrics(
    date_str: str,
    hour: int,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
) -> None:
    logger.info(f"Aggregating log volume metrics for {date_str} hour {hour}")
    async with database.get_logs_session() as session:
        query = sa.text(
            """
            INSERT INTO aggregated_metrics (
                project_id,
                date,
                hour,
                metric_type,
                endpoint_method,
                endpoint_path,
                log_level,
                log_type,
                log_count,
                error_count
            )
            SELECT
                project_id,
                :date_str AS date,
                :hour AS hour,
                'log_volume' AS metric_type,
                NULL AS endpoint_method,
                NULL AS endpoint_path,
                level AS log_level,
                log_type,
                COUNT(*) AS log_count,
                COUNT(*) FILTER (WHERE level IN ('error', 'critical')) AS error_count
            FROM logs
            WHERE
                timestamp >= :start_time
                AND timestamp < :end_time
            GROUP BY
                project_id,
                level,
                log_type
            ON CONFLICT (
                project_id,
                date,
                hour,
                metric_type,
                COALESCE(endpoint_method, ''),
                COALESCE(endpoint_path, ''),
                COALESCE(log_level, ''),
                COALESCE(log_type, '')
            )
            DO UPDATE SET
                log_count = EXCLUDED.log_count,
                error_count = EXCLUDED.error_count,
                updated_at = NOW()
        """
        )

        result = await session.execute(
            query,
            {
                "date_str": date_str,
                "hour": hour,
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        await session.commit()

        logger.info(
            f"Aggregated log volume metrics for {date_str} hour {hour}: "
            f"{result.rowcount} rows affected"
        )
