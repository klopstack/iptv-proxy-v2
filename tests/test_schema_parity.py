"""Schema parity: Alembic upgrade produces expected tables and indexes."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from tests.alembic_test_helpers import alembic_upgrade_sqlite
from tests.schema_parity_helpers import FK_ONDELETE_SPOT_CHECKS, REQUIRED_CHANNEL_INDEXES


def _sqlite_connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


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
    """Database built like production: Alembic upgrade head."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    alembic_upgrade_sqlite(path)

    yield path

    for suffix in ("", "-wal", "-shm"):
        p = Path(f"{path}{suffix}")
        if p.exists():
            p.unlink()


@pytest.mark.migrations
@pytest.mark.sqlite_only
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
            "alembic_version",
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

    def test_post_baseline_account_columns(self, migrated_db):
        conn = sqlite3.connect(migrated_db)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(accounts)").fetchall()}
        for name in ("category_tag_grouping", "ppv_show_replay", "ppv_show_historical"):
            assert name in columns, f"missing accounts.{name}"
        conn.close()

    def test_post_baseline_playlist_config_columns(self, migrated_db):
        conn = sqlite3.connect(migrated_db)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(playlist_configs)").fetchall()}
        assert "category_tag_grouping" in columns
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
        conn = _sqlite_connect(migrated_db)
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
