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

-- Expression index for endpoint duration extraction (avoids repeated cast in analytics queries)
CREATE INDEX idx_logs_endpoint_duration
ON logs (
    project_id,
    timestamp DESC,
    ((attributes->'endpoint'->>'duration_ms')::float)
)
WHERE log_type = 'endpoint'
  AND attributes->'endpoint'->>'duration_ms' IS NOT NULL;

-- Covering index for error list panel queries (index-only scan for maximum performance)
-- Contains all columns needed for error list display in dashboard panels
-- Matches SSE notification format for consistent error representation
CREATE INDEX idx_logs_error_list_covering ON logs (project_id, timestamp DESC, level, log_type, error_type, message, error_fingerprint, sdk_version, platform)
WHERE level IN ('error', 'critical');

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
-- 4. BOTTLENECK METRICS (Route Performance Tracking)
-- ============================================
-- Per-route performance metrics grouped by project, date, hour, and route
-- Enables users to identify slow endpoints and performance bottlenecks

CREATE TABLE bottleneck_metrics (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL,

    -- Time bucket
    date VARCHAR(8) NOT NULL,  -- YYYYMMDD format
    hour SMALLINT NOT NULL,  -- 0-23

    -- Route identification
    route VARCHAR(500) NOT NULL,  -- Endpoint path (e.g., /api/users/{id})

    -- Request counts
    log_count INTEGER DEFAULT 0 NOT NULL,

    -- Performance metrics (duration in milliseconds)
    min_duration_ms INTEGER DEFAULT 0,
    max_duration_ms INTEGER DEFAULT 0,
    avg_duration_ms FLOAT DEFAULT 0,
    median_duration_ms INTEGER DEFAULT 0,  -- p50

    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Composite index for fast lookups by project, date, and hour
CREATE INDEX idx_bottleneck_metrics_lookup
ON bottleneck_metrics(project_id, date, hour);

-- Index for route-specific queries
CREATE INDEX idx_bottleneck_metrics_route
ON bottleneck_metrics(project_id, date, route);

-- Unique constraint for UPSERT operations
CREATE UNIQUE INDEX uq_bottleneck_metrics
ON bottleneck_metrics(project_id, date, hour, route);

-- Constraints
ALTER TABLE bottleneck_metrics ADD CONSTRAINT check_bottleneck_hour_range
CHECK (hour >= 0 AND hour <= 23);

-- ============================================
-- 5. ROLLUP TABLES (APScheduler-populated aggregations)
-- ============================================

CREATE TABLE log_volume_5m (
    project_id  BIGINT NOT NULL,
    level       VARCHAR(20) NOT NULL,
    bucket      TIMESTAMPTZ NOT NULL,
    count       BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, level, bucket)
);
CREATE INDEX idx_lv5m_project_bucket ON log_volume_5m (project_id, bucket DESC);

CREATE TABLE log_volume_1h (
    project_id  BIGINT NOT NULL,
    level       VARCHAR(20) NOT NULL,
    bucket      TIMESTAMPTZ NOT NULL,
    count       BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, level, bucket)
);
CREATE INDEX idx_lv1h_project_bucket ON log_volume_1h (project_id, bucket DESC);

CREATE TABLE log_volume_1d (
    project_id  BIGINT NOT NULL,
    level       VARCHAR(20) NOT NULL,
    bucket      DATE NOT NULL,
    count       BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, level, bucket)
);
CREATE INDEX idx_lv1d_project_bucket ON log_volume_1d (project_id, bucket DESC);

CREATE TABLE error_rate_5m (
    project_id  BIGINT NOT NULL,
    bucket      TIMESTAMPTZ NOT NULL,
    errors      BIGINT NOT NULL DEFAULT 0,
    total       BIGINT NOT NULL DEFAULT 0,
    ratio       DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, bucket)
);
CREATE INDEX idx_er5m_project_bucket ON error_rate_5m (project_id, bucket DESC);

CREATE TABLE endpoint_latency_1h (
    project_id  BIGINT NOT NULL,
    route       TEXT NOT NULL,
    bucket      TIMESTAMPTZ NOT NULL,
    count       BIGINT NOT NULL DEFAULT 0,
    p50_ms      DOUBLE PRECISION,
    p95_ms      DOUBLE PRECISION,
    p99_ms      DOUBLE PRECISION,
    PRIMARY KEY (project_id, route, bucket)
);
CREATE INDEX idx_el1h_project_bucket ON endpoint_latency_1h (project_id, bucket DESC);

CREATE TABLE rollup_job_state (
    job_name    TEXT NOT NULL PRIMARY KEY,
    last_bucket TIMESTAMPTZ NOT NULL
);

-- ============================================
-- 6. SPANS TABLE (Distributed Tracing)
-- Daily range-partitioned
-- ============================================

CREATE TABLE spans (
    span_id           CHAR(16) NOT NULL,
    trace_id          CHAR(32) NOT NULL,
    parent_span_id    CHAR(16),
    project_id        BIGINT NOT NULL,
    service_name      TEXT NOT NULL,
    name              TEXT NOT NULL,
    kind              SMALLINT NOT NULL DEFAULT 0,
    start_time        TIMESTAMPTZ NOT NULL,
    duration_ns       BIGINT NOT NULL DEFAULT 0,
    status_code       SMALLINT NOT NULL DEFAULT 0,
    status_message    TEXT,
    attributes        JSONB NOT NULL DEFAULT '{}'::jsonb,
    events            JSONB,
    error_fingerprint CHAR(64),
    PRIMARY KEY (span_id, start_time)
) PARTITION BY RANGE (start_time);

CREATE INDEX brin_spans_project_time ON spans USING BRIN (project_id, start_time);
CREATE INDEX idx_spans_trace ON spans (trace_id);
CREATE INDEX idx_spans_op ON spans (project_id, service_name, name, start_time DESC);
CREATE INDEX idx_spans_errors ON spans (project_id, start_time DESC) WHERE status_code = 2;

CREATE TABLE span_latency_1h (
    project_id   BIGINT NOT NULL,
    service_name TEXT NOT NULL,
    name         TEXT NOT NULL,
    bucket       TIMESTAMPTZ NOT NULL,
    calls        BIGINT NOT NULL DEFAULT 0,
    p50_ns       BIGINT,
    p95_ns       BIGINT,
    p99_ns       BIGINT,
    errors       BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, service_name, name, bucket)
);
CREATE INDEX idx_sl1h_project_bucket ON span_latency_1h (project_id, bucket DESC);

-- Add trace correlation columns to logs
ALTER TABLE logs
    ADD COLUMN trace_id CHAR(32),
    ADD COLUMN span_id  CHAR(16);
CREATE INDEX idx_log_trace ON logs (trace_id) WHERE trace_id IS NOT NULL;

-- ============================================
-- 7. CUSTOM METRICS TABLE
-- Daily range-partitioned
-- ============================================

CREATE TABLE custom_metrics (
    project_id  BIGINT NOT NULL,
    name        TEXT NOT NULL,
    tags        JSONB NOT NULL DEFAULT '{}'::jsonb,
    ts          TIMESTAMPTZ NOT NULL,
    type        SMALLINT NOT NULL,
    count       BIGINT NOT NULL DEFAULT 0,
    sum         DOUBLE PRECISION NOT NULL DEFAULT 0,
    min_v       DOUBLE PRECISION,
    max_v       DOUBLE PRECISION,
    buckets     JSONB,
    PRIMARY KEY (project_id, name, tags, ts)
) PARTITION BY RANGE (ts);

CREATE INDEX idx_cm_lookup ON custom_metrics (project_id, name, ts DESC);
CREATE INDEX idx_cm_tags ON custom_metrics USING GIN (tags);

CREATE TABLE metric_series_count (
    project_id   BIGINT NOT NULL PRIMARY KEY,
    series_count BIGINT NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE custom_metrics_5m (
    project_id  BIGINT NOT NULL,
    name        TEXT NOT NULL,
    tags        JSONB NOT NULL DEFAULT '{}'::jsonb,
    bucket      TIMESTAMPTZ NOT NULL,
    type        SMALLINT NOT NULL,
    count       BIGINT NOT NULL DEFAULT 0,
    sum         DOUBLE PRECISION NOT NULL DEFAULT 0,
    min_v       DOUBLE PRECISION,
    max_v       DOUBLE PRECISION,
    PRIMARY KEY (project_id, name, tags, bucket)
);
CREATE INDEX idx_cm5m_lookup ON custom_metrics_5m (project_id, name, bucket DESC);

CREATE TABLE custom_metrics_1h (
    project_id  BIGINT NOT NULL,
    name        TEXT NOT NULL,
    tags        JSONB NOT NULL DEFAULT '{}'::jsonb,
    bucket      TIMESTAMPTZ NOT NULL,
    type        SMALLINT NOT NULL,
    count       BIGINT NOT NULL DEFAULT 0,
    sum         DOUBLE PRECISION NOT NULL DEFAULT 0,
    min_v       DOUBLE PRECISION,
    max_v       DOUBLE PRECISION,
    PRIMARY KEY (project_id, name, tags, bucket)
);
CREATE INDEX idx_cm1h_lookup ON custom_metrics_1h (project_id, name, bucket DESC);

CREATE TABLE custom_metrics_1d (
    project_id  BIGINT NOT NULL,
    name        TEXT NOT NULL,
    tags        JSONB NOT NULL DEFAULT '{}'::jsonb,
    bucket      DATE NOT NULL,
    type        SMALLINT NOT NULL,
    count       BIGINT NOT NULL DEFAULT 0,
    sum         DOUBLE PRECISION NOT NULL DEFAULT 0,
    min_v       DOUBLE PRECISION,
    max_v       DOUBLE PRECISION,
    PRIMARY KEY (project_id, name, tags, bucket)
);
CREATE INDEX idx_cm1d_lookup ON custom_metrics_1d (project_id, name, bucket DESC);

