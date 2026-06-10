"""Shared helpers for idempotent Alembic upgrades during legacy transition."""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


def column_exists(table_name: str, column_name: str) -> bool:
    """Return True when ``column_name`` is already present on ``table_name``."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}
