#!/usr/bin/env python3
"""
Check EPG entry generation and channel-event associations.
Diagnoses whether EPG entries are being generated and properly linked.
"""

import sqlite3


def check_epg_status():
    """Check EPG entry generation status."""
    print("=" * 80)
    print("EPG ENTRY GENERATION & CHANNEL ASSOCIATION STATUS")
    print("=" * 80)

    conn = sqlite3.connect("data/iptv_proxy.db")
    cursor = conn.cursor()

    # 1. Check Event table
    print("\n1. EVENT TABLE STATUS")
    cursor.execute("SELECT COUNT(*) FROM events")
    event_count = cursor.fetchone()[0]
    print(f"   Total events in database: {event_count}")

    if event_count > 0:
        cursor.execute(
            """
            SELECT
                e.id,
                e.external_id,
                e.home_team_name,
                e.away_team_name,
                e.sport,
                e.scheduled_at,
                COUNT(ecl.channel_id) as linked_channels
            FROM events e
            LEFT JOIN event_channel_links ecl ON e.id = ecl.event_id
            GROUP BY e.id
            LIMIT 5
        """
        )
        for row in cursor.fetchall():
            print(f"   Event {row[0]}: {row[2]} vs {row[3]} ({row[4]}) @ {row[5]}")
            print(f"     → Linked to {row[6]} channels")
    else:
        print("   ✗ NO EVENTS IN DATABASE - EPG ENRICHMENT NOT RUNNING")

    # 2. Check EventChannelLink table
    print("\n2. EVENT-CHANNEL LINK STATUS")
    cursor.execute("SELECT COUNT(*) FROM event_channel_links")
    link_count = cursor.fetchone()[0]
    print(f"   Total channel-event links: {link_count}")

    if link_count > 0:
        cursor.execute(
            """
            SELECT
                ecl.event_id,
                ecl.channel_id,
                c.name,
                ecl.match_confidence,
                ecl.match_method
            FROM event_channel_links ecl
            JOIN channels c ON ecl.channel_id = c.id
            LIMIT 5
        """
        )
        for row in cursor.fetchall():
            print(f"   Event {row[0]} ↔ Channel {row[1]}: {row[2]}")
            print(f"     Confidence: {row[3]}, Method: {row[4]}")
    else:
        print("   ✗ NO CHANNEL-EVENT LINKS - ENRICHMENT NOT CREATING ASSOCIATIONS")

    # 3. Check PPV channels and their enrichment status
    print("\n3. PPV CHANNEL ENRICHMENT STATUS")
    cursor.execute(
        """
        SELECT
            ppv_enrichment_status,
            COUNT(*) as count
        FROM channels
        WHERE is_ppv = 1
        GROUP BY ppv_enrichment_status
    """
    )

    status_counts = cursor.fetchall()
    if status_counts:
        total_ppv = sum(count for _, count in status_counts)
        print(f"   Total PPV channels: {total_ppv}")
        for status, count in status_counts:
            status_display = status if status else "NULL"
            print(f"     • {status_display}: {count}")
    else:
        cursor.execute("SELECT COUNT(*) FROM channels WHERE is_ppv = 1")
        ppv_count = cursor.fetchone()[0]
        print(f"   Total PPV channels: {ppv_count}")
        print("   ✗ No enrichment status tracking - field may be NULL for all channels")

    # 4. Check for queued or in-progress enrichment
    print("\n4. CURRENT ENRICHMENT QUEUE STATUS")
    cursor.execute(
        """
        SELECT
            ppv_enrichment_status,
            COUNT(*) as count
        FROM channels
        WHERE ppv_enrichment_status IN ('queued', 'processing', 'retry_pending', 'error')
        GROUP BY ppv_enrichment_status
    """
    )

    queue_items = cursor.fetchall()
    if queue_items:
        print("   Channels awaiting enrichment:")
        for status, count in queue_items:
            print(f"     • {status}: {count}")
    else:
        print("   ✗ No channels queued for enrichment")

    # 5. Check enrichment metadata
    print("\n5. ENRICHMENT METADATA")
    cursor.execute(
        """
        SELECT key, value FROM sync_metadata
        WHERE key LIKE 'ppv_enrichment%' OR key LIKE 'thesportsdb%'
    """
    )

    metadata = cursor.fetchall()
    if metadata:
        for key, value in metadata:
            value_display = value[:60] + "..." if len(value) > 60 else value
            print(f"   {key}: {value_display}")
    else:
        print("   ✗ No enrichment metadata found")

    # 6. Check EPG Channel associations
    print("\n6. EPG CHANNEL ASSOCIATIONS")
    cursor.execute("SELECT COUNT(*) FROM epg_channels")
    epg_count = cursor.fetchone()[0]
    print(f"   Total EPG channels in database: {epg_count}")

    cursor.execute("SELECT COUNT(*) FROM channels WHERE epg_channel_id IS NOT NULL")
    channels_with_epg = cursor.fetchone()[0]
    print(f"   Channels with EPG mappings: {channels_with_epg}")

    cursor.execute("SELECT COUNT(*) FROM channel_epg_mappings")
    mapping_count = cursor.fetchone()[0]
    print(f"   Channel-EPG mapping entries: {mapping_count}")

    # 7. Check for PPV visibility settings
    print("\n7. PPV VISIBILITY SETTINGS")
    cursor.execute(
        """
        SELECT ppv_visibility, COUNT(*) as count
        FROM accounts
        WHERE ppv_visibility IS NOT NULL
        GROUP BY ppv_visibility
    """
    )

    visibility = cursor.fetchall()
    if visibility:
        for vis, count in visibility:
            print(f"   {vis}: {count} accounts")
    else:
        print("   ✗ No PPV visibility settings configured")

    conn.close()

    # Summary
    print("\n" + "=" * 80)
    print("DIAGNOSIS SUMMARY")
    print("=" * 80)

    if event_count == 0 and link_count == 0:
        print(
            """
✗ ISSUE FOUND: EPG entries are NOT being generated and NO channels are linked to events.

ROOT CAUSE: The PPV enrichment background task is either:
  1. Not running (scheduler not active)
  2. Not being called with actual PPV channels
  3. Not queuing channels successfully
  4. Not successfully matching channels to events

NEXT STEPS:
  1. Verify scheduler is running: Check scheduler logs
  2. Queue channels for enrichment: POST /api/ppv-enrichment/queue/all-ppv
  3. Check enrichment status: GET /api/ppv-enrichment/status
  4. Run enrichment manually: POST /api/ppv-enrichment/process
  5. Monitor TheSportsDB API responses
        """
        )
    elif event_count > 0 and link_count > 0:
        print(
            f"""
✓ SUCCESS: EPG entries are being generated and channels are properly linked.

  {event_count} events in database
  {link_count} channel-event associations

EPG generation should work correctly.
        """
        )
    elif event_count > 0 and link_count == 0:
        print(
            f"""
⚠ PARTIAL SUCCESS: Events exist but NO channels are linked.

  {event_count} events created
  {link_count} channel-event links (NONE!)

The enrichment service is creating events but not linking them to channels.
This may be because:
  1. All enrichment attempts failed at the matching stage
  2. Events were imported manually but not linked
  3. Channel-event linking is failing silently

CHECK: Look at channel ppv_enrichment_status and ppv_enrichment_error fields.
        """
        )


if __name__ == "__main__":
    check_epg_status()
