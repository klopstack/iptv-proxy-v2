#!/usr/bin/env python3
"""
Test script to manually trigger EPG sync and check results.
"""
import sys
import time

import requests


def test_epg_sync(source_id: int):
    """Trigger EPG sync for a source and check results."""
    base_url = "http://localhost:8000"

    # Get source info before sync
    print(f"\n=== Testing EPG Sync for Source ID {source_id} ===\n")

    # Trigger sync
    print(f"Triggering sync for source {source_id}...")
    response = requests.post(f"{base_url}/api/epg/sources/{source_id}/sync", timeout=600)

    if response.status_code == 200:
        result = response.json()
        print("✅ Sync successful!")
        print(f"   Message: {result.get('message', 'N/A')}")
        if "stats" in result:
            stats = result["stats"]
            print("   Stats:")
            print(f"     - Channels added: {stats.get('channels_added', 0)}")
            print(f"     - Channels updated: {stats.get('channels_updated', 0)}")
            print(f"     - Programs added: {stats.get('programs_added', 0)}")
            print(f"     - Programs updated: {stats.get('programs_updated', 0)}")
            print(f"     - Programs deleted: {stats.get('programs_deleted', 0)}")
    else:
        print(f"❌ Sync failed with status {response.status_code}")
        print(f"   Response: {response.text}")
        return False

    # Give DB a moment to settle
    time.sleep(1)

    # Check program count
    print("\nChecking program count in database...")
    response = requests.get(f"{base_url}/api/epg/sources/{source_id}")
    if response.status_code == 200:
        source = response.json()
        print(f"   Source: {source['name']}")
        print(f"   Type: {source['source_type']}")
        print(f"   Channel count: {source.get('channel_count', 0)}")
        print(f"   Last sync: {source.get('last_sync', 'Never')}")

    return True


if __name__ == "__main__":
    # Test with PlutoTV (source 4) which is usually fast
    source_id = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    success = test_epg_sync(source_id)
    sys.exit(0 if success else 1)
