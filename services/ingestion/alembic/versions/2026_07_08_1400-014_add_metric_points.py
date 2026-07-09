"""add metric_points table (partitioned) and metric_points_1h rollup

Revision ID: 014
Revises: 013
Create Date: 2026-07-08 14:00:00.000000

Design note: migration 007 introduced a `custom_metrics` domain (dropped in 009)
that used a raw `tags JSONB` column as part of the primary key on a table
PARTITION BY RANGE(ts). JSONB-in-composite-PK is fragile for partitioned
uniqueness (index bloat, no stable ordering) and no cardinality-limit
enforcement was ever wired up. This migration normalizes tags into a
fixed-width `tags_hash CHAR(16)` (blake2b digest of the canonicalized,
sorted-keys JSON tag map) used in the primary key / partition locality
instead, while keeping a `tags JSONB` column (GIN-indexed) alongside for
display and ad-hoc filtering.
"""
from alembic import op

revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
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
        ) PARTITION BY RANGE (ts)
    """)

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_metric_points_lookup "
        "ON metric_points (project_id, name, ts DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_metric_points_tags "
        "ON metric_points USING GIN (tags)"
    )

    op.execute("""
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
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_metric_points_1h_lookup "
        "ON metric_points_1h (project_id, name, bucket DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_metric_points_1h_lookup")
    op.execute("DROP TABLE IF EXISTS metric_points_1h")

    op.execute("DROP INDEX IF EXISTS idx_metric_points_tags")
    op.execute("DROP INDEX IF EXISTS idx_metric_points_lookup")
    op.execute("DROP TABLE IF EXISTS metric_points")
