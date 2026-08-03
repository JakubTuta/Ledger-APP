"""add client_channel/client_country columns to logs, and the ip_country_ranges lookup table

Revision ID: 017
Revises: 016
Create Date: 2026-08-03 10:00:00.000000

Two new typed columns on `logs`, populated going forward only - there is no
backfill UPDATE here, because historic rows never carried caller data to
promote (the SDK/gateway support for it ships in this same release). See
migration 008 for the promote-with-backfill pattern this deliberately does
NOT follow.

`ip_country_ranges` is a small standalone (non-partitioned) table: the
in-memory bisect table the ingestion worker builds from it is what's on the
hot path, this table is just the source of truth the weekly RIR refresh job
writes to and the worker reloads from - occasional full-table reads, no
per-request access.
"""

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE logs
            ADD COLUMN IF NOT EXISTS client_channel VARCHAR(20),
            ADD COLUMN IF NOT EXISTS client_country CHAR(2)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS ip_country_ranges (
            id BIGSERIAL PRIMARY KEY,
            family SMALLINT NOT NULL,
            range_start BIGINT NOT NULL,
            range_end BIGINT NOT NULL,
            country_code CHAR(2) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT check_ip_country_family CHECK (family IN (4, 6))
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ip_country_ranges_family_start
            ON ip_country_ranges (family, range_start)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_ip_country_ranges_family_start")
    op.execute("DROP TABLE IF EXISTS ip_country_ranges")
    op.execute("""
        ALTER TABLE logs
            DROP COLUMN IF EXISTS client_channel,
            DROP COLUMN IF EXISTS client_country
    """)
