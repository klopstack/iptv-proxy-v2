"""add_ppv_group_visibility_toggles

Revision ID: 6e7d8c9b0a1f
Revises: 7f8e9d0c1b2a
Create Date: 2026-06-10 16:30:01.000000

Adds per-group Replay/Historical visibility toggles for group_live_replay mode.
Replaces legacy_sqlite migration 2026_06_10_add_ppv_group_visibility_toggles.
"""

import sqlalchemy as sa
from alembic import op

from alembic_migrations.migration_helpers import column_exists

revision = "6e7d8c9b0a1f"
down_revision = "7f8e9d0c1b2a"
branch_labels = None
depends_on = None


def upgrade():
    if not column_exists("accounts", "ppv_show_replay"):
        with op.batch_alter_table("accounts", schema=None) as batch_op:
            batch_op.add_column(sa.Column("ppv_show_replay", sa.Boolean(), nullable=False, server_default=sa.true()))

    if not column_exists("accounts", "ppv_show_historical"):
        with op.batch_alter_table("accounts", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("ppv_show_historical", sa.Boolean(), nullable=False, server_default=sa.true())
            )


def downgrade():
    if column_exists("accounts", "ppv_show_historical"):
        with op.batch_alter_table("accounts", schema=None) as batch_op:
            batch_op.drop_column("ppv_show_historical")

    if column_exists("accounts", "ppv_show_replay"):
        with op.batch_alter_table("accounts", schema=None) as batch_op:
            batch_op.drop_column("ppv_show_replay")
