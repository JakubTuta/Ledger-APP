-- ============================================
-- 1. ACCOUNTS & AUTHENTICATION
-- ============================================

CREATE TABLE accounts (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    company_name VARCHAR(255),
    plan VARCHAR(50) DEFAULT 'free', -- free, pro, enterprise
    status VARCHAR(20) DEFAULT 'active', -- active, suspended, deleted
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_accounts_email ON accounts(email);
CREATE INDEX idx_accounts_status ON accounts(status) WHERE status = 'active';

-- ============================================
-- 2. PROJECTS (multi-tenancy)
-- ============================================

CREATE TABLE projects (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL, -- URL-friendly identifier
    environment VARCHAR(50) DEFAULT 'production', -- production, staging, dev
    
    -- Settings
    retention_days INTEGER DEFAULT 30, -- How long to keep logs
    daily_quota BIGINT DEFAULT 1000000, -- Max logs per day
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_projects_account_id ON projects(account_id);
CREATE INDEX idx_projects_slug ON projects(slug);

-- ============================================
-- 3. API KEYS
-- ============================================

CREATE TABLE api_keys (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    
    -- Key parts
    key_prefix VARCHAR(20) NOT NULL, -- e.g., "ak_live_" (visible to user)
    key_hash VARCHAR(255) NOT NULL UNIQUE, -- bcrypt hash of full key
    
    -- Metadata
    name VARCHAR(255), -- User-given name "Production API Key"
    last_used_at TIMESTAMPTZ,
    
    -- Security
    status VARCHAR(20) DEFAULT 'active', -- active, revoked
    expires_at TIMESTAMPTZ, -- NULL = never expires
    
    -- Rate limiting (per key)
    rate_limit_per_minute INTEGER DEFAULT 1000,
    rate_limit_per_hour INTEGER DEFAULT 50000,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_project_id ON projects(project_id);
CREATE INDEX idx_api_keys_status ON api_keys(status) WHERE status = 'active';

-- ============================================
-- 4. USAGE TRACKING (for quotas & billing)
-- ============================================

CREATE TABLE daily_usage (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    
    logs_ingested BIGINT DEFAULT 0,
    logs_queried BIGINT DEFAULT 0,
    storage_bytes BIGINT DEFAULT 0,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(project_id, date)
);

CREATE INDEX idx_daily_usage_project_date ON daily_usage(project_id, date DESC);
