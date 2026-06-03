"""Shared expectations for schema parity tests (indexes and FK ondelete)."""

# (table, column, ref_table, ref_column, expected on_delete from migration DDL)
FK_ONDELETE_SPOT_CHECKS = (
    ("active_streams", "credential_id", "credentials", "id", "CASCADE"),
    ("channels", "category_id", "categories", "id", "SET NULL"),
    ("channels", "account_id", "accounts", "id", "CASCADE"),
    ("channel_tags", "account_id", "accounts", "id", "CASCADE"),
    ("channel_tags", "tag_id", "tags", "id", "CASCADE"),
    ("credentials", "account_id", "accounts", "id", "CASCADE"),
)

REQUIRED_CHANNEL_INDEXES = frozenset({"ix_channel_ppv_queue"})
