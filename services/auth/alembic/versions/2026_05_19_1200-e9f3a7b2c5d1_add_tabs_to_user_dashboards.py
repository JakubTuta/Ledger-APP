"""add tabs and active_tab_id to user_dashboards

Revision ID: e9f3a7b2c5d1
Revises: d8e2f0a5c4b3
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = 'e9f3a7b2c5d1'
down_revision = 'd8e2f0a5c4b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'user_dashboards',
        sa.Column('tabs', JSONB, nullable=False, server_default='[]'),
    )
    op.add_column(
        'user_dashboards',
        sa.Column('active_tab_id', sa.String, nullable=True),
    )


def downgrade() -> None:
    op.drop_column('user_dashboards', 'active_tab_id')
    op.drop_column('user_dashboards', 'tabs')
