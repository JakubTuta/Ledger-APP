"""widen idx_alert_events_rule_id to (rule_id, id DESC)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-29 14:00:00.000000

Both alert-evaluator reads of this table are "newest event for this rule":

    _get_snoozed_until()      ORDER BY id DESC LIMIT 1
    _firing_episode_start()   MIN(fired_at) ... id > (SELECT MAX(id) ...)

With rule_id alone, each runs every minute per firing rule and has to read and
sort that rule's whole event history to answer. Carrying `id` in the index
turns both into a bounded scan of the index tail.
"""

from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_alert_events_rule_id")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_alert_events_rule_id "
        "ON alert_events (rule_id, id DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_alert_events_rule_id")
    op.execute("CREATE INDEX IF NOT EXISTS idx_alert_events_rule_id ON alert_events (rule_id)")
