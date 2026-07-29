"""add_available_routes_to_projects

Revision ID: f8c9d3e2a1b0
Revises: ca45da6bfae9
Create Date: 2025-11-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'f8c9d3e2a1b0'
down_revision = 'ca45da6bfae9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column(
            'available_routes',
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default='{}'
        )
    )


def downgrade() -> None:
    op.drop_column('projects', 'available_routes')
