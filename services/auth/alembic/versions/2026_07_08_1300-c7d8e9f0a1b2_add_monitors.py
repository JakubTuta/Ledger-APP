"""add monitors and monitor_checks tables

Revision ID: c7d8e9f0a1b2
Revises: a3b4c5d6e7f8
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa


revision = 'c7d8e9f0a1b2'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'monitors',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column(
            'project_id',
            sa.BigInteger(),
            sa.ForeignKey('projects.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('kind', sa.VARCHAR(length=20), nullable=False),
        sa.Column('name', sa.VARCHAR(length=255), nullable=False),
        sa.Column('target_url', sa.VARCHAR(length=2048), nullable=True),
        sa.Column('token', sa.VARCHAR(length=64), nullable=True),
        sa.Column('interval_s', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('timeout_s', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('expected_status', sa.Integer(), nullable=False, server_default='200'),
        sa.Column('grace_s', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('state', sa.VARCHAR(length=10), nullable=False, server_default='unknown'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
    )

    op.create_index('idx_monitors_project_id', 'monitors', ['project_id'])
    op.create_index(
        'idx_monitors_token',
        'monitors',
        ['token'],
        unique=True,
        postgresql_where=sa.text('token IS NOT NULL'),
    )
    op.create_index(
        'idx_monitors_enabled',
        'monitors',
        ['kind', 'enabled'],
        postgresql_where=sa.text('enabled = TRUE'),
    )

    op.create_check_constraint(
        'check_monitor_kind',
        'monitors',
        "kind IN ('http', 'heartbeat')",
    )
    op.create_check_constraint(
        'check_monitor_state',
        'monitors',
        "state IN ('unknown', 'up', 'down')",
    )

    op.create_table(
        'monitor_checks',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            'monitor_id',
            sa.BigInteger(),
            sa.ForeignKey('monitors.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'checked_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column('ok', sa.Boolean(), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
    )

    op.create_index(
        'idx_monitor_checks_monitor_checked',
        'monitor_checks',
        ['monitor_id', 'checked_at'],
    )
    op.create_index(
        'idx_monitor_checks_checked_at',
        'monitor_checks',
        ['checked_at'],
    )


def downgrade() -> None:
    op.drop_index('idx_monitor_checks_checked_at', table_name='monitor_checks')
    op.drop_index('idx_monitor_checks_monitor_checked', table_name='monitor_checks')
    op.drop_table('monitor_checks')

    op.drop_constraint('check_monitor_state', 'monitors', type_='check')
    op.drop_constraint('check_monitor_kind', 'monitors', type_='check')
    op.drop_index('idx_monitors_enabled', table_name='monitors')
    op.drop_index('idx_monitors_token', table_name='monitors')
    op.drop_index('idx_monitors_project_id', table_name='monitors')
    op.drop_table('monitors')
