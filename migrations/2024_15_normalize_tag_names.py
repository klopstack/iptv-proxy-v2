"""
Normalize tag names to uppercase for consistency

This migration updates existing Tag and TagRule records to use
consistent uppercase formatting for tag names.

Changes:
- Tags: "Network:FOX" -> "NETWORK:FOX", "DMA:Los Angeles" -> "DMA:LOS ANGELES"
- TagRules: Normalize tag_name field (except special tags like __CLEANUP__)
- Merges duplicate tags that differ only by case
"""

import os
import re
import sqlite3
import sys


def normalize_tag_name(tag_name):
    """
    Normalize a tag name for consistent storage.
    Mirrors the logic in TagService.normalize_tag_name()
    """
    if not tag_name:
        return tag_name

    # Skip special tags
    if tag_name.startswith("__") and tag_name.endswith("__"):
        return tag_name

    # Convert to uppercase
    normalized = tag_name.upper()

    # Handle Unicode superscript characters
    superscript_map = {
        "ᴿ": "R",
        "ᴬ": "A",
        "ᵂ": "W",
        "ᴹ": "M",
        "ᴰ": "D",
        "⁶": "6",
        "⁰": "0",
        "ᶠ": "F",
        "ᵖ": "P",
        "ˢ": "S",
        "ᴮ": "B",
        "ᴷ": "K",
        "ᴸ": "L",
        "ᴺ": "N",
        "ᵀ": "T",
        "ᵁ": "U",
        "ⁱ": "I",
        "ⁿ": "N",
    }
    for char, replacement in superscript_map.items():
        normalized = normalized.replace(char, replacement)

    # Remove special characters except alphanumeric, spaces, colons, and hyphens
    normalized = re.sub(r"[^\w\s:\-]", "", normalized)
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    normalized = normalized.strip("_")

    # Strip trailing numbers
    normalized = re.sub(r"_\d+$", "", normalized)

    return normalized if len(normalized) >= 2 else tag_name


def migrate(db_path):
    """
    Normalize tag names in the database.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        stats = {
            "tags_updated": 0,
            "tags_merged": 0,
            "tag_rules_updated": 0,
            "channel_tags_updated": 0,
        }

        # Step 1: Build mapping of old tag names to normalized names
        cursor.execute("SELECT id, name FROM tags")
        tags = cursor.fetchall()

        tag_name_to_ids = {}  # normalized_name -> list of (id, original_name)
        for tag_id, name in tags:
            normalized = normalize_tag_name(name)
            if normalized not in tag_name_to_ids:
                tag_name_to_ids[normalized] = []
            tag_name_to_ids[normalized].append((tag_id, name))

        # Step 2: Process all groups - first merge duplicates, then rename
        # We need to do merging first, then renaming, to avoid unique constraint issues

        # Phase 2a: Merge duplicates (groups with more than one tag)
        for normalized_name, id_list in tag_name_to_ids.items():
            if len(id_list) > 1:
                # Multiple tags with same normalized name - merge them
                # Keep the first one as canonical
                canonical_id = id_list[0][0]

                # Merge other tags into canonical
                for tag_id, _ in id_list[1:]:
                    # Update channel_tags to point to canonical tag
                    # Handle potential duplicates by using INSERT OR IGNORE pattern
                    cursor.execute(
                        """
                        UPDATE OR IGNORE channel_tags
                        SET tag_id = ?
                        WHERE tag_id = ?
                        """,
                        (canonical_id, tag_id),
                    )
                    updated = cursor.rowcount
                    stats["channel_tags_updated"] += updated

                    # Delete any remaining channel_tags that would be duplicates
                    cursor.execute("DELETE FROM channel_tags WHERE tag_id = ?", (tag_id,))

                    # Delete the duplicate tag
                    cursor.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
                    stats["tags_merged"] += 1

        # Phase 2b: Now rename all remaining tags to their normalized form
        # Since duplicates are already merged, each normalized name maps to exactly one tag
        for normalized_name, id_list in tag_name_to_ids.items():
            # After merging, we only care about the first (canonical) tag in each group
            tag_id, original_name = id_list[0]
            if original_name != normalized_name:
                cursor.execute("UPDATE tags SET name = ? WHERE id = ?", (normalized_name, tag_id))
                stats["tags_updated"] += 1

        # Step 3: Normalize TagRule.tag_name values
        cursor.execute("SELECT id, tag_name FROM tag_rules")
        tag_rules = cursor.fetchall()

        for rule_id, tag_name in tag_rules:
            if tag_name and not (tag_name.startswith("__") and tag_name.endswith("__")):
                normalized = normalize_tag_name(tag_name)
                if normalized and normalized != tag_name:
                    cursor.execute("UPDATE tag_rules SET tag_name = ? WHERE id = ?", (normalized, rule_id))
                    stats["tag_rules_updated"] += 1

        conn.commit()
        conn.close()

        message = (
            f"Normalized tag names: "
            f"{stats['tags_updated']} tags updated, "
            f"{stats['tags_merged']} duplicate tags merged, "
            f"{stats['tag_rules_updated']} tag rules updated, "
            f"{stats['channel_tags_updated']} channel-tag associations updated"
        )
        return True, message

    except Exception as e:
        return False, f"Failed to normalize tag names: {e}"


if __name__ == "__main__":
    # For standalone execution
    db_path = os.getenv("DATABASE_URL", "sqlite:///data/iptv_proxy.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")
    elif db_path.startswith("sqlite://"):
        db_path = db_path.replace("sqlite://", "")

    success, message = migrate(db_path)
    print(message)
    sys.exit(0 if success else 1)
