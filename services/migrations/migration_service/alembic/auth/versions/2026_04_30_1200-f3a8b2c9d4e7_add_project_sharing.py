"""add project sharing

Revision ID: f3a8b2c9d4e7
Revises: e5a7b2f9c3d1
Create Date: 2026-04-30 12:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "f3a8b2c9d4e7"
down_revision = "e5a7b2f9c3d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_members",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.VARCHAR(20), nullable=False, server_default="member"),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "account_id", name="uq_project_members"),
        sa.CheckConstraint(
            "role IN ('owner', 'member')", name="check_member_role"
        ),
    )
    op.create_index("idx_project_members_account_id", "project_members", ["account_id"])
    op.create_index("idx_project_members_project_id", "project_members", ["project_id"])

    op.create_table(
        "project_invite_codes",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("code_hash", sa.CHAR(64), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["used_by"], ["accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash", name="uq_invite_code_hash"),
    )
    op.create_index(
        "idx_invite_codes_code_hash",
        "project_invite_codes",
        ["code_hash"],
        postgresql_where=sa.text("used_at IS NULL"),
    )
    op.create_index(
        "idx_invite_codes_project_expires",
        "project_invite_codes",
        ["project_id", "expires_at"],
    )

    op.execute("""
        INSERT INTO project_members (project_id, account_id, role, joined_at)
        SELECT id, account_id, 'owner', created_at
        FROM projects
        ON CONFLICT (project_id, account_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("project_invite_codes")
    op.drop_table("project_members")
