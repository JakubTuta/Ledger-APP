"""rebuild log_volume_1h / log_volume_1d from their sources

Revision ID: 023
Revises: 022
Create Date: 2026-10-03 10:00:00.000000

Both rollup jobs resumed from their watermark and, because ON CONFLICT replaces
a bucket outright, rewrote every bucket they touched with only the slice after
the watermark. A day or hour that was still open when a run started kept just
its tail, so every stored day is a fraction of what was ingested - the usage
history chart and anything else reading these tables were short.

The jobs now start at the top of the watermark's bucket, which stops new damage.
This revision repairs what is already stored: dropping the two watermarks makes
the next run recompute 35 days from log_volume_5m (retained 90 days) and then
log_volume_1d from that, overwriting each bucket with its true sum. Both
upserts are idempotent, so a re-run is harmless. Days older than 35 days stay
as they were; nothing upstream is left to rebuild them from.

The downgrade does nothing: a watermark is derived state, and the jobs recreate
it on their next run.
"""
from alembic import op

revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM rollup_job_state "
        "WHERE job_name IN ('log_volume_1h_rollup', 'log_volume_1d_rollup')"
    )


def downgrade() -> None:
    pass
