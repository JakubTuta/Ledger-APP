"""drop accounts.notification_preferences

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-03 10:00:00.000000

The account-level on/off + per-project level filter behind the Settings >
Notifications tab is gone. It sat in front of every in-app alert notification
the gateway streamed, so a user who had ever touched it could set up an alert
that fired and never reached them. Delivery is now controlled only by the alert
rule itself and the per-rule `notification_preferences` mute table, neither of
which this column ever fed.

The downgrade restores the column with its original server default; the stored
choices are not recoverable, which is intended - they only ever suppressed
delivery.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("accounts", "notification_preferences")


def downgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column(
            "notification_preferences",
            postgresql.JSONB,
            nullable=False,
            server_default='{"enabled": true, "projects": {}}',
        ),
    )
