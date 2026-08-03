-- Logs DB bootstrap. Kept in sync with
-- services/migrations/migration_service/alembic/logs/versions/*
-- (current head: 017) and with the ORM models in
-- services/ingestion/ingestion_service/models.py and
-- services/query/query_service/models.py.
--
-- Index policy for this database: `logs`, `spans` and `metric_points` are on the
-- ingestion hot path, so every index here has to be justified by a query that
-- actually exists. See revision 015 for the list of indexes that were removed
-- and why, and revision 016 for the BRIN additions.
--
-- Constraint names are written to match what Alembic actually produced
-- (verified against a fresh `alembic upgrade head`).

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
    log_id VARCHAR(64),
    client_channel VARCHAR(20),
    client_country CHAR(2),
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- ============================================
-- CHECK CONSTRAINTS
-- ============================================

DO $$ BEGIN
    -- Named check_level, not check_log_level: it was defined inline on the
    -- CREATE TABLE in the initial migration and never renamed, unlike the
    -- same-shaped constraint on aggregated_metrics.log_level.
    ALTER TABLE logs ADD CONSTRAINT check_level
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

-- Log list / keyset pagination: ORDER BY (timestamp DESC, id DESC).
CREATE INDEX IF NOT EXISTS idx_logs_project_timestamp ON logs (project_id, timestamp DESC, id DESC);

-- Error-level slices of the log list and of get_error_list().
CREATE INDEX IF NOT EXISTS idx_logs_project_level ON logs (project_id, level, timestamp DESC)
WHERE level IN ('error', 'critical');

-- Occurrence sparkline for one error group.
CREATE INDEX IF NOT EXISTS idx_logs_error_fingerprint ON logs (project_id, error_fingerprint, timestamp DESC)
WHERE error_fingerprint IS NOT NULL;

-- Every HTTP-shaped read: the status_class filter and facet, the
-- status_code >= 400 arm of get_error_list(), and the alert evaluator's
-- error_rate_4xx / error_rate_5xx window.
CREATE INDEX IF NOT EXISTS idx_logs_project_http ON logs (project_id, timestamp DESC, status_code)
WHERE status_code IS NOT NULL;

-- Analytics aggregates a time window across all projects. Without this the
-- planner falls back to a full index-only scan of idx_logs_project_timestamp
-- with timestamp as a non-boundary qual - work proportional to the partition
-- rather than to the window. BRIN rather than btree because this is the
-- ingestion hot path and log rows arrive in near-timestamp order.
-- NOTE: earlier revisions of this file declared this index as
-- `idx_logs_timestamp`, but no Alembic migration ever created it, so no
-- alembic-provisioned database actually had it. Revision 016 creates it.
CREATE INDEX IF NOT EXISTS brin_logs_timestamp ON logs USING BRIN (timestamp);

-- Conflict target for the ingestion worker's idempotent COPY insert.
CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_dedup ON logs (project_id, log_id, timestamp)
WHERE log_id IS NOT NULL;

-- ============================================
-- PARTITIONS (Monthly - Auto-created)
-- ============================================
-- Note: Partitions are auto-created by ingestion service on startup for logs,
-- spans and metric_points alike, all with the {table}_{YYYY}_{MM} name shape.
-- Old partitions are detached and dropped by the analytics retention job based
-- on retention_days from the projects table.

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
    occurrence_count BIGINT DEFAULT 1 NOT NULL,
    status VARCHAR(20) DEFAULT 'unresolved' NOT NULL,
    assigned_to BIGINT,
    sample_log_id BIGINT,
    sample_stack_trace TEXT,
    resolved_at TIMESTAMPTZ,
    resolved_in_release VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_error_groups_fingerprint ON error_groups (project_id, fingerprint);
CREATE INDEX IF NOT EXISTS idx_error_groups_status ON error_groups (project_id, status, last_seen);
CREATE INDEX IF NOT EXISTS idx_error_groups_last_seen ON error_groups (project_id, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_error_groups_first_seen ON error_groups (project_id, first_seen DESC);
CREATE INDEX IF NOT EXISTS idx_error_groups_resolved ON error_groups (project_id, resolved_at)
WHERE status = 'resolved' AND resolved_at IS NOT NULL;

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

-- `date` trails the equality columns: readers filter project_id/metric_type by
-- equality and `date` as a range.
CREATE INDEX IF NOT EXISTS idx_aggregated_metrics_lookup ON aggregated_metrics (project_id, metric_type, date);
CREATE INDEX IF NOT EXISTS idx_aggregated_metrics_endpoint ON aggregated_metrics (project_id, endpoint_path, date) WHERE metric_type = 'endpoint';
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

-- The unique index doubles as the read index: get_bottleneck_list() filters
-- project_id by equality and `date` as a range, which its leading prefix serves.
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
-- get_trace() and the per-row span_count subquery in list_traces().
CREATE INDEX IF NOT EXISTS idx_spans_project_trace ON spans (project_id, trace_id);
-- list_traces() returns root spans only, newest first.
CREATE INDEX IF NOT EXISTS idx_spans_roots ON spans (project_id, start_time DESC) WHERE parent_span_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_spans_op ON spans (project_id, service_name, name, start_time DESC);

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

-- ============================================
-- 7. METRIC POINTS (OTLP metrics) + hourly rollup
-- ============================================

CREATE TABLE IF NOT EXISTS metric_points (
    project_id      BIGINT NOT NULL,
    name            TEXT NOT NULL,
    type            SMALLINT NOT NULL,
    ts              TIMESTAMPTZ NOT NULL,
    value           DOUBLE PRECISION,
    count           BIGINT,
    sum             DOUBLE PRECISION,
    bucket_counts   JSONB,
    explicit_bounds JSONB,
    tags            JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags_hash       CHAR(16) NOT NULL,
    service_name    TEXT,
    PRIMARY KEY (project_id, name, tags_hash, ts)
) PARTITION BY RANGE (ts);

CREATE INDEX IF NOT EXISTS idx_metric_points_lookup ON metric_points (project_id, name, ts DESC);
-- query_metrics() filters raw points with `tags @> '{...}'::jsonb`.
CREATE INDEX IF NOT EXISTS idx_metric_points_tags ON metric_points USING GIN (tags);
-- usage_stats and the 1h rollup scan `ts` across all projects (see the BRIN on
-- logs.timestamp for the same reasoning).
CREATE INDEX IF NOT EXISTS brin_metric_points_ts ON metric_points USING BRIN (ts);

CREATE TABLE IF NOT EXISTS metric_points_1h (
    project_id   BIGINT NOT NULL,
    name         TEXT NOT NULL,
    type         SMALLINT NOT NULL,
    tags_hash    CHAR(16) NOT NULL,
    tags         JSONB NOT NULL DEFAULT '{}'::jsonb,
    bucket       TIMESTAMPTZ NOT NULL,
    count        BIGINT NOT NULL DEFAULT 0,
    sum_v        DOUBLE PRECISION NOT NULL DEFAULT 0,
    min_v        DOUBLE PRECISION,
    max_v        DOUBLE PRECISION,
    avg_v        DOUBLE PRECISION,
    PRIMARY KEY (project_id, name, tags_hash, bucket)
);

-- ============================================
-- 8. IP COUNTRY RANGES (client IP -> country lookup source)
-- ============================================
-- Source of truth for the ingestion worker's in-memory bisect table (see
-- services/ingestion/ingestion_service/services/ip_country.py). Populated
-- and refreshed weekly by the analytics `rir_refresh` job from the five
-- RIRs' public delegated-extended statistics files, not a per-request table
-- - occasional full-table reads only.
--
-- family: 4 or 6. range_start/range_end: the IPv4 address as a 32-bit
-- integer, or the top 48 bits of an IPv6 address as an integer (matching
-- the SDK's own /48 IPv6 truncation granularity) - both fit comfortably in
-- BIGINT.

CREATE TABLE IF NOT EXISTS ip_country_ranges (
    id BIGSERIAL PRIMARY KEY,
    family SMALLINT NOT NULL,
    range_start BIGINT NOT NULL,
    range_end BIGINT NOT NULL,
    country_code CHAR(2) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$ BEGIN
    ALTER TABLE ip_country_ranges ADD CONSTRAINT check_ip_country_family
        CHECK (family IN (4, 6));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_ip_country_ranges_family_start
    ON ip_country_ranges (family, range_start);
CREATE INDEX IF NOT EXISTS idx_metric_points_1h_lookup ON metric_points_1h (project_id, name, bucket DESC);
