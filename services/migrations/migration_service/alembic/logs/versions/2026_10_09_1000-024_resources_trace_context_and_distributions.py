"""store OTLP resources once; trace context on logs; exp histograms, summaries, exemplars

Revision ID: 024
Revises: 023
Create Date: 2026-10-09 10:00:00.000000

Every log row carried its full OTLP resource in `attributes` and every metric
point carried it in `tags` (measured: ~300 bytes for the Ledger SDK's resource,
~2 KB with OTel's process detector). A new `resources` table holds each distinct
resource once per project; rows reference it by `resource_hash`, and the query
service merges it back in on read. Metric points keep only the identifying
resource keys (service, instance, environment, host/k8s placement) in `tags`,
which also stops descriptive attributes from bloating the GIN index.

`service_name`, `trace_id` and `span_id` on logs used to live only inside the
JSONB. As columns they serve the service filter and trace -> logs correlation
without detoasting every row in the window. No index is added for either: both
reads are time-bounded scans through idx_logs_project_timestamp, and these
tables are on the ingestion hot path.

`exp_histogram`, `quantiles` and `exemplars` store OTLP exponential histograms,
summaries and exemplars, which the gateway previously rejected.

Every new column is nullable with no default, so on the partitioned tables
these are catalog-only ADD COLUMNs. Existing rows are not rewritten: they keep
their merged attributes and NULL in the new columns, which readers handle.

`service_edges_1h` is the hourly rollup behind long-window service maps: the
graph is a self-join of every span in the window, measured at ~3-6 s for 24 h of
a busy project (430k spans) on the production database's 0.5 CPU. The analytics
job keeps it current every 10 minutes; windows of a few hours stay on raw spans.
"""
from alembic import op

revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS resources (
            project_id    BIGINT NOT NULL,
            resource_hash BIGINT NOT NULL,
            attributes    JSONB NOT NULL,
            first_seen    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (project_id, resource_hash)
        )
        """
    )
    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS resource_hash BIGINT")
    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS service_name VARCHAR(255)")
    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS trace_id CHAR(32)")
    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS span_id CHAR(16)")
    op.execute("ALTER TABLE spans ADD COLUMN IF NOT EXISTS resource_hash BIGINT")
    op.execute("ALTER TABLE metric_points ADD COLUMN IF NOT EXISTS resource_hash BIGINT")
    op.execute("ALTER TABLE metric_points ADD COLUMN IF NOT EXISTS exp_histogram JSONB")
    op.execute("ALTER TABLE metric_points ADD COLUMN IF NOT EXISTS quantiles JSONB")
    op.execute("ALTER TABLE metric_points ADD COLUMN IF NOT EXISTS exemplars JSONB")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS service_edges_1h (
            project_id      BIGINT NOT NULL,
            bucket          TIMESTAMPTZ NOT NULL,
            caller          TEXT NOT NULL,
            callee          TEXT NOT NULL,
            calls           BIGINT NOT NULL,
            errors          BIGINT NOT NULL,
            duration_ns_sum BIGINT NOT NULL,
            p95_ns          BIGINT,
            PRIMARY KEY (project_id, bucket, caller, callee)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS service_edges_1h")
    op.execute("ALTER TABLE metric_points DROP COLUMN IF EXISTS exemplars")
    op.execute("ALTER TABLE metric_points DROP COLUMN IF EXISTS quantiles")
    op.execute("ALTER TABLE metric_points DROP COLUMN IF EXISTS exp_histogram")
    op.execute("ALTER TABLE metric_points DROP COLUMN IF EXISTS resource_hash")
    op.execute("ALTER TABLE spans DROP COLUMN IF EXISTS resource_hash")
    op.execute("ALTER TABLE logs DROP COLUMN IF EXISTS span_id")
    op.execute("ALTER TABLE logs DROP COLUMN IF EXISTS trace_id")
    op.execute("ALTER TABLE logs DROP COLUMN IF EXISTS service_name")
    op.execute("ALTER TABLE logs DROP COLUMN IF EXISTS resource_hash")
    op.execute("DROP TABLE IF EXISTS resources")
