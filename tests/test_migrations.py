"""Tests for migration runner and schema tracking."""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from run_migrations import ensure_schema_migrations_table, get_applied_migrations, run_migrations, sqlite_connect


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
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
            assert cursor.fetchone() is not None
            conn.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_migration_chain_after_create_all(self, temp_db):
        original_db_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{temp_db}"
        try:
            assert run_migrations(temp_db) is True
        finally:
            if original_db_url is not None:
                os.environ["DATABASE_URL"] = original_db_url
            else:
                os.environ.pop("DATABASE_URL", None)

        conn = sqlite3.connect(temp_db)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "schema_migrations" in tables
        assert "accounts" in tables
        assert "channels" in tables
        assert "playlist_configs" in tables
        assert "epg_programs" in tables

        cursor = conn.execute("PRAGMA table_info(playlist_configs)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "slug" in columns

        conn.close()

        fk_conn = sqlite_connect(temp_db)
        try:
            assert fk_conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            violations = fk_conn.execute("PRAGMA foreign_key_check").fetchall()
            assert violations == [], f"foreign_key_check violations: {violations}"
        finally:
            fk_conn.close()

        applied = get_applied_migrations(temp_db)
        assert len(applied) >= 40

    def test_second_run_skips_tracked_migrations(self, temp_db):
        original_db_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{temp_db}"
        try:
            assert run_migrations(temp_db) is True
            applied_first = len(get_applied_migrations(temp_db))
            assert run_migrations(temp_db) is True
            applied_second = len(get_applied_migrations(temp_db))
        finally:
            if original_db_url is not None:
                os.environ["DATABASE_URL"] = original_db_url
            else:
                os.environ.pop("DATABASE_URL", None)

        assert applied_first == applied_second
        assert applied_first > 0
