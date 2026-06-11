"""add_category_tag_grouping

Revision ID: 7f8e9d0c1b2a
Revises: 40ca71c79446
Create Date: 2026-06-10 16:30:00.000000

Adds tag-based output category grouping settings to accounts and playlist_configs.
Replaces legacy_sqlite migration 2026_06_07_add_category_tag_grouping.
"""

import sqlalchemy as sa
from alembic import op

from alembic_migrations.migration_helpers import add_column_if_missing, column_exists

revision = "7f8e9d0c1b2a"
down_revision = "40ca71c79446"
branch_labels = None
depends_on = None


def upgrade():
    add_column_if_missing(
        "accounts",
        "category_tag_grouping",
        sa.Column("category_tag_grouping", sa.Text(), nullable=True),
    )

    if not column_exists("playlist_configs", "category_tag_grouping"):
        with op.batch_alter_table("playlist_configs", schema=None) as batch_op:
            batch_op.add_column(sa.Column("category_tag_grouping", sa.Text(), nullable=True))


def downgrade():
    if column_exists("playlist_configs", "category_tag_grouping"):
        with op.batch_alter_table("playlist_configs", schema=None) as batch_op:
            batch_op.drop_column("category_tag_grouping")

    if column_exists("accounts", "category_tag_grouping"):
        with op.batch_alter_table("accounts", schema=None) as batch_op:
            batch_op.drop_column("category_tag_grouping")
