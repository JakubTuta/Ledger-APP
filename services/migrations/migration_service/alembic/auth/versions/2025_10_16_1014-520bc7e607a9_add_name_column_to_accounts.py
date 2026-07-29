"""add_name_column_to_accounts

Revision ID: 520bc7e607a9
Revises: a2dd1ac4850d
Create Date: 2025-10-16 10:14:46.719826

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '520bc7e607a9'
down_revision = 'a2dd1ac4850d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('name', sa.VARCHAR(length=255), nullable=False, server_default=''))
    op.alter_column('accounts', 'name', server_default=None)


def downgrade() -> None:
    op.drop_column('accounts', 'name')