-- ============================================
-- 1. LOGS TABLE (Partitioned by Month)
-- ============================================

CREATE TABLE IF NOT EXISTS logs (
    id BIGSERIAL NOT NULL,
    project_id BIGINT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    level VARCHAR(20) NOT NULL,
    log_type VARCHAR(30) NOT NULL,
    importance VARCHAR(20) DEFAULT 'standard' NOT NULL,
    environment VARCHAR(20),
    release VARCHAR(100),
    message TEXT,
    error_type VARCHAR(255),
    error_message TEXT,
    stack_trace TEXT,
    attributes JSONB,
    method VARCHAR(8),
    path VARCHAR(2048),
    status_code SMALLINT,
    duration_ms INTEGER,
    sdk_version VARCHAR(20),
    platform VARCHAR(50),
    platform_version VARCHAR(50),
    processing_time_ms SMALLINT,
    error_fingerprint CHAR(64),
    trace_id CHAR(32),
    span_id CHAR(16),
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- ============================================
-- CHECK CONSTRAINTS
-- ============================================

DO $$ BEGIN
    ALTER TABLE logs ADD CONSTRAINT check_log_level
        CHECK (level IN ('debug', 'info', 'warning', 'error', 'critical'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE logs ADD CONSTRAINT check_log_type
        CHECK (log_type IN ('console', 'logger', 'exception', 'network', 'database', 'endpoint', 'custom'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE logs ADD CONSTRAINT check_importance
        CHECK (importance IN ('critical', 'high', 'standard', 'low'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- PERFORMANCE INDEXES
-- ============================================

CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs USING BRIN (timestamp);

CREATE INDEX IF NOT EXISTS idx_logs_project_timestamp ON logs (project_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_logs_project_level ON logs (project_id, level, timestamp DESC)
WHERE level IN ('error', 'critical');

CREATE INDEX IF NOT EXISTS idx_logs_attributes ON logs USING GIN (attributes);

CREATE INDEX IF NOT EXISTS idx_logs_error_fingerprint ON logs (project_id, error_fingerprint, timestamp DESC)
WHERE error_fingerprint IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_logs_dashboard ON logs (project_id, timestamp DESC, level, message)
WHERE importance IN ('critical', 'high');

CREATE INDEX IF NOT EXISTS idx_logs_endpoint_monitoring ON logs (project_id, timestamp DESC, level)
WHERE log_type = 'endpoint';

CREATE INDEX IF NOT EXISTS idx_logs_endpoint_duration
ON logs (
    project_id,
    timestamp DESC,
    ((attributes->'endpoint'->>'duration_ms')::float)
)
WHERE log_type = 'endpoint'
  AND attributes->'endpoint'->>'duration_ms' IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_logs_error_list_covering ON logs (project_id, timestamp DESC, level, log_type, error_type, message, error_fingerprint, sdk_version, platform)
WHERE level IN ('error', 'critical');

CREATE INDEX IF NOT EXISTS idx_log_trace ON logs (trace_id) WHERE trace_id IS NOT NULL;

-- ============================================
-- PARTITIONS (Monthly - Auto-created)
-- ============================================
-- Note: Partitions are auto-created by ingestion service on startup
-- Old partitions should be dropped based on retention_days from projects table

CREATE TABLE IF NOT EXISTS logs_2025_01 PARTITION OF logs FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
CREATE TABLE IF NOT EXISTS logs_2025_02 PARTITION OF logs FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
CREATE TABLE IF NOT EXISTS logs_2025_03 PARTITION OF logs FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');
CREATE TABLE IF NOT EXISTS logs_2025_04 PARTITION OF logs FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');
CREATE TABLE IF NOT EXISTS logs_2025_05 PARTITION OF logs FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');
CREATE TABLE IF NOT EXISTS logs_2025_06 PARTITION OF logs FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');
CREATE TABLE IF NOT EXISTS logs_2025_07 PARTITION OF logs FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');
CREATE TABLE IF NOT EXISTS logs_2025_08 PARTITION OF logs FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');
CREATE TABLE IF NOT EXISTS logs_2025_09 PARTITION OF logs FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');
CREATE TABLE IF NOT EXISTS logs_2025_10 PARTITION OF logs FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');
CREATE TABLE IF NOT EXISTS logs_2025_11 PARTITION OF logs FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');
CREATE TABLE IF NOT EXISTS logs_2025_12 PARTITION OF logs FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');
CREATE TABLE IF NOT EXISTS logs_2026_01 PARTITION OF logs FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

-- ============================================
-- 2. ERROR GROUPS (Aggregated Error Tracking)
-- ============================================

CREATE TABLE IF NOT EXISTS error_groups (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL,
    fingerprint CHAR(64) NOT NULL,
    error_type VARCHAR(255) NOT NULL,
    error_message TEXT,
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    occurrence_count BIGINT DEFAULT 1,
    status VARCHAR(20) DEFAULT 'unresolved',
    assigned_to BIGINT,
    sample_log_id BIGINT,
    sample_stack_trace TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_error_groups_fingerprint ON error_groups (project_id, fingerprint);
CREATE INDEX IF NOT EXISTS idx_error_groups_status ON error_groups (project_id, status, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_error_groups_type ON error_groups (project_id, error_type, last_seen DESC);

DO $$ BEGIN
    ALTER TABLE error_groups ADD CONSTRAINT check_error_status
        CHECK (status IN ('unresolved', 'resolved', 'ignored', 'muted'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 3. AGGREGATED METRICS (Hourly Analytics)
-- ============================================

CREATE TABLE IF NOT EXISTS aggregated_metrics (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL,
    date VARCHAR(8) NOT NULL,
    hour SMALLINT NOT NULL,
    metric_type VARCHAR(20) NOT NULL,
    endpoint_method VARCHAR(10),
    endpoint_path VARCHAR(500),
    log_level VARCHAR(20),
    log_type VARCHAR(30),
    log_count INTEGER DEFAULT 0 NOT NULL,
    error_count INTEGER DEFAULT 0 NOT NULL,
    avg_duration_ms FLOAT,
    min_duration_ms INTEGER,
    max_duration_ms INTEGER,
    p95_duration_ms INTEGER,
    p99_duration_ms INTEGER,
    extra_metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_aggregated_metrics_lookup ON aggregated_metrics (project_id, date, metric_type);
CREATE INDEX IF NOT EXISTS idx_aggregated_metrics_endpoint ON aggregated_metrics (project_id, date, endpoint_path) WHERE metric_type = 'endpoint';
CREATE UNIQUE INDEX IF NOT EXISTS uq_aggregated_metrics ON aggregated_metrics (
    project_id, date, hour, metric_type,
    COALESCE(endpoint_method, ''), COALESCE(endpoint_path, ''),
    COALESCE(log_level, ''), COALESCE(log_type, '')
);

DO $$ BEGIN
    ALTER TABLE aggregated_metrics ADD CONSTRAINT check_metric_type
        CHECK (metric_type IN ('exception', 'endpoint', 'log_volume'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE aggregated_metrics ADD CONSTRAINT check_hour_range
        CHECK (hour >= 0 AND hour <= 23);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE aggregated_metrics ADD CONSTRAINT check_log_level
        CHECK (log_level IS NULL OR log_level IN ('debug', 'info', 'warning', 'error', 'critical'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE aggregated_metrics ADD CONSTRAINT check_log_type
        CHECK (log_type IS NULL OR log_type IN ('console', 'logger', 'exception', 'network', 'database', 'endpoint', 'custom'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 4. BOTTLENECK METRICS (Route Performance Tracking)
-- ============================================

CREATE TABLE IF NOT EXISTS bottleneck_metrics (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL,
    date VARCHAR(8) NOT NULL,
    hour SMALLINT NOT NULL,
    route VARCHAR(500) NOT NULL,
    log_count INTEGER DEFAULT 0 NOT NULL,
    min_duration_ms INTEGER DEFAULT 0,
    max_duration_ms INTEGER DEFAULT 0,
    avg_duration_ms FLOAT DEFAULT 0,
    median_duration_ms INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bottleneck_metrics_lookup ON bottleneck_metrics (project_id, date, hour);
CREATE INDEX IF NOT EXISTS idx_bottleneck_metrics_route ON bottleneck_metrics (project_id, date, route);
CREATE UNIQUE INDEX IF NOT EXISTS uq_bottleneck_metrics ON bottleneck_metrics (project_id, date, hour, route);

DO $$ BEGIN
    ALTER TABLE bottleneck_metrics ADD CONSTRAINT check_bottleneck_hour_range
        CHECK (hour >= 0 AND hour <= 23);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 5. ROLLUP TABLES (APScheduler-populated aggregations)
-- ============================================

CREATE TABLE IF NOT EXISTS log_volume_5m (
    project_id  BIGINT NOT NULL,
    level       VARCHAR(20) NOT NULL,
    bucket      TIMESTAMPTZ NOT NULL,
    count       BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, level, bucket)
);
CREATE INDEX IF NOT EXISTS idx_lv5m_project_bucket ON log_volume_5m (project_id, bucket DESC);

CREATE TABLE IF NOT EXISTS log_volume_1h (
    project_id  BIGINT NOT NULL,
    level       VARCHAR(20) NOT NULL,
    bucket      TIMESTAMPTZ NOT NULL,
    count       BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, level, bucket)
);
CREATE INDEX IF NOT EXISTS idx_lv1h_project_bucket ON log_volume_1h (project_id, bucket DESC);

CREATE TABLE IF NOT EXISTS log_volume_1d (
    project_id  BIGINT NOT NULL,
    level       VARCHAR(20) NOT NULL,
    bucket      DATE NOT NULL,
    count       BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, level, bucket)
);
CREATE INDEX IF NOT EXISTS idx_lv1d_project_bucket ON log_volume_1d (project_id, bucket DESC);

CREATE TABLE IF NOT EXISTS error_rate_5m (
    project_id  BIGINT NOT NULL,
    bucket      TIMESTAMPTZ NOT NULL,
    errors      BIGINT NOT NULL DEFAULT 0,
    total       BIGINT NOT NULL DEFAULT 0,
    ratio       DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, bucket)
);
CREATE INDEX IF NOT EXISTS idx_er5m_project_bucket ON error_rate_5m (project_id, bucket DESC);

CREATE TABLE IF NOT EXISTS endpoint_latency_1h (
    project_id  BIGINT NOT NULL,
    route       TEXT NOT NULL,
    bucket      TIMESTAMPTZ NOT NULL,
    count       BIGINT NOT NULL DEFAULT 0,
    p50_ms      DOUBLE PRECISION,
    p95_ms      DOUBLE PRECISION,
    p99_ms      DOUBLE PRECISION,
    PRIMARY KEY (project_id, route, bucket)
);
CREATE INDEX IF NOT EXISTS idx_el1h_project_bucket ON endpoint_latency_1h (project_id, bucket DESC);

CREATE TABLE IF NOT EXISTS rollup_job_state (
    job_name    TEXT NOT NULL PRIMARY KEY,
    last_bucket TIMESTAMPTZ NOT NULL
);

-- ============================================
-- 6. SPANS TABLE (Distributed Tracing)
-- ============================================

CREATE TABLE IF NOT EXISTS spans (
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

CREATE INDEX IF NOT EXISTS brin_spans_project_time ON spans USING BRIN (project_id, start_time);
CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans (trace_id);
CREATE INDEX IF NOT EXISTS idx_spans_op ON spans (project_id, service_name, name, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_spans_errors ON spans (project_id, start_time DESC) WHERE status_code = 2;

CREATE TABLE IF NOT EXISTS span_latency_1h (
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
CREATE INDEX IF NOT EXISTS idx_sl1h_project_bucket ON span_latency_1h (project_id, bucket DESC);
