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
    log_type VARCHAR(30) NOT NULL,  -- console, logger, exception, database, endpoint, custom
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
CHECK (log_type IN ('console', 'logger', 'exception', 'network', 'database', 'endpoint', 'custom'));

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

-- Partial index for endpoint monitoring logs
-- Used for performance monitoring and API endpoint analytics
CREATE INDEX idx_logs_endpoint_monitoring ON logs (project_id, timestamp DESC, level)
WHERE log_type = 'endpoint';

-- ============================================
-- PARTITIONS (Monthly - Auto-created)
-- ============================================
-- Note: Partitions are auto-created by ingestion service on startup
-- Old partitions should be dropped based on retention_days from projects table

CREATE TABLE logs_2025_01 PARTITION OF logs
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE logs_2025_02 PARTITION OF logs
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');

CREATE TABLE logs_2025_03 PARTITION OF logs
    FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');

CREATE TABLE logs_2025_04 PARTITION OF logs
    FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');

CREATE TABLE logs_2025_05 PARTITION OF logs
    FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');

CREATE TABLE logs_2025_06 PARTITION OF logs
    FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');

CREATE TABLE logs_2025_07 PARTITION OF logs
    FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');

CREATE TABLE logs_2025_08 PARTITION OF logs
    FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');

CREATE TABLE logs_2025_09 PARTITION OF logs
    FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');

CREATE TABLE logs_2025_10 PARTITION OF logs
    FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');

CREATE TABLE logs_2025_11 PARTITION OF logs
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');

CREATE TABLE logs_2025_12 PARTITION OF logs
    FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');

CREATE TABLE logs_2026_01 PARTITION OF logs
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

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
-- 3. AGGREGATED METRICS (Hourly Analytics)
-- ============================================
-- Pre-aggregated metrics for exceptions and endpoint monitoring
-- Enables fast dashboard queries without scanning full logs table

CREATE TABLE aggregated_metrics (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL,

    -- Time bucket
    date VARCHAR(8) NOT NULL,  -- YYYYMMDD format
    hour SMALLINT NOT NULL,  -- 0-23

    -- Metric type
    metric_type VARCHAR(20) NOT NULL,  -- exception, endpoint, log_volume

    -- Endpoint identification (NULL for exceptions and log_volume)
    endpoint_method VARCHAR(10),  -- GET, POST, PUT, DELETE, etc.
    endpoint_path VARCHAR(500),  -- /api/users/{id}

    -- Log volume identification (NULL for endpoint and exception)
    log_level VARCHAR(20),  -- debug, info, warning, error, critical
    log_type VARCHAR(30),  -- console, logger, exception, network, database, endpoint, custom

    -- Counts
    log_count INTEGER DEFAULT 0 NOT NULL,
    error_count INTEGER DEFAULT 0 NOT NULL,  -- 4xx+5xx for endpoints, all for exceptions

    -- Performance metrics (endpoint only)
    avg_duration_ms FLOAT,
    min_duration_ms INTEGER,
    max_duration_ms INTEGER,
    p95_duration_ms INTEGER,
    p99_duration_ms INTEGER,

    -- Additional metadata
    extra_metadata JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Composite index for fast lookups by project, date, and type
CREATE INDEX idx_aggregated_metrics_lookup
ON aggregated_metrics(project_id, date, metric_type);

-- Partial index for endpoint queries
CREATE INDEX idx_aggregated_metrics_endpoint
ON aggregated_metrics(project_id, date, endpoint_path)
WHERE metric_type = 'endpoint';

-- Unique constraint for UPSERT operations
CREATE UNIQUE INDEX uq_aggregated_metrics
ON aggregated_metrics(
    project_id,
    date,
    hour,
    metric_type,
    COALESCE(endpoint_method, ''),
    COALESCE(endpoint_path, ''),
    COALESCE(log_level, ''),
    COALESCE(log_type, '')
);

-- Constraints
ALTER TABLE aggregated_metrics ADD CONSTRAINT check_metric_type
CHECK (metric_type IN ('exception', 'endpoint', 'log_volume'));

ALTER TABLE aggregated_metrics ADD CONSTRAINT check_hour_range
CHECK (hour >= 0 AND hour <= 23);

ALTER TABLE aggregated_metrics ADD CONSTRAINT check_log_level
CHECK (log_level IS NULL OR log_level IN ('debug', 'info', 'warning', 'error', 'critical'));

ALTER TABLE aggregated_metrics ADD CONSTRAINT check_log_type
CHECK (log_type IS NULL OR log_type IN ('console', 'logger', 'exception', 'network', 'database', 'endpoint', 'custom'));

-- ============================================
-- 4. INGESTION METRICS (Performance Monitoring)
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

CREATE TABLE ingestion_metrics_2025_03 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');

CREATE TABLE ingestion_metrics_2025_04 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');

CREATE TABLE ingestion_metrics_2025_05 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');

CREATE TABLE ingestion_metrics_2025_06 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');

CREATE TABLE ingestion_metrics_2025_07 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');

CREATE TABLE ingestion_metrics_2025_08 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');

CREATE TABLE ingestion_metrics_2025_09 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');

CREATE TABLE ingestion_metrics_2025_10 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');

CREATE TABLE ingestion_metrics_2025_11 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');

CREATE TABLE ingestion_metrics_2025_12 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');

CREATE TABLE ingestion_metrics_2026_01 PARTITION OF ingestion_metrics
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
