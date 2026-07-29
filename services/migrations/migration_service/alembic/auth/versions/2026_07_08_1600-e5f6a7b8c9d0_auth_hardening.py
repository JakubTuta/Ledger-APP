"""auth hardening: email verification, TOTP 2FA

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'accounts',
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'accounts',
        sa.Column('email_verification_token', sa.CHAR(length=64), nullable=True),
    )
    op.add_column(
        'accounts',
        sa.Column('email_verification_sent_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'accounts',
        sa.Column('totp_secret', sa.VARCHAR(length=32), nullable=True),
    )
    op.add_column(
        'accounts',
        sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'accounts',
        sa.Column('totp_backup_codes', postgresql.JSONB(), nullable=True),
    )

    op.create_unique_constraint(
        'uq_accounts_email_verification_token',
        'accounts',
        ['email_verification_token'],
    )

    # Backfill: this project is dev/beta and email verification is a brand-new
    # requirement. Retroactively requiring every existing account to verify
    # would lock out the entire current user base on their next login-gated
    # action. Mark all pre-existing accounts as already verified; only
    # accounts created by NEW registrations from this point forward will
    # start out with email_verified = FALSE and go through the verify-email
    # flow.
    op.execute("UPDATE accounts SET email_verified = TRUE")


def downgrade() -> None:
    op.drop_constraint('uq_accounts_email_verification_token', 'accounts', type_='unique')
    op.drop_column('accounts', 'totp_backup_codes')
    op.drop_column('accounts', 'totp_enabled')
    op.drop_column('accounts', 'totp_secret')
    op.drop_column('accounts', 'email_verification_sent_at')
    op.drop_column('accounts', 'email_verification_token')
    op.drop_column('accounts', 'email_verified')
