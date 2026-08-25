"""record OTLP aggregation temporality on metric points

Revision ID: 022
Revises: 021
Create Date: 2026-08-25 22:00:00.000000

The OTLP translator was discarding `aggregation_temporality`, so a counter
exported cumulatively (the opentelemetry-python default) was indistinguishable
from a delta counter once stored. The two need opposite treatment on read - a
cumulative series is a running total that must be differenced reset-aware
before it means anything, a delta series is already per-interval - and with the
field gone the query layer had no way to pick. Persisting it is the smallest
thing that makes both correct.

Nullable with no backfill on purpose: rows written before this revision have an
unknown temporality, and NULL says exactly that. `metric_points` is partitioned
and hot on the write path, so this is a bare catalog-only ADD COLUMN (Postgres
11+ fast default) with no index - temporality is read alongside a
(project_id, name) lookup that idx_metric_points_lookup already serves, never
filtered on by itself.
"""
from alembic import op

revision = '022'
down_revision = '021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE metric_points ADD COLUMN IF NOT EXISTS temporality SMALLINT")
    op.execute("ALTER TABLE metric_points_1h ADD COLUMN IF NOT EXISTS temporality SMALLINT")


def downgrade() -> None:
    op.execute("ALTER TABLE metric_points_1h DROP COLUMN IF EXISTS temporality")
    op.execute("ALTER TABLE metric_points DROP COLUMN IF EXISTS temporality")
