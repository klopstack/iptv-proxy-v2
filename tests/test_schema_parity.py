"""Schema parity: migrations + create_all produce expected tables and indexes."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from run_migrations import run_migrations, sqlite_connect
from tests.schema_parity_helpers import FK_ONDELETE_SPOT_CHECKS, REQUIRED_CHANNEL_INDEXES


def _channel_indexes(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='channels'").fetchall()
    }


def _fk_ondelete(conn: sqlite3.Connection, table: str, column: str) -> str | None:
    """Return ON DELETE action for a column from PRAGMA foreign_key_list."""
    for row in conn.execute(f"PRAGMA foreign_key_list({table})").fetchall():
        if row[3] == column:
            return row[6] or "NO ACTION"
    return None


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

    def test_channel_ppv_queue_index_after_migrations(self, migrated_db):
        conn = sqlite3.connect(migrated_db)
        indexes = _channel_indexes(conn)
        assert REQUIRED_CHANNEL_INDEXES <= indexes
        conn.close()

    def test_channel_ppv_queue_index_on_create_all_fixture(self, app):
        """Default pytest path uses create_all only — index must come from the model."""
        with app.app_context():
            from models import db as _db

            row = _db.session.execute(
                _db.text(
                    "SELECT name FROM sqlite_master WHERE type='index' "
                    "AND tbl_name='channels' AND name='ix_channel_ppv_queue'"
                )
            ).fetchone()
            assert row is not None, "ix_channel_ppv_queue missing from create_all test DB"

    def test_fk_ondelete_spot_checks(self, migrated_db):
        conn = sqlite_connect(migrated_db)
        try:
            for table, column, ref_table, ref_col, expected in FK_ONDELETE_SPOT_CHECKS:
                actual = _fk_ondelete(conn, table, column)
                assert (
                    actual == expected
                ), f"{table}.{column} -> {ref_table}.{ref_col}: expected ON DELETE {expected}, got {actual}"
        finally:
            conn.close()

    def test_foreign_keys_enabled_on_app_connection(self, app):
        """App engine listener enables FK enforcement (production path)."""
        with app.app_context():
            from models import db as _db

            row = _db.session.execute(_db.text("PRAGMA foreign_keys")).fetchone()
            assert row[0] == 1
