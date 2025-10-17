-- ============================================
-- 1. LOGS TABLE (Partitioned by Month)
-- ============================================

CREATE TABLE logs (
    -- Primary identification
    id BIGSERIAL NOT NULL,
    project_id BIGINT NOT NULL,

    -- Temporal data (partition key)
    timestamp TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    -- Log classification
    level VARCHAR(20) NOT NULL,  -- debug, info, warning, error, critical
    log_type VARCHAR(30) NOT NULL,  -- console, logger, exception, network, database, custom
    importance VARCHAR(20) DEFAULT 'standard' NOT NULL,  -- critical, high, standard, low

    -- Source identification
    environment VARCHAR(20),  -- production, staging, dev
    release VARCHAR(100),  -- version/release tag

    -- Content fields
    message TEXT,  -- Log message or console output (max 10KB enforced by API)
    error_type VARCHAR(255),  -- Exception class name (e.g., "ValueError")
    error_message TEXT,  -- Error description (max 5KB enforced by API)
    stack_trace TEXT,  -- Full stack trace (max 50KB enforced by API)

    -- Context metadata (JSONB for flexibility)
    attributes JSONB,  -- Custom fields: user_id, request_id, tags, etc. (max 100KB enforced by API)

    -- SDK metadata
    sdk_version VARCHAR(20),
    platform VARCHAR(50),  -- python, node, java, etc.
    platform_version VARCHAR(50),

    -- Performance tracking
    processing_time_ms SMALLINT,  -- Time to process this log (worker latency)

    -- Error grouping (set by ingestion service)
    error_fingerprint CHAR(64),  -- SHA-256 hash for error grouping

    PRIMARY KEY (id, timestamp)  -- Composite key required for partitioning
) PARTITION BY RANGE (timestamp);

-- ============================================
-- CHECK CONSTRAINTS
-- ============================================

ALTER TABLE logs ADD CONSTRAINT check_log_level
CHECK (level IN ('debug', 'info', 'warning', 'error', 'critical'));

ALTER TABLE logs ADD CONSTRAINT check_log_type
CHECK (log_type IN ('console', 'logger', 'exception', 'network', 'database', 'custom'));

ALTER TABLE logs ADD CONSTRAINT check_importance
CHECK (importance IN ('critical', 'high', 'standard', 'low'));

-- ============================================
-- PERFORMANCE INDEXES
-- ============================================

-- BRIN index for timestamp (very small, perfect for time-series)
-- 1000x smaller than B-tree, still provides fast range scans
CREATE INDEX idx_logs_timestamp ON logs USING BRIN (timestamp);

-- Composite index for common queries (project + time range)
-- Most queries filter by project_id and time range
CREATE INDEX idx_logs_project_timestamp ON logs (project_id, timestamp DESC);

-- Partial index for error/critical logs (smaller, faster)
-- Only indexes error and critical level logs
CREATE INDEX idx_logs_project_level ON logs (project_id, level, timestamp DESC)
WHERE level IN ('error', 'critical');

-- GIN index for JSONB queries (searching custom attributes)
-- Enables fast queries on nested JSONB fields
CREATE INDEX idx_logs_attributes ON logs USING GIN (attributes);

-- Index for error grouping
-- Used by Query Service to show grouped errors
CREATE INDEX idx_logs_error_fingerprint ON logs (project_id, error_fingerprint, timestamp DESC)
WHERE error_fingerprint IS NOT NULL;

-- Covering index for dashboard queries (index-only scan)
-- Contains all columns needed for dashboard, never touches table (10x faster)
CREATE INDEX idx_logs_dashboard ON logs (project_id, timestamp DESC, level, message)
WHERE importance IN ('critical', 'high');

-- ============================================
-- PARTITIONS (Monthly - Auto-created)
-- ============================================
-- Note: Partitions should be auto-created by pg_cron or ingestion service
-- Old partitions should be dropped based on retention_days from projects table

CREATE TABLE logs_2025_01 PARTITION OF logs
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE logs_2025_02 PARTITION OF logs
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');

CREATE TABLE logs_2025_03 PARTITION OF logs
    FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');

-- Future partitions created automatically by service
-- Example script for auto-creation:
-- DO $$
-- BEGIN
--   EXECUTE format(
--     'CREATE TABLE IF NOT EXISTS logs_%s PARTITION OF logs FOR VALUES FROM (%L) TO (%L)',
--     to_char(date_trunc('month', NOW() + interval '1 month'), 'YYYY_MM'),
--     date_trunc('month', NOW() + interval '1 month'),
--     date_trunc('month', NOW() + interval '2 months')
--   );
-- END $$;

-- ============================================
-- 2. ERROR GROUPS (Aggregated Error Tracking)
-- ============================================
-- Enables Sentry-like error grouping UI

CREATE TABLE error_groups (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL,

    -- Error identification
    fingerprint CHAR(64) NOT NULL,  -- SHA-256 of error signature
    error_type VARCHAR(255) NOT NULL,
    error_message TEXT,

    -- Tracking
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    occurrence_count BIGINT DEFAULT 1,

    -- Status
    status VARCHAR(20) DEFAULT 'unresolved',  -- unresolved, resolved, ignored, muted
    assigned_to BIGINT,  -- User ID (future feature)

    -- Representative example (first occurrence)
    sample_log_id BIGINT,
    sample_stack_trace TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Unique constraint on fingerprint per project
CREATE UNIQUE INDEX idx_error_groups_fingerprint
ON error_groups(project_id, fingerprint);

-- Index for filtering by status
CREATE INDEX idx_error_groups_status
ON error_groups(project_id, status, last_seen DESC);

-- Index for filtering by error type
CREATE INDEX idx_error_groups_type
ON error_groups(project_id, error_type, last_seen DESC);

ALTER TABLE error_groups ADD CONSTRAINT check_error_status
CHECK (status IN ('unresolved', 'resolved', 'ignored', 'muted'));

-- ============================================
-- 3. INGESTION METRICS (Performance Monitoring)
-- ============================================
-- Tracks ingestion service performance over time

CREATE TABLE ingestion_metrics (
    id BIGSERIAL NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    -- Throughput
    logs_received BIGINT DEFAULT 0,
    logs_processed BIGINT DEFAULT 0,
    logs_failed BIGINT DEFAULT 0,

    -- Latency (percentiles in milliseconds)
    latency_p50 SMALLINT,
    latency_p95 SMALLINT,
    latency_p99 SMALLINT,

    -- Queue depth
    queue_size BIGINT,

    -- Resource usage
    worker_count SMALLINT,

    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Monthly partitions (same pattern as logs table)
CREATE TABLE ingestion_metrics_2025_01 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE ingestion_metrics_2025_02 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');

-- ============================================
-- EXAMPLE QUERIES
-- ============================================

-- Get recent errors for a project (uses idx_logs_project_level)
-- SELECT id, timestamp, error_type, error_message
-- FROM logs
-- WHERE project_id = 123
--   AND level = 'error'
--   AND timestamp > NOW() - INTERVAL '1 day'
-- ORDER BY timestamp DESC
-- LIMIT 100;

-- Find logs with specific user_id in attributes (uses idx_logs_attributes)
-- SELECT id, timestamp, message
-- FROM logs
-- WHERE project_id = 123
--   AND attributes @> '{"user": {"id": "usr_123"}}'
-- ORDER BY timestamp DESC;

-- Get error group summary (grouped by fingerprint)
-- SELECT
--   fingerprint,
--   error_type,
--   occurrence_count,
--   first_seen,
--   last_seen,
--   status
-- FROM error_groups
-- WHERE project_id = 123
--   AND status = 'unresolved'
-- ORDER BY last_seen DESC;

-- ============================================
-- NOTES ON PERFORMANCE
-- ============================================

-- 1. Partition Pruning:
--    Queries with timestamp filters only scan relevant partitions
--    Example: Last 7 days → scans 1 partition instead of all 12

-- 2. BRIN Indexes:
--    Perfect for time-series data with sequential inserts
--    1000x smaller than B-tree indexes
--    Trade-off: Slightly slower for point queries, but we don't do those

-- 3. Covering Indexes:
--    idx_logs_dashboard contains all columns for dashboard queries
--    PostgreSQL never needs to access the table (Heap Fetches: 0)
--    10x faster than regular index scans

-- 4. JSONB Indexes:
--    GIN indexes enable fast searches on nested JSONB fields
--    Supports operators: @>, ->, ->>, ?, ?|, ?&

-- 5. Bulk Inserts:
--    Use PostgreSQL COPY protocol for 50x faster inserts
--    Workers should batch 1K-10K logs per COPY operation
--    Example: 100 logs/sec (INSERT) → 5000 logs/sec (COPY)

-- 6. Error Fingerprinting:
--    SHA-256 hash of: error_type + first_3_stack_frames + platform
--    UPSERT pattern to increment occurrence_count
--    Enables Sentry-like error grouping without scanning all logs
