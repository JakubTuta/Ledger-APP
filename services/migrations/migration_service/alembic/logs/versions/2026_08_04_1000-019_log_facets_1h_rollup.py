"""add log_facets_1h rollup table for the Explore filter sidebar

Revision ID: 019
Revises: 018
Create Date: 2026-08-04 10:00:00.000000

`get_log_facets()` counted every row in the window: a GROUPING SETS pass
over `logs` whose facet dimensions (level, log_type, status_code,
environment, client_channel) live in no index, so the planner range-scans
`idx_logs_project_timestamp` and heap-fetches every matching row. At ~700k
logs per week that exceeds the gateway's 10s gRPC deadline and the sidebar
never renders - the same failure mode revision 018 fixed for the country
breakdown.

A covering index on those five columns would fix the read, but every index
on `logs` is paid for on the ingestion hot path, and an index-only scan
still degrades on freshly-ingested pages the visibility map hasn't caught
up on. Pre-aggregating instead keeps the write path untouched and turns a
7-day facet query from ~700k rows into ~168 buckets worth of grouped rows.

One row per (project, hour, level, log_type, status_class, environment,
client_channel). Nullable source columns collapse to '' rather than NULL so
the primary key can carry them - ON CONFLICT never matches on NULL. The
primary key's leading (project_id, bucket) prefix serves the read, so no
secondary index is created.
"""

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS log_facets_1h (
            project_id     BIGINT      NOT NULL,
            bucket         TIMESTAMPTZ NOT NULL,
            level          VARCHAR(20) NOT NULL,
            log_type       VARCHAR(30) NOT NULL,
            status_class   VARCHAR(3)  NOT NULL DEFAULT '',
            environment    VARCHAR(20) NOT NULL DEFAULT '',
            client_channel VARCHAR(20) NOT NULL DEFAULT '',
            count          BIGINT      NOT NULL DEFAULT 0,
            PRIMARY KEY (project_id, bucket, level, log_type, status_class, environment, client_channel)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS log_facets_1h")
