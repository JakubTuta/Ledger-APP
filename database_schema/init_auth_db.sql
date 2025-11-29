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
-- 2. PROJECTS (multi-tenancy)
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
