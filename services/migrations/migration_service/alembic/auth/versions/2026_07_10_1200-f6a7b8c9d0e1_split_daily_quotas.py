"""split daily_quota into logs/spans/metrics quotas; add span/metric usage counters

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa


revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('check_daily_quota', 'projects', type_='check')
    op.alter_column('projects', 'daily_quota', new_column_name='logs_daily_quota')

    op.add_column(
        'projects',
        sa.Column('spans_daily_quota', sa.BigInteger(), nullable=False, server_default='300000'),
    )
    op.add_column(
        'projects',
        sa.Column('metrics_daily_quota', sa.BigInteger(), nullable=False, server_default='100000'),
    )

    op.create_check_constraint('check_logs_daily_quota', 'projects', 'logs_daily_quota >= 1000')
    op.create_check_constraint('check_spans_daily_quota', 'projects', 'spans_daily_quota >= 1000')
    op.create_check_constraint('check_metrics_daily_quota', 'projects', 'metrics_daily_quota >= 1000')

    op.add_column(
        'daily_usage',
        sa.Column('spans_ingested', sa.BigInteger(), nullable=False, server_default='0'),
    )
    op.add_column(
        'daily_usage',
        sa.Column('metric_points_ingested', sa.BigInteger(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('daily_usage', 'metric_points_ingested')
    op.drop_column('daily_usage', 'spans_ingested')

    op.drop_constraint('check_metrics_daily_quota', 'projects', type_='check')
    op.drop_constraint('check_spans_daily_quota', 'projects', type_='check')
    op.drop_constraint('check_logs_daily_quota', 'projects', type_='check')

    op.drop_column('projects', 'metrics_daily_quota')
    op.drop_column('projects', 'spans_daily_quota')

    op.alter_column('projects', 'logs_daily_quota', new_column_name='daily_quota')
    op.create_check_constraint('check_daily_quota', 'projects', 'daily_quota >= 1000')
