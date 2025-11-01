"""add_user_dashboards_table

Revision ID: ca45da6bfae9
Revises: 520bc7e607a9
Create Date: 2025-10-30 14:35:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'ca45da6bfae9'
down_revision = '520bc7e607a9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('user_dashboards',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('panels', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_index('idx_user_dashboards_panels', 'user_dashboards', ['panels'], unique=False, postgresql_using='gin')
    op.create_index('idx_user_dashboards_user_id', 'user_dashboards', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_dashboards_id'), 'user_dashboards', ['id'], unique=False)
    op.create_index(op.f('ix_user_dashboards_user_id'), 'user_dashboards', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_dashboards_user_id'), table_name='user_dashboards')
    op.drop_index(op.f('ix_user_dashboards_id'), table_name='user_dashboards')
    op.drop_index('idx_user_dashboards_user_id', table_name='user_dashboards')
    op.drop_index('idx_user_dashboards_panels', table_name='user_dashboards', postgresql_using='gin')
    op.drop_table('user_dashboards')
