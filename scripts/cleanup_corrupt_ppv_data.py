#!/usr/bin/env python3
"""
Reset corrupt PPV enrichment data and prepare for a clean re-enrichment run.

Removes:
- Channel→event links
- PPV event records
- PPV Events EPG channels, programs, and IPTV→EPG mappings
- Poisoned calendar cache file

Resets all PPV channels to queued for re-enrichment.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

CALENDAR_CACHE_FILENAME = "calendar_cache.json"

PPV_METADATA_KEYS = (
    "ppv_calendar_processed_count",
    "ppv_calendar_matched_count",
    "ppv_details_fetched_count",
    "ppv_detail_queue_size",
    "last_ppv_enrichment",
    "last_ppv_prefetch",
)


def cleanup_corrupt_ppv_data(db_path: str, data_dir: str, dry_run: bool = True) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        ppv_source = cursor.execute("SELECT id FROM epg_sources WHERE source_type = 'ppv_events'").fetchone()
        ppv_source_id = ppv_source[0] if ppv_source else None

        counts = {
            "event_links": cursor.execute("SELECT COUNT(*) FROM event_channel_links").fetchone()[0],
            "events": cursor.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "ppv_channels": cursor.execute("SELECT COUNT(*) FROM channels WHERE is_ppv = 1").fetchone()[0],
        }

        if ppv_source_id:
            counts["epg_channels"] = cursor.execute(
                "SELECT COUNT(*) FROM epg_channels WHERE source_id = ?",
                (ppv_source_id,),
            ).fetchone()[0]
            counts["epg_mappings"] = cursor.execute(
                """
                SELECT COUNT(*) FROM channel_epg_mappings cem
                JOIN epg_channels ec ON cem.epg_channel_id = ec.id
                WHERE ec.source_id = ?
                """,
                (ppv_source_id,),
            ).fetchone()[0]
            counts["epg_programs"] = cursor.execute(
                """
                SELECT COUNT(*) FROM epg_programs ep
                JOIN epg_channels ec ON ep.epg_channel_id = ec.id
                WHERE ec.source_id = ?
                """,
                (ppv_source_id,),
            ).fetchone()[0]
        else:
            counts["epg_channels"] = 0
            counts["epg_mappings"] = 0
            counts["epg_programs"] = 0

        cache_path = Path(data_dir) / CALENDAR_CACHE_FILENAME
        cache_exists = cache_path.exists()

        print(f"\n{'DRY RUN — no changes' if dry_run else 'APPLYING cleanup'}")
        print(f"Database: {db_path}")
        print(f"Data dir: {data_dir}")
        print("\nWill remove:")
        for key, value in counts.items():
            print(f"  {key}: {value}")
        print(f"  calendar_cache.json: {'yes' if cache_exists else 'no (missing)'}")
        print(f"\nWill queue {counts['ppv_channels']} PPV channels for re-enrichment")

        if dry_run:
            print("\nRun with --apply to execute.")
            return

        if ppv_source_id:
            cursor.execute(
                """
                DELETE FROM channel_epg_mappings
                WHERE epg_channel_id IN (
                    SELECT id FROM epg_channels WHERE source_id = ?
                )
                """,
                (ppv_source_id,),
            )
            cursor.execute(
                """
                DELETE FROM epg_programs
                WHERE epg_channel_id IN (
                    SELECT id FROM epg_channels WHERE source_id = ?
                )
                """,
                (ppv_source_id,),
            )
            cursor.execute("DELETE FROM epg_channels WHERE source_id = ?", (ppv_source_id,))
            cursor.execute(
                """
                UPDATE epg_sources
                SET channel_count = 0,
                    last_sync = NULL,
                    last_sync_status = NULL,
                    last_sync_message = NULL
                WHERE id = ?
                """,
                (ppv_source_id,),
            )

        cursor.execute("DELETE FROM event_channel_links")
        cursor.execute("DELETE FROM events")

        cursor.execute(
            """
            UPDATE channels
            SET ppv_enrichment_status = 'queued',
                ppv_enrichment_attempts = 0,
                ppv_enrichment_error = NULL,
                ppv_enrichment_last_attempt = NULL,
                thesportsdb_id = NULL
            WHERE is_ppv = 1
            """
        )
        queued = cursor.rowcount

        for key in PPV_METADATA_KEYS:
            cursor.execute("DELETE FROM sync_metadata WHERE key = ?", (key,))

        conn.commit()

        if cache_exists:
            cache_path.unlink()
            print(f"Removed {cache_path}")

        print("\nCleanup complete:")
        print(f"  PPV channels queued: {queued}")
        print(f"  Removed {counts['event_links']} event links")
        print(f"  Removed {counts['events']} events")
        if ppv_source_id:
            print(f"  Removed {counts['epg_channels']} PPV EPG channels")
            print(f"  Removed {counts['epg_mappings']} EPG mappings")
            print(f"  Removed {counts['epg_programs']} EPG programs")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset corrupt PPV enrichment data")
    parser.add_argument("--db", default="data/iptv_proxy.db", help="Path to SQLite database")
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Data directory containing calendar_cache.json",
    )
    parser.add_argument("--apply", action="store_true", help="Execute cleanup (default is dry run)")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    cleanup_corrupt_ppv_data(str(db_path), args.data_dir, dry_run=not args.apply)


if __name__ == "__main__":
    main()
