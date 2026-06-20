"""add_xtream_vod_passthrough

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-20 12:00:00.000000

Adds optional upstream VOD passthrough flag to xtream_credentials.
"""

import sqlalchemy as sa
from alembic import op

from alembic_migrations.migration_helpers import add_column_if_missing, column_exists

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    add_column_if_missing(
        "xtream_credentials",
        "vod_passthrough",
        sa.Column("vod_passthrough", sa.Boolean(), nullable=True, server_default=sa.false()),
    )


def downgrade():
    if column_exists("xtream_credentials", "vod_passthrough"):
        with op.batch_alter_table("xtream_credentials", schema=None) as batch_op:
            batch_op.drop_column("vod_passthrough")
