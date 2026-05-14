-- ============================================
-- 1. ACCOUNTS & AUTHENTICATION
-- ============================================

CREATE TABLE accounts (
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

CREATE UNIQUE INDEX CONCURRENTLY idx_accounts_email 
ON accounts(email);

CREATE INDEX CONCURRENTLY idx_accounts_status
ON accounts(status)
WHERE status = 'active';

CREATE INDEX CONCURRENTLY idx_accounts_notification_prefs
ON accounts USING GIN(notification_preferences);

-- ============================================
-- 2. REFRESH TOKENS (JWT refresh)
-- ============================================

CREATE TABLE refresh_tokens (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    device_info VARCHAR(255),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    last_used_at TIMESTAMPTZ
);

CREATE INDEX CONCURRENTLY idx_refresh_tokens_token_hash
ON refresh_tokens(token_hash);

CREATE INDEX CONCURRENTLY idx_refresh_tokens_account_id
ON refresh_tokens(account_id);

CREATE INDEX CONCURRENTLY idx_refresh_tokens_active
ON refresh_tokens(token_hash, account_id, expires_at)
WHERE revoked = FALSE;

CREATE INDEX CONCURRENTLY idx_refresh_tokens_cleanup
ON refresh_tokens(expires_at)
WHERE revoked = FALSE;

ALTER TABLE refresh_tokens
ADD CONSTRAINT fk_refresh_tokens_account
FOREIGN KEY (account_id) REFERENCES accounts(id)
ON DELETE CASCADE;

-- ============================================
-- 3. PROJECTS (multi-tenancy)
-- ============================================

CREATE TABLE projects (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    environment VARCHAR(20) DEFAULT 'production',
    retention_days SMALLINT DEFAULT 30,
    daily_quota BIGINT DEFAULT 1000000,
    available_routes TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX CONCURRENTLY idx_projects_account_id 
ON projects(account_id);

ALTER TABLE projects 
ADD CONSTRAINT fk_projects_account 
FOREIGN KEY (account_id) REFERENCES accounts(id) 
ON DELETE CASCADE;

CREATE UNIQUE INDEX CONCURRENTLY idx_projects_slug 
ON projects(slug);

-- ============================================
-- 3. API KEYS
-- ============================================

CREATE TABLE api_keys (
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

CREATE UNIQUE INDEX CONCURRENTLY idx_api_keys_key_hash 
ON api_keys(key_hash);

CREATE INDEX CONCURRENTLY idx_api_keys_validation
ON api_keys(key_hash, status, expires_at, project_id)
WHERE status = 'active';

CREATE INDEX CONCURRENTLY idx_api_keys_project_id 
ON projects(account_id);


-- ============================================
-- 4. USAGE TRACKING (for quotas & billing)
-- ============================================

CREATE TABLE daily_usage (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL,
    date DATE NOT NULL,
    logs_ingested BIGINT DEFAULT 0,
    logs_queried BIGINT DEFAULT 0,
    storage_bytes BIGINT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_project_date UNIQUE(project_id, date)
);

CREATE INDEX CONCURRENTLY idx_daily_usage_project_date
ON daily_usage(project_id, date DESC);

-- ============================================
-- 5. USER DASHBOARDS (panel configuration)
-- ============================================

CREATE TABLE user_dashboards (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    panels JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_user_dashboard UNIQUE(user_id)
);

CREATE INDEX CONCURRENTLY idx_user_dashboards_user_id
ON user_dashboards(user_id);

CREATE INDEX CONCURRENTLY idx_user_dashboards_panels
ON user_dashboards USING GIN(panels);

ALTER TABLE user_dashboards
ADD CONSTRAINT fk_user_dashboards_account
FOREIGN KEY (user_id) REFERENCES accounts(id)
ON DELETE CASCADE;

-- ============================================
-- 6. PERSISTED NOTIFICATIONS
-- ============================================

CREATE TABLE notifications (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    project_id  BIGINT NOT NULL,
    kind        TEXT NOT NULL,
    severity    SMALLINT NOT NULL DEFAULT 1,
    payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at     TIMESTAMPTZ,
    expires_at  TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '30 days'
);

CREATE INDEX idx_notif_unread ON notifications (user_id, created_at DESC)
WHERE read_at IS NULL;
CREATE INDEX idx_notif_expires ON notifications (expires_at);
CREATE INDEX idx_notif_user_project ON notifications (user_id, project_id, created_at DESC);

ALTER TABLE notifications
    ADD CONSTRAINT check_notification_kind
    CHECK (kind IN ('error', 'alert_firing', 'alert_resolved', 'quota_warning'));
ALTER TABLE notifications
    ADD CONSTRAINT check_notification_severity
    CHECK (severity IN (1, 2, 3));

-- ============================================
-- 8. ALERT RULES ENGINE
-- ============================================

CREATE TABLE alert_rules (
    id               BIGSERIAL PRIMARY KEY,
    project_id       BIGINT NOT NULL,
    name             TEXT NOT NULL,
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    metric           TEXT NOT NULL,
    tag_filter       JSONB DEFAULT '{}'::jsonb,
    comparator       TEXT NOT NULL,
    threshold        DOUBLE PRECISION NOT NULL,
    window_seconds   INTEGER NOT NULL,
    cooldown_seconds INTEGER NOT NULL DEFAULT 600,
    severity         SMALLINT NOT NULL DEFAULT 2,
    channels         JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_fired_at    TIMESTAMPTZ,
    last_state       TEXT NOT NULL DEFAULT 'ok',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alert_rules_project ON alert_rules (project_id);
CREATE INDEX idx_alert_rules_enabled ON alert_rules (enabled) WHERE enabled = TRUE;

ALTER TABLE alert_rules
    ADD CONSTRAINT check_alert_comparator
    CHECK (comparator IN ('>', '<', '>=', '<='));
ALTER TABLE alert_rules
    ADD CONSTRAINT check_alert_severity
    CHECK (severity IN (1, 2, 3));
ALTER TABLE alert_rules
    ADD CONSTRAINT check_alert_state
    CHECK (last_state IN ('ok', 'firing'));

CREATE TABLE alert_channels (
    id          BIGSERIAL PRIMARY KEY,
    project_id  BIGINT NOT NULL,
    user_id     BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    config      JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alert_channels_project ON alert_channels (project_id);
CREATE INDEX idx_alert_channels_user ON alert_channels (user_id);

ALTER TABLE alert_channels
    ADD CONSTRAINT check_channel_kind
    CHECK (kind IN ('in_app', 'email', 'webhook'));

CREATE TABLE notification_preferences (
    user_id     BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    project_id  BIGINT NOT NULL,
    rule_id     BIGINT,
    severity    SMALLINT,
    muted       BOOLEAN NOT NULL DEFAULT FALSE,
    channels    JSONB,
    PRIMARY KEY (user_id, project_id, COALESCE(rule_id, 0), COALESCE(severity, 0))
);

CREATE INDEX idx_notif_prefs_user_project ON notification_preferences (user_id, project_id);
