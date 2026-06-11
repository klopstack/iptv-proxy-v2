"""Shared helpers for idempotent Alembic upgrades during legacy transition."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


def column_exists(table_name: str, column_name: str) -> bool:
    """Return True when ``column_name`` is already present on ``table_name``."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def add_column_if_missing(table_name: str, column_name: str, column: sa.Column) -> None:
    """Add ``column`` when absent.

    SQLite production databases often have child tables with FK references to
    ``accounts``. ``batch_alter_table`` recreates the parent via DROP TABLE, which
    fails under ``PRAGMA foreign_keys=ON``; native ``ALTER TABLE ... ADD COLUMN``
    avoids that.
    """
    if column_exists(table_name, column_name):
        return

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        parts = [column_name, _sqlite_type(column)]
        if column.server_default is not None:
            parts.append(f"DEFAULT {_sqlite_default(column.server_default)}")
        if not column.nullable:
            parts.append("NOT NULL")
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN {' '.join(parts)}")
        return

    op.add_column(table_name, column)


def _sqlite_type(column: sa.Column) -> str:
    type_ = column.type.compile(dialect=sa.dialects.sqlite.dialect())
    if isinstance(column.type, sa.Boolean):
        return "BOOLEAN"
    return type_


def _sqlite_default(server_default: sa.DefaultClause) -> str:
    arg = server_default.arg
    if arg is True or arg is sa.true() or getattr(arg, "value", None) is True:
        return "1"
    if arg is False or arg is sa.false() or getattr(arg, "value", None) is False:
        return "0"
    return str(arg.compile(dialect=sa.dialects.sqlite.dialect()))
