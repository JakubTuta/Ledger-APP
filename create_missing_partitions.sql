-- ============================================
-- Create Missing Partitions for 2025
-- ============================================
-- This script creates missing monthly partitions for the logs and ingestion_metrics tables
-- Run this on your production database to fix the "no partition found" error

-- Logs table partitions (April - December 2025 + January 2026)
CREATE TABLE IF NOT EXISTS logs_2025_04 PARTITION OF logs
    FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');

CREATE TABLE IF NOT EXISTS logs_2025_05 PARTITION OF logs
    FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');

CREATE TABLE IF NOT EXISTS logs_2025_06 PARTITION OF logs
    FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');

CREATE TABLE IF NOT EXISTS logs_2025_07 PARTITION OF logs
    FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');

CREATE TABLE IF NOT EXISTS logs_2025_08 PARTITION OF logs
    FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');

CREATE TABLE IF NOT EXISTS logs_2025_09 PARTITION OF logs
    FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');

CREATE TABLE IF NOT EXISTS logs_2025_10 PARTITION OF logs
    FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');

CREATE TABLE IF NOT EXISTS logs_2025_11 PARTITION OF logs
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');

CREATE TABLE IF NOT EXISTS logs_2025_12 PARTITION OF logs
    FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');

CREATE TABLE IF NOT EXISTS logs_2026_01 PARTITION OF logs
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

-- Ingestion metrics table partitions (April - December 2025 + January 2026)
CREATE TABLE IF NOT EXISTS ingestion_metrics_2025_03 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');

CREATE TABLE IF NOT EXISTS ingestion_metrics_2025_04 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');

CREATE TABLE IF NOT EXISTS ingestion_metrics_2025_05 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');

CREATE TABLE IF NOT EXISTS ingestion_metrics_2025_06 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');

CREATE TABLE IF NOT EXISTS ingestion_metrics_2025_07 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');

CREATE TABLE IF NOT EXISTS ingestion_metrics_2025_08 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');

CREATE TABLE IF NOT EXISTS ingestion_metrics_2025_09 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');

CREATE TABLE IF NOT EXISTS ingestion_metrics_2025_10 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');

CREATE TABLE IF NOT EXISTS ingestion_metrics_2025_11 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');

CREATE TABLE IF NOT EXISTS ingestion_metrics_2025_12 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');

CREATE TABLE IF NOT EXISTS ingestion_metrics_2026_01 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

-- Verify partitions were created
SELECT
    schemaname,
    tablename,
    CASE
        WHEN tablename LIKE '%_____\___' THEN 'Partition'
        ELSE 'Parent Table'
    END as type
FROM pg_tables
WHERE tablename LIKE 'logs%' OR tablename LIKE 'ingestion_metrics%'
ORDER BY tablename;
