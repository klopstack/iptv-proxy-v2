#!/usr/bin/env python3
"""
Quick test to verify dynamic filtering works correctly.
Run this to test the fix for preview channels filtering.
"""

from app import app
from models import Account, Category, Channel, Filter, db
from services.filter_service import FilterService


def test_dynamic_filtering():
    """Test that dynamic filtering correctly filters channels"""
    with app.app_context():
        # Find an account
        account = Account.query.first()
        if not account:
            print("❌ No accounts found in database")
            return

        print(f"✅ Testing account: {account.name} (ID: {account.id})")

        # Get filters for this account
        filters = Filter.query.filter_by(account_id=account.id, enabled=True).all()
        print(f"\n📋 Filters ({len(filters)}):")
        for f in filters:
            print(f"  - {f.filter_action} {f.filter_type}: '{f.filter_value}'")

        # Get some test channels
        test_channels = (
            Channel.query.filter_by(account_id=account.id, is_active=True)
            .join(Category, Channel.category_id == Category.id, isouter=True)
            .limit(100)
            .all()
        )

        print(f"\n📺 Total test channels: {len(test_channels)}")

        # Apply filters dynamically
        filtered_channels = FilterService.apply_filters_to_channels(test_channels, account.id)

        print(f"✅ Filtered channels: {len(filtered_channels)}")
        print(f"🗑️  Filtered out: {len(test_channels) - len(filtered_channels)}")

        # Look for specific problematic channel
        problem_channel = None
        for ch in test_channels:
            if "SERIE A TEAM PPV" in ch.name and ch.name.startswith("###"):
                problem_channel = ch
                break

        if problem_channel:
            print(f"\n🔍 Found problem channel: {problem_channel.name}")
            print(f"   Category: {problem_channel.category.category_name if problem_channel.category else 'None'}")
            print(f"   Was filtered: {problem_channel not in filtered_channels}")

            # Test PPV placeholder detection
            from services.filter_service import is_ppv_placeholder_name

            is_placeholder = is_ppv_placeholder_name(problem_channel.name)
            print(f"   Is PPV placeholder: {is_placeholder}")

            if problem_channel in filtered_channels:
                print("   ❌ ERROR: Channel should have been filtered out!")
            else:
                print("   ✅ SUCCESS: Channel was correctly filtered out!")

        print("\n✅ Dynamic filtering test complete!")


if __name__ == "__main__":
    test_dynamic_filtering()
