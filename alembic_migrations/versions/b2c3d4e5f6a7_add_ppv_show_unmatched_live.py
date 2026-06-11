"""add_ppv_show_unmatched_live

Revision ID: b2c3d4e5f6a7
Revises: 6e7d8c9b0a1f
Create Date: 2026-06-10 18:00:00.000000

Adds per-group Unmatched Live visibility toggle for group_live_replay mode.
Replaces legacy_sqlite migration 2026_06_10_add_ppv_show_unmatched_live.
"""

import sqlalchemy as sa
from alembic import op

from alembic_migrations.migration_helpers import add_column_if_missing, column_exists

revision = "b2c3d4e5f6a7"
down_revision = "6e7d8c9b0a1f"
branch_labels = None
depends_on = None


def upgrade():
    add_column_if_missing(
        "accounts",
        "ppv_show_unmatched_live",
        sa.Column("ppv_show_unmatched_live", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade():
    if column_exists("accounts", "ppv_show_unmatched_live"):
        with op.batch_alter_table("accounts", schema=None) as batch_op:
            batch_op.drop_column("ppv_show_unmatched_live")
