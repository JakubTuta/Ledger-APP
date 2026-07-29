"""initial_schema

Revision ID: a2dd1ac4850d
Revises: 
Create Date: 2025-10-10 23:03:33.442045

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2dd1ac4850d'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id BIGSERIAL NOT NULL,
            email VARCHAR(255) NOT NULL,
            password_hash CHAR(60) NOT NULL,
            plan VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT check_account_plan CHECK (plan IN ('free', 'pro', 'enterprise')),
            CONSTRAINT check_account_status CHECK (status IN ('active', 'suspended', 'deleted'))
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_accounts_email ON accounts (email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts (status) WHERE status = 'active'")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_accounts_email ON accounts (email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_accounts_id ON accounts (id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id BIGSERIAL NOT NULL,
            account_id BIGINT NOT NULL,
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(255) NOT NULL,
            environment VARCHAR(20) NOT NULL,
            retention_days SMALLINT NOT NULL,
            daily_quota BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT check_project_environment CHECK (environment IN ('production', 'staging', 'dev')),
            CONSTRAINT check_daily_quota CHECK (daily_quota >= 1000),
            CONSTRAINT check_retention_days CHECK (retention_days >= 1 AND retention_days <= 365),
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_projects_account_id ON projects (account_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_projects_slug ON projects (slug)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_projects_account_id ON projects (account_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_projects_id ON projects (id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_projects_slug ON projects (slug)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id BIGSERIAL NOT NULL,
            project_id BIGINT NOT NULL,
            key_prefix VARCHAR(20) NOT NULL,
            key_hash CHAR(60) NOT NULL,
            name VARCHAR(255),
            last_used_at TIMESTAMPTZ,
            status VARCHAR(20) NOT NULL,
            expires_at TIMESTAMPTZ,
            rate_limit_per_minute INTEGER NOT NULL,
            rate_limit_per_hour INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT check_api_key_status CHECK (status IN ('active', 'revoked')),
            CONSTRAINT check_rate_limit_per_hour CHECK (rate_limit_per_hour >= 100),
            CONSTRAINT check_rate_limit_per_minute CHECK (rate_limit_per_minute >= 10),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys (key_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_project_id ON api_keys (project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_validation ON api_keys (key_hash, status, expires_at, project_id) WHERE status = 'active'")
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_keys_id ON api_keys (id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_api_keys_key_hash ON api_keys (key_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_keys_project_id ON api_keys (project_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS daily_usage (
            id BIGSERIAL NOT NULL,
            project_id BIGINT NOT NULL,
            date TIMESTAMP NOT NULL,
            logs_ingested BIGINT NOT NULL,
            logs_queried BIGINT NOT NULL,
            storage_bytes BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT check_logs_ingested CHECK (logs_ingested >= 0),
            CONSTRAINT check_logs_queried CHECK (logs_queried >= 0),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_usage_project_date ON daily_usage (project_id, date DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daily_usage_id ON daily_usage (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daily_usage_project_id ON daily_usage (project_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_usage_project_date ON daily_usage (project_id, date)")


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('uq_daily_usage_project_date', table_name='daily_usage')
    op.drop_index(op.f('ix_daily_usage_project_id'), table_name='daily_usage')
    op.drop_index(op.f('ix_daily_usage_id'), table_name='daily_usage')
    op.drop_index('idx_daily_usage_project_date', table_name='daily_usage', postgresql_ops={'date': 'DESC'})
    op.drop_table('daily_usage')
    op.drop_index(op.f('ix_api_keys_project_id'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_key_hash'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_id'), table_name='api_keys')
    op.drop_index('idx_api_keys_validation', table_name='api_keys', postgresql_where=sa.text("status = 'active'"))
    op.drop_index('idx_api_keys_project_id', table_name='api_keys')
    op.drop_index('idx_api_keys_key_hash', table_name='api_keys')
    op.drop_table('api_keys')
    op.drop_index(op.f('ix_projects_slug'), table_name='projects')
    op.drop_index(op.f('ix_projects_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_account_id'), table_name='projects')
    op.drop_index('idx_projects_slug', table_name='projects')
    op.drop_index('idx_projects_account_id', table_name='projects')
    op.drop_table('projects')
    op.drop_index(op.f('ix_accounts_id'), table_name='accounts')
    op.drop_index(op.f('ix_accounts_email'), table_name='accounts')
    op.drop_index('idx_accounts_status', table_name='accounts', postgresql_where=sa.text("status = 'active'"))
    op.drop_index('idx_accounts_email', table_name='accounts')
    op.drop_table('accounts')
    # ### end Alembic commands ###