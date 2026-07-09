-- ============================================
-- 1. ACCOUNTS & AUTHENTICATION
-- ============================================

CREATE TABLE IF NOT EXISTS accounts (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    password_hash CHAR(60) NOT NULL,
    name VARCHAR(255) NOT NULL,
    plan VARCHAR(20) DEFAULT 'free',
    status VARCHAR(20) DEFAULT 'active',
    notification_preferences JSONB NOT NULL DEFAULT '{"enabled": true, "projects": {}}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_accounts_email ON accounts (email);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_accounts_status ON accounts (status) WHERE status = 'active';
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_accounts_notification_prefs ON accounts USING GIN (notification_preferences);

-- ============================================
-- 2. REFRESH TOKENS (JWT refresh)
-- ============================================

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    device_info VARCHAR(255),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    last_used_at TIMESTAMPTZ
);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_refresh_tokens_token_hash ON refresh_tokens (token_hash);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_refresh_tokens_account_id ON refresh_tokens (account_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_refresh_tokens_active ON refresh_tokens (token_hash, account_id, expires_at) WHERE revoked = FALSE;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_refresh_tokens_cleanup ON refresh_tokens (expires_at) WHERE revoked = FALSE;

DO $$ BEGIN
    ALTER TABLE refresh_tokens ADD CONSTRAINT fk_refresh_tokens_account
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 3. PROJECTS (multi-tenancy)
-- ============================================

CREATE TABLE IF NOT EXISTS projects (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    environment VARCHAR(20) DEFAULT 'production',
    retention_days SMALLINT DEFAULT 30,
    daily_quota BIGINT DEFAULT 100000,
    available_routes TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_projects_account_id ON projects (account_id);
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_projects_slug ON projects (slug);

DO $$ BEGIN
    ALTER TABLE projects ADD CONSTRAINT fk_projects_account
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 4. API KEYS
-- ============================================

CREATE TABLE IF NOT EXISTS api_keys (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL,
    key_prefix VARCHAR(20) NOT NULL,
    key_hash CHAR(60) NOT NULL,
    name VARCHAR(255),
    last_used_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'active',
    expires_at TIMESTAMPTZ,
    rate_limit_per_minute INTEGER DEFAULT 1000,
    rate_limit_per_hour INTEGER DEFAULT 50000,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_api_keys_key_hash ON api_keys (key_hash);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_api_keys_validation ON api_keys (key_hash, status, expires_at, project_id) WHERE status = 'active';
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_api_keys_project_id ON api_keys (project_id);

-- ============================================
-- 5. USAGE TRACKING (for quotas & billing)
-- ============================================

CREATE TABLE IF NOT EXISTS daily_usage (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL,
    date DATE NOT NULL,
    logs_ingested BIGINT DEFAULT 0,
    logs_queried BIGINT DEFAULT 0,
    storage_bytes BIGINT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_project_date UNIQUE (project_id, date)
);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_usage_project_date ON daily_usage (project_id, date DESC);

-- ============================================
-- 6. USER DASHBOARDS (panel configuration)
-- ============================================

CREATE TABLE IF NOT EXISTS user_dashboards (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    panels JSONB NOT NULL DEFAULT '[]'::jsonb,
    tabs JSONB NOT NULL DEFAULT '[]'::jsonb,
    active_tab_id VARCHAR,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_user_dashboard UNIQUE (user_id)
);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_dashboards_user_id ON user_dashboards (user_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_dashboards_panels ON user_dashboards USING GIN (panels);

DO $$ BEGIN
    ALTER TABLE user_dashboards ADD CONSTRAINT fk_user_dashboards_account
        FOREIGN KEY (user_id) REFERENCES accounts(id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 7. PERSISTED NOTIFICATIONS
-- ============================================

CREATE TABLE IF NOT EXISTS notifications (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    project_id BIGINT NOT NULL,
    kind       TEXT NOT NULL,
    severity   SMALLINT NOT NULL DEFAULT 1,
    payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at    TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '30 days'
);

CREATE INDEX IF NOT EXISTS idx_notif_unread ON notifications (user_id, created_at DESC) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_notif_expires ON notifications (expires_at);
CREATE INDEX IF NOT EXISTS idx_notif_user_project ON notifications (user_id, project_id, created_at DESC);

DO $$ BEGIN
    ALTER TABLE notifications ADD CONSTRAINT check_notification_kind
        CHECK (kind IN ('error', 'alert_firing', 'alert_resolved', 'quota_warning'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE notifications ADD CONSTRAINT check_notification_severity
        CHECK (severity IN (1, 2, 3));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 8. ALERT RULES ENGINE
-- ============================================

CREATE TABLE IF NOT EXISTS alert_rules (
    id            BIGSERIAL PRIMARY KEY,
    project_id    BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name          VARCHAR(255) NOT NULL,
    metric_type   VARCHAR(50) NOT NULL,
    comparator    VARCHAR(4) NOT NULL,
    threshold     DOUBLE PRECISION NOT NULL,
    unit          VARCHAR(8) NOT NULL DEFAULT 'count',
    severity      VARCHAR(20) NOT NULL DEFAULT 'warning',
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    state         VARCHAR(10) NOT NULL DEFAULT 'ok',
    last_fired_at TIMESTAMPTZ,
    fired_value   DOUBLE PRECISION,
    for_minutes      SMALLINT NOT NULL DEFAULT 0,
    cooldown_minutes SMALLINT NOT NULL DEFAULT 0,
    last_notified_at TIMESTAMPTZ,
    pending_since    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_rules_project_id ON alert_rules (project_id);
CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules (project_id, enabled) WHERE enabled = TRUE;

DO $$ BEGIN
    ALTER TABLE alert_rules ADD CONSTRAINT check_alert_comparator
        CHECK (comparator IN ('>', '<', '>=', '<='));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE alert_rules ADD CONSTRAINT check_alert_severity
        CHECK (severity IN ('critical', 'warning', 'info'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE alert_rules ADD CONSTRAINT check_alert_state
        CHECK (state IN ('ok', 'pending', 'firing'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE alert_rules ADD CONSTRAINT check_alert_unit
        CHECK (unit IN ('ms', 's', '%', 'count'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS connectors (
    id         BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    kind       VARCHAR(20) NOT NULL,
    name       VARCHAR(255) NOT NULL,
    config     JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_connectors_account_id ON connectors (account_id);

DO $$ BEGIN
    ALTER TABLE connectors ADD CONSTRAINT check_connector_kind
        CHECK (kind IN ('in_app', 'email', 'webhook'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS alert_rule_connectors (
    rule_id      BIGINT NOT NULL REFERENCES alert_rules(id) ON DELETE CASCADE,
    connector_id BIGINT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
    PRIMARY KEY (rule_id, connector_id)
);

CREATE INDEX IF NOT EXISTS idx_alert_rule_connectors_connector ON alert_rule_connectors (connector_id);

CREATE TABLE IF NOT EXISTS alert_events (
    id              BIGSERIAL PRIMARY KEY,
    rule_id         BIGINT REFERENCES alert_rules(id) ON DELETE SET NULL,
    project_id      BIGINT NOT NULL,
    rule_name       VARCHAR(255) NOT NULL,
    metric_type     VARCHAR(50) NOT NULL,
    comparator      VARCHAR(4) NOT NULL,
    threshold       DOUBLE PRECISION NOT NULL,
    unit            VARCHAR(8) NOT NULL DEFAULT 'count',
    value           DOUBLE PRECISION NOT NULL,
    severity        VARCHAR(20) NOT NULL DEFAULT 'warning',
    state           VARCHAR(10) NOT NULL,
    connectors_sent JSONB NOT NULL DEFAULT '[]'::jsonb,
    fired_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_events_project_fired ON alert_events (project_id, fired_at);
CREATE INDEX IF NOT EXISTS idx_alert_events_rule_id ON alert_events (rule_id);

DO $$ BEGIN
    ALTER TABLE alert_events ADD CONSTRAINT check_alert_event_state
        CHECK (state IN ('firing', 'resolved'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS notification_preferences (
    user_id    BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    project_id BIGINT NOT NULL,
    rule_id    BIGINT,
    severity   SMALLINT,
    muted      BOOLEAN NOT NULL DEFAULT FALSE,
    channels   JSONB,
    PRIMARY KEY (user_id, project_id, COALESCE(rule_id, 0), COALESCE(severity, 0))
);

CREATE INDEX IF NOT EXISTS idx_notif_prefs_user_project ON notification_preferences (user_id, project_id);
