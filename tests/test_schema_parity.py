"""Schema parity: migrations + create_all produce expected tables and indexes."""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from run_migrations import run_migrations


@pytest.fixture
def migrated_db():
    """Database built like production: create_all then tracked migrations."""
    from sqlalchemy import create_engine

    from models import db as _db

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    engine = create_engine(f"sqlite:///{path}")
    _db.metadata.create_all(engine)
    engine.dispose()

    assert run_migrations(path) is True
    yield path

    for suffix in ("", "-wal", "-shm"):
        p = Path(f"{path}{suffix}")
        if p.exists():
            p.unlink()


@pytest.mark.migrations
class TestSchemaParity:
    def test_critical_tables_exist(self, migrated_db):
        conn = sqlite3.connect(migrated_db)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        for name in (
            "accounts",
            "channels",
            "channel_tags",
            "playlist_configs",
            "epg_programs",
            "schema_migrations",
            "sync_metadata",
        ):
            assert name in tables, f"missing table {name}"
        conn.close()

    def test_playlist_config_slug_index(self, migrated_db):
        conn = sqlite3.connect(migrated_db)
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='playlist_configs'"
            ).fetchall()
        }
        assert "idx_playlist_configs_slug" in indexes or "ix_playlist_configs_slug" in indexes
        conn.close()

    def test_channel_tags_account_stream_index(self, migrated_db):
        conn = sqlite3.connect(migrated_db)
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='channel_tags'"
            ).fetchall()
        }
        assert "idx_channel_tags_account_stream" in indexes
        conn.close()

    def test_accounts_sync_started_at_column(self, migrated_db):
        conn = sqlite3.connect(migrated_db)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(accounts)").fetchall()}
        assert "sync_started_at" in columns
        conn.close()

    def test_foreign_keys_enabled_on_app_connection(self, app):
        """App engine listener enables FK enforcement (production path)."""
        with app.app_context():
            from models import db as _db

            row = _db.session.execute(_db.text("PRAGMA foreign_keys")).fetchone()
            assert row[0] == 1
