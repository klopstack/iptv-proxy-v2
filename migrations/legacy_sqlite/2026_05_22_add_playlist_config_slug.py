"""Add slug column to playlist_configs for indexed URL lookup.

Migration: 2026_05_22_add_playlist_config_slug
Created: 2026-05-22
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    import re

    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-") or "playlist"


def _make_unique_slug(name: str, used: set[str]) -> str:
    base = _slugify(name)
    candidate = base
    counter = 2
    while candidate in used:
        candidate = f"{base}-{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def migrate(db_path):
    """Add slug column, backfill from names, and enforce uniqueness."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(playlist_configs)")
        columns = {row[1] for row in cursor.fetchall()}
        if "slug" in columns:
            return True, "playlist_configs.slug already exists, skipping"

        logger.info("Adding slug column to playlist_configs")
        cursor.execute("ALTER TABLE playlist_configs ADD COLUMN slug VARCHAR(220)")

        cursor.execute("SELECT id, name FROM playlist_configs ORDER BY id")
        rows = cursor.fetchall()
        used_slugs: set[str] = set()
        for config_id, name in rows:
            slug = _make_unique_slug(name or f"config-{config_id}", used_slugs)
            cursor.execute("UPDATE playlist_configs SET slug = ? WHERE id = ?", (slug, config_id))

        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_playlist_configs_slug ON playlist_configs (slug)")

        conn.commit()
        return True, f"Added slug column and backfilled {len(rows)} playlist config(s)"
    except Exception as e:
        conn.rollback()
        logger.error(f"Error adding playlist_configs.slug: {e}")
        return False, f"Error: {str(e)}"
    finally:
        conn.close()


if __name__ == "__main__":
    import os
    import sys

    db_path = os.getenv("DATABASE_URL", "sqlite:///data/iptv_proxy.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")

    success, message = migrate(db_path)
    if success:
        print(f"✓ {message}")
        sys.exit(0)
    print(f"✗ {message}")
    sys.exit(1)
