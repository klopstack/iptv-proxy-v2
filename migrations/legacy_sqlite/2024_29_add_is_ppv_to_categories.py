"""Add is_ppv column to categories table for efficient PPV detection"""
import logging
import re
import sqlite3

logger = logging.getLogger(__name__)

# PPV category detection patterns (same as in epg_service.py)
PPV_CATEGORY_PATTERNS = [
    r"\bPPV\b",  # PPV as a word
    r"PAY[\s-]?PER[\s-]?VIEW",  # Pay-per-view variations
]


def is_ppv_category(category_name: str) -> bool:
    """Check if a category name indicates PPV content."""
    if not category_name:
        return False

    name_upper = category_name.upper()
    for pattern in PPV_CATEGORY_PATTERNS:
        if re.search(pattern, name_upper, re.IGNORECASE):
            return True
    return False


def migrate(db_path):
    """Add is_ppv column to categories table and populate it."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(categories)")
        columns = [row[1] for row in cursor.fetchall()]

        if "is_ppv" in columns:
            logger.info("Column is_ppv already exists in categories table")
            return True, "Column is_ppv already exists, skipping"

        # Add the is_ppv column
        logger.info("Adding is_ppv column to categories table")
        cursor.execute("ALTER TABLE categories ADD COLUMN is_ppv BOOLEAN DEFAULT 0")

        # Update existing categories based on category_name
        cursor.execute("SELECT id, category_name FROM categories")
        categories = cursor.fetchall()

        updated_count = 0
        for category_id, category_name in categories:
            if is_ppv_category(category_name):
                cursor.execute("UPDATE categories SET is_ppv = 1 WHERE id = ?", (category_id,))
                updated_count += 1

        # Create index for the is_ppv column
        try:
            cursor.execute("CREATE INDEX idx_category_ppv ON categories(is_ppv)")
        except sqlite3.OperationalError:
            # Index might already exist
            pass

        conn.commit()
        logger.info(f"Added is_ppv column and marked {updated_count} categories as PPV")
        return True, f"Added is_ppv column to categories, marked {updated_count} categories as PPV"

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        return False, f"Migration failed: {str(e)}"
    finally:
        conn.close()
