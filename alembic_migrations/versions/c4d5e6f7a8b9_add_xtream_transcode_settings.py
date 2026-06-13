"""add_xtream_transcode_settings

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-06-12 12:00:00.000000

Adds per-client transcode settings to xtream_credentials.
"""

import sqlalchemy as sa
from alembic import op

from alembic_migrations.migration_helpers import add_column_if_missing, column_exists

revision = "c4d5e6f7a8b9"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    add_column_if_missing(
        "xtream_credentials",
        "transcode_enabled",
        sa.Column("transcode_enabled", sa.Boolean(), nullable=True, server_default=sa.false()),
    )
    add_column_if_missing(
        "xtream_credentials",
        "transcode_max_height",
        sa.Column("transcode_max_height", sa.Integer(), nullable=True, server_default=sa.text("720")),
    )
    add_column_if_missing(
        "xtream_credentials",
        "transcode_max_bitrate_kbps",
        sa.Column("transcode_max_bitrate_kbps", sa.Integer(), nullable=True, server_default=sa.text("8000")),
    )
    add_column_if_missing(
        "xtream_credentials",
        "transcode_audio_channels",
        sa.Column("transcode_audio_channels", sa.Integer(), nullable=True, server_default=sa.text("2")),
    )
    add_column_if_missing(
        "xtream_credentials",
        "transcode_audio_bitrate_kbps",
        sa.Column("transcode_audio_bitrate_kbps", sa.Integer(), nullable=True, server_default=sa.text("128")),
    )


def downgrade():
    for col in (
        "transcode_audio_bitrate_kbps",
        "transcode_audio_channels",
        "transcode_max_bitrate_kbps",
        "transcode_max_height",
        "transcode_enabled",
    ):
        if column_exists("xtream_credentials", col):
            with op.batch_alter_table("xtream_credentials", schema=None) as batch_op:
                batch_op.drop_column(col)
