"""Tests for migration runner and schema tracking."""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from run_migrations import ensure_schema_migrations_table, get_applied_migrations, run_migrations


@pytest.fixture
def temp_db():
    """Temporary SQLite database initialized via create_all (matches production boot)."""
    from sqlalchemy import create_engine

    from models import db as _db

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    engine = create_engine(f"sqlite:///{path}")
    _db.metadata.create_all(engine)
    engine.dispose()

    yield path

    for suffix in ("", "-wal", "-shm"):
        p = Path(f"{path}{suffix}")
        if p.exists():
            p.unlink()


class TestMigrationRunner:
    def test_schema_migrations_table_created(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            ensure_schema_migrations_table(path)
            conn = sqlite3.connect(path)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            )
            assert cursor.fetchone() is not None
            conn.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_migration_chain_after_create_all(self, temp_db):
        os.environ["DATABASE_URL"] = f"sqlite:///{temp_db}"
        try:
            assert run_migrations(temp_db) is True
        finally:
            os.environ.pop("DATABASE_URL", None)

        conn = sqlite3.connect(temp_db)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "schema_migrations" in tables
        assert "accounts" in tables
        assert "channels" in tables
        assert "playlist_configs" in tables
        assert "epg_programs" in tables

        cursor = conn.execute("PRAGMA table_info(playlist_configs)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "slug" in columns

        cursor = conn.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 0  # raw sqlite3 connection; app enables via listener
        conn.close()

        applied = get_applied_migrations(temp_db)
        assert len(applied) >= 40

    def test_second_run_skips_tracked_migrations(self, temp_db):
        os.environ["DATABASE_URL"] = f"sqlite:///{temp_db}"
        try:
            assert run_migrations(temp_db) is True
            applied_first = len(get_applied_migrations(temp_db))
            assert run_migrations(temp_db) is True
            applied_second = len(get_applied_migrations(temp_db))
        finally:
            os.environ.pop("DATABASE_URL", None)

        assert applied_first == applied_second
        assert applied_first > 0
