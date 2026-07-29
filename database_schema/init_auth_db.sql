-- Auth DB bootstrap. Kept in sync with
-- services/migrations/migration_service/alembic/auth/versions/*
-- (current head: b8c9d0e1f2a3) and services/auth/auth_service/models.py.
--
-- Index policy: one index per access path. A primary key already has a unique
-- index, a unique constraint already has one, and Postgres can use any leading
-- prefix of a composite index - so none of those get a second narrow copy.
-- See revision a7b8c9d0e1f2 for the duplicates that were removed.
--
-- Constraint/index names below are written to match what Alembic actually
-- produced (verified against a fresh `alembic upgrade head`), not Postgres's
-- default naming - a handful of columns use SQLAlchemy's `index=True`/`unique=True`
-- shorthand (named `ix_<table>_<col>`) or an explicitly named constraint,
-- rather than the plain inline `UNIQUE`/`REFERENCES` this file would otherwise
-- default to.

-- ============================================
-- 1. ACCOUNTS & AUTHENTICATION
-- ============================================

CREATE TABLE IF NOT EXISTS accounts (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    password_hash CHAR(60) NOT NULL,
    name VARCHAR(255) NOT NULL,
    plan VARCHAR(20) DEFAULT 'free' NOT NULL,
    status VARCHAR(20) DEFAULT 'active' NOT NULL,
    notification_preferences JSONB NOT NULL DEFAULT '{"enabled": true, "projects": {}}'::jsonb,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    email_verification_token CHAR(64),
    email_verification_sent_at TIMESTAMPTZ,
    totp_secret VARCHAR(32),
    totp_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    totp_backup_codes JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_accounts_email ON accounts (email);
CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts (status) WHERE status = 'active';

DO $$ BEGIN
    ALTER TABLE accounts ADD CONSTRAINT uq_accounts_email_verification_token
        UNIQUE (email_verification_token);
EXCEPTION WHEN duplicate_table THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE accounts ADD CONSTRAINT check_account_plan
        CHECK (plan IN ('free', 'pro', 'enterprise'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE accounts ADD CONSTRAINT check_account_status
        CHECK (status IN ('active', 'suspended', 'deleted'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 2. REFRESH TOKENS (JWT refresh)
-- ============================================

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL,
    token_hash CHAR(64) NOT NULL,
    device_info VARCHAR(255),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    last_used_at TIMESTAMPTZ
);

DO $$ BEGIN
    ALTER TABLE refresh_tokens ADD CONSTRAINT fk_refresh_tokens_account
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE refresh_tokens ADD CONSTRAINT uq_refresh_tokens_token_hash
        UNIQUE (token_hash);
EXCEPTION WHEN duplicate_table THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_account_id ON refresh_tokens (account_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_active ON refresh_tokens (token_hash, account_id, expires_at) WHERE revoked = FALSE;
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_cleanup ON refresh_tokens (expires_at) WHERE revoked = FALSE;

-- ============================================
-- 3. PROJECTS (multi-tenancy)
-- ============================================

CREATE TABLE IF NOT EXISTS projects (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    environment VARCHAR(20) DEFAULT 'production' NOT NULL,
    retention_days SMALLINT DEFAULT 30 NOT NULL,
    logs_daily_quota BIGINT DEFAULT 100000 NOT NULL,
    spans_daily_quota BIGINT DEFAULT 300000 NOT NULL,
    metrics_daily_quota BIGINT DEFAULT 100000 NOT NULL,
    available_routes VARCHAR[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_projects_slug ON projects (slug);
CREATE INDEX IF NOT EXISTS idx_projects_account_id ON projects (account_id);

DO $$ BEGIN
    ALTER TABLE projects ADD CONSTRAINT check_project_environment
        CHECK (environment IN ('production', 'staging', 'dev'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE projects ADD CONSTRAINT check_retention_days
        CHECK (retention_days >= 1 AND retention_days <= 365);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE projects ADD CONSTRAINT check_logs_daily_quota
        CHECK (logs_daily_quota >= 1000);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE projects ADD CONSTRAINT check_spans_daily_quota
        CHECK (spans_daily_quota >= 1000);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE projects ADD CONSTRAINT check_metrics_daily_quota
        CHECK (metrics_daily_quota >= 1000);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 4. API KEYS
-- ============================================

CREATE TABLE IF NOT EXISTS api_keys (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    key_prefix VARCHAR(20) NOT NULL,
    -- SHA-256 hex digest: an indexed equality lookup, not a bcrypt compare.
    key_hash CHAR(64) NOT NULL,
    name VARCHAR(255),
    last_used_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'active' NOT NULL,
    expires_at TIMESTAMPTZ,
    rate_limit_per_minute INTEGER DEFAULT 1000 NOT NULL,
    rate_limit_per_hour INTEGER DEFAULT 50000 NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_api_keys_key_hash ON api_keys (key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_project_id ON api_keys (project_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_validation ON api_keys (key_hash, status, expires_at, project_id) WHERE status = 'active';

DO $$ BEGIN
    ALTER TABLE api_keys ADD CONSTRAINT check_api_key_status
        CHECK (status IN ('active', 'revoked'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE api_keys ADD CONSTRAINT check_rate_limit_per_minute
        CHECK (rate_limit_per_minute >= 10);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE api_keys ADD CONSTRAINT check_rate_limit_per_hour
        CHECK (rate_limit_per_hour >= 100);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 5. USAGE TRACKING (for quotas & billing)
-- ============================================

CREATE TABLE IF NOT EXISTS daily_usage (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    -- TIMESTAMP, not DATE: the ORM column is DateTime(timezone=False) - a date
    -- value goes in, but the column itself doesn't enforce that.
    date TIMESTAMP NOT NULL,
    logs_ingested BIGINT DEFAULT 0 NOT NULL,
    spans_ingested BIGINT DEFAULT 0 NOT NULL,
    metric_points_ingested BIGINT DEFAULT 0 NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Doubles as the upsert conflict target and the read path; Postgres scans it
-- backwards for the date-descending queries.
CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_usage_project_date ON daily_usage (project_id, date);

DO $$ BEGIN
    ALTER TABLE daily_usage ADD CONSTRAINT check_logs_ingested CHECK (logs_ingested >= 0);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 6. PROJECT SHARING
-- ============================================

CREATE TABLE IF NOT EXISTS project_members (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    role VARCHAR(20) DEFAULT 'member' NOT NULL,
    joined_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT uq_project_members UNIQUE (project_id, account_id)
);

CREATE INDEX IF NOT EXISTS idx_project_members_account_id ON project_members (account_id);

DO $$ BEGIN
    ALTER TABLE project_members ADD CONSTRAINT check_member_role
        CHECK (role IN ('owner', 'member'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS project_invite_codes (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code_hash CHAR(64) NOT NULL,
    created_by BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    used_by BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT uq_invite_code_hash UNIQUE (code_hash)
);

CREATE INDEX IF NOT EXISTS idx_invite_codes_code_hash ON project_invite_codes (code_hash) WHERE used_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_invite_codes_project_expires ON project_invite_codes (project_id, expires_at);

-- ============================================
-- 7. USER DASHBOARDS (panel configuration)
-- ============================================

CREATE TABLE IF NOT EXISTS user_dashboards (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    panels JSONB NOT NULL DEFAULT '[]'::jsonb,
    tabs JSONB NOT NULL DEFAULT '[]'::jsonb,
    active_tab_id VARCHAR,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    UNIQUE (user_id)
);

-- ============================================
-- 8. PERSISTED NOTIFICATIONS
-- ============================================

CREATE TABLE IF NOT EXISTS notifications (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    project_id BIGINT NOT NULL,
    kind       VARCHAR(30) NOT NULL,
    severity   VARCHAR(20) NOT NULL DEFAULT 'info',
    payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at    TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications (user_id, read_at);
CREATE INDEX IF NOT EXISTS idx_notifications_project_id ON notifications (project_id);
CREATE INDEX IF NOT EXISTS idx_notifications_expires_at ON notifications (expires_at);

DO $$ BEGIN
    ALTER TABLE notifications ADD CONSTRAINT check_notification_kind
        CHECK (kind IN ('error', 'alert_firing', 'alert_resolved', 'quota_warning'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE notifications ADD CONSTRAINT check_notification_severity
        CHECK (severity IN ('critical', 'warning', 'info'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 9. ALERT RULES ENGINE
-- ============================================

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
        CHECK (kind IN ('in_app', 'email', 'webhook', 'slack', 'discord', 'pagerduty', 'opsgenie'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

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
    escalation_after_minutes SMALLINT,
    -- INTEGER, not BIGINT like the account/project FK columns elsewhere in
    -- this file - matches the migration that added this column.
    escalate_connector_id    INTEGER,
    escalated_at             TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_rules_project_id ON alert_rules (project_id);

DO $$ BEGIN
    ALTER TABLE alert_rules ADD CONSTRAINT fk_alert_rules_escalate_connector_id
        FOREIGN KEY (escalate_connector_id) REFERENCES connectors(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

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
    fired_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- INTEGER, not BIGINT - matches the migration that added this column.
    acked_by        INTEGER,
    acked_at        TIMESTAMPTZ,
    snoozed_until   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_alert_events_project_fired ON alert_events (project_id, fired_at);
-- The evaluator's two per-rule reads are both "newest event for this rule".
CREATE INDEX IF NOT EXISTS idx_alert_events_rule_id ON alert_events (rule_id, id DESC);

DO $$ BEGIN
    ALTER TABLE alert_events ADD CONSTRAINT fk_alert_events_acked_by
        FOREIGN KEY (acked_by) REFERENCES accounts(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE alert_events ADD CONSTRAINT check_alert_event_state
        CHECK (state IN ('firing', 'resolved'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS notification_preferences (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    project_id BIGINT NOT NULL,
    rule_id    BIGINT REFERENCES alert_rules(id) ON DELETE CASCADE,
    severity   VARCHAR(20),
    muted      BOOLEAN NOT NULL DEFAULT FALSE,
    channel_overrides JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notif_prefs_user_project ON notification_preferences (user_id, project_id);

DO $$ BEGIN
    ALTER TABLE notification_preferences ADD CONSTRAINT uq_notif_prefs
        UNIQUE (user_id, project_id, rule_id, severity);
EXCEPTION WHEN duplicate_table THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE notification_preferences ADD CONSTRAINT check_notif_pref_severity
        CHECK (severity IS NULL OR severity IN ('critical', 'warning', 'info'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 10. MAINTENANCE WINDOWS (alert suppression)
-- ============================================

CREATE TABLE IF NOT EXISTS maintenance_windows (
    id         BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name       VARCHAR(255) NOT NULL,
    starts_at  TIMESTAMPTZ NOT NULL,
    ends_at    TIMESTAMPTZ NOT NULL,
    recurrence VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_maintenance_windows_project_id ON maintenance_windows (project_id);

DO $$ BEGIN
    ALTER TABLE maintenance_windows ADD CONSTRAINT check_maintenance_window_recurrence
        CHECK (recurrence IN ('none', 'daily', 'weekly') OR recurrence IS NULL);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 11. MONITORS (uptime + heartbeat)
-- ============================================

CREATE TABLE IF NOT EXISTS monitors (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind            VARCHAR(20) NOT NULL,
    name            VARCHAR(255) NOT NULL,
    target_url      VARCHAR(2048),
    token           VARCHAR(64),
    interval_s      INTEGER NOT NULL DEFAULT 60,
    timeout_s       INTEGER NOT NULL DEFAULT 10,
    expected_status INTEGER NOT NULL DEFAULT 200,
    grace_s         INTEGER NOT NULL DEFAULT 0,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    state           VARCHAR(10) NOT NULL DEFAULT 'unknown',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_monitors_project_id ON monitors (project_id);
-- Partial, so the many heartbeat-less http monitors don't occupy the index.
CREATE UNIQUE INDEX IF NOT EXISTS idx_monitors_token ON monitors (token) WHERE token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_monitors_enabled ON monitors (kind, enabled) WHERE enabled = TRUE;

DO $$ BEGIN
    ALTER TABLE monitors ADD CONSTRAINT check_monitor_kind
        CHECK (kind IN ('http', 'heartbeat'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE monitors ADD CONSTRAINT check_monitor_state
        CHECK (state IN ('unknown', 'up', 'down'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS monitor_checks (
    id          BIGSERIAL PRIMARY KEY,
    monitor_id  BIGINT NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
    checked_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ok          BOOLEAN NOT NULL,
    latency_ms  INTEGER,
    status_code INTEGER,
    error       TEXT
);

-- Latest-check lookup and the 24h uptime window.
CREATE INDEX IF NOT EXISTS idx_monitor_checks_monitor_checked ON monitor_checks (monitor_id, checked_at);
-- Retention trim (see the analytics retention job).
CREATE INDEX IF NOT EXISTS idx_monitor_checks_checked_at ON monitor_checks (checked_at);
