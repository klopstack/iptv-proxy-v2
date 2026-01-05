#!/usr/bin/env python3
"""
Cleanup script to remove low-confidence PPV event-channel matches.

This script removes EventChannelLink records with confidence below 0.5,
which were created due to the previous MIN_MATCH_CONFIDENCE threshold of 0.3.

After cleanup, channels can be re-enriched with the new, higher threshold.
"""

import sqlite3
import sys
from pathlib import Path


def cleanup_low_confidence_matches(db_path: str, threshold: float = 0.35, dry_run: bool = True) -> None:
    """
    Remove event-channel links below the confidence threshold.

    Args:
        db_path: Path to the SQLite database
        threshold: Minimum confidence to keep (default 0.35, matching MIN_MATCH_CONFIDENCE)
        dry_run: If True, only report what would be deleted without deleting
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Count links below threshold
        cursor.execute("SELECT COUNT(*) FROM event_channel_links WHERE match_confidence < ?", (threshold,))
        count = cursor.fetchone()[0]

        if count == 0:
            print(f"✓ No event-channel links found with confidence below {threshold}")
            return

        # Get details of what will be removed
        cursor.execute(
            """
            SELECT 
                ecl.id,
                c.name,
                e.home_team_name,
                e.away_team_name,
                ecl.match_confidence,
                ecl.match_method
            FROM event_channel_links ecl
            JOIN channels c ON ecl.channel_id = c.id
            JOIN events e ON ecl.event_id = e.id
            WHERE ecl.match_confidence < ?
            ORDER BY ecl.match_confidence ASC
            LIMIT 20
            """,
            (threshold,),
        )

        print(
            f"\n{'DRY RUN: Would remove' if dry_run else 'Removing'} {count} event-channel links with confidence < {threshold}"
        )
        print("\nSample of links to be removed:")
        print("-" * 120)
        print(f"{'Channel Name':<60} {'Event':<40} {'Conf':>6} {'Method':<20}")
        print("-" * 120)

        for link_id, channel_name, home_team, away_team, confidence, method in cursor.fetchall():
            event_name = f"{home_team} vs {away_team}"
            print(f"{channel_name[:60]:<60} {event_name[:40]:<40} {confidence:6.2f} {method:<20}")

        if not dry_run:
            # Delete the low-confidence links
            cursor.execute("DELETE FROM event_channel_links WHERE match_confidence < ?", (threshold,))
            conn.commit()
            print(f"\n✓ Removed {count} low-confidence event-channel links")

            # Reset channel enrichment status so they can be re-enriched
            cursor.execute(
                """
                UPDATE channels 
                SET ppv_enrichment_status = NULL,
                    ppv_enrichment_last_attempt = NULL
                WHERE id IN (
                    SELECT DISTINCT channel_id 
                    FROM event_channel_links 
                    WHERE match_confidence < ?
                )
                """,
                (threshold,),
            )
            reset_count = cursor.rowcount
            conn.commit()
            print(f"✓ Reset enrichment status for {reset_count} channels")

            # Show remaining statistics
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    AVG(match_confidence) as avg_confidence,
                    MIN(match_confidence) as min_confidence,
                    MAX(match_confidence) as max_confidence
                FROM event_channel_links
                """
            )
            stats = cursor.fetchone()
            print(f"\nRemaining event-channel links:")
            print(f"  Total: {stats[0]}")
            print(f"  Avg confidence: {stats[1]:.2f}")
            print(f"  Range: {stats[2]:.2f} - {stats[3]:.2f}")
        else:
            print(f"\n⚠ DRY RUN - No changes made. Run with --apply to actually delete these links.")

    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Clean up low-confidence PPV event-channel matches",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview what would be deleted (dry run)
  python cleanup_low_confidence_matches.py

  # Actually delete low-confidence matches
  python cleanup_low_confidence_matches.py --apply

  # Use custom threshold
  python cleanup_low_confidence_matches.py --threshold 0.6 --apply

  # Specify database path
  python cleanup_low_confidence_matches.py --db /path/to/iptv_proxy.db --apply
        """,
    )

    parser.add_argument(
        "--db",
        default="data/iptv_proxy.db",
        help="Path to SQLite database (default: data/iptv_proxy.db)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.35,
        help="Minimum confidence threshold to keep (default: 0.35, matching MIN_MATCH_CONFIDENCE)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete the links (without this, runs in dry-run mode)",
    )

    args = parser.parse_args()

    # Check if database exists
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"✗ Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    cleanup_low_confidence_matches(
        db_path=str(db_path),
        threshold=args.threshold,
        dry_run=not args.apply,
    )


if __name__ == "__main__":
    main()
