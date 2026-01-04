#!/usr/bin/env python3
"""
Export PPV channels from database to PPV.list file.

Reads all PPV channels (is_ppv=True) from the database and writes them to PPV.list
in the format: id|stream_id|channel_name|country|category|0
"""

import logging
import os
import sys

# Set up database path before importing app
os.environ.setdefault("DATABASE_URL", "sqlite:////home/benklop/repos/iptv-proxy-v2/data/iptv_proxy.db")

from app import app  # noqa: E402
from models import Category, Channel, db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def export_ppv_channels():
    """Export PPV channels from database to PPV.list."""

    with app.app_context():
        try:
            # Query all PPV channels with their categories
            channels = (
                db.session.query(Channel, Category)
                .outerjoin(Category, Channel.category_id == Category.id)
                .filter(Channel.is_ppv.is_(True))
                .order_by(Channel.id)
                .all()
            )

            if not channels:
                logger.error("No PPV channels found in database")
                return False

            logger.info(f"Found {len(channels)} PPV channels in database")

            # Write to PPV.list
            with open("PPV.list", "w", encoding="utf-8") as f:
                for channel, category in channels:
                    # Extract country code from name if present (e.g., "US: " -> "US")
                    country = "XX"  # Default
                    if channel.name and "|" in channel.name:
                        parts = channel.name.split("|")
                        if len(parts[0].strip()) == 2:
                            country = parts[0].strip()

                    category_name = category.category_name if category else "Unknown"

                    # Format: id|stream_id|channel_name|country|category|0
                    line = f"{channel.id}|{channel.stream_id}|{channel.name}|{country}|{category_name}|0"
                    f.write(line + "\n")

            logger.info(f"✅ Exported {len(channels)} channels to PPV.list")
            return True

        except Exception as e:
            logger.error(f"Error exporting PPV channels: {e}")
            return False


if __name__ == "__main__":
    success = export_ppv_channels()
    sys.exit(0 if success else 1)
