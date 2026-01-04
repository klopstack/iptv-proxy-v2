#!/usr/bin/env python3
"""
Test script for Xtream Codes API functionality
Demonstrates credential creation and API usage
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app import app
from models import Account, XtreamCredential, db


def test_xtream_api():
    """Test Xtream API endpoints"""
    print("=" * 80)
    print("Xtream Codes API Test Suite")
    print("=" * 80)

    with app.app_context():
        # Test 1: Create test credential
        print("\n[1/5] Testing credential creation...")

        # Check if test account exists
        test_account = Account.query.filter_by(name="Test Account").first()
        if not test_account:
            print("⚠️  No test account found. Please create an account first.")
            print("   This test requires at least one account in the database.")
            return False

        # Create test credential
        test_cred = XtreamCredential.query.filter_by(username="test-user").first()
        if test_cred:
            print(f"   ℹ️  Using existing credential: {test_cred.username}")
        else:
            test_cred = XtreamCredential(
                username="test-user",
                password="test-pass",
                account_id=test_account.id,
                use_filters=True,
                collapse_duplicates=False,
                enabled=True,
                description="Test credential for API validation",
            )
            db.session.add(test_cred)
            db.session.commit()
            print(f"   ✅ Created test credential: {test_cred.username}")

        # Test 2: Verify model relationships
        print("\n[2/5] Testing model relationships...")
        assert test_cred.account is not None, "Account relationship failed"
        assert test_cred.account.id == test_account.id, "Account ID mismatch"
        print(f"   ✅ Credential linked to account: {test_cred.account.name}")

        # Test 3: Test authentication function
        print("\n[3/5] Testing authentication...")
        from routes.xtream import authenticate_xtream

        with app.test_request_context("/?username=test-user&password=test-pass"):
            xtream_cred, account, playlist_config = authenticate_xtream()
            assert xtream_cred is not None, "Authentication failed"
            assert xtream_cred.username == "test-user", "Wrong credential returned"
            assert account is not None, "Account not loaded"
            print(f"   ✅ Authentication successful for: {xtream_cred.username}")

        # Test 4: Test API endpoints
        print("\n[4/5] Testing API endpoints...")

        # Test user info endpoint
        with app.test_client() as client:
            response = client.get("/player_api.php?username=test-user&password=test-pass")
            assert response.status_code == 200, f"User info endpoint failed: {response.status_code}"
            data = json.loads(response.data)
            assert "user_info" in data, "Missing user_info in response"
            assert data["user_info"]["auth"] == 1, "Authentication failed"
            print(f"   ✅ /player_api.php (auth): {data['user_info']['status']}")

        # Test live categories endpoint
        with app.test_client() as client:
            response = client.get("/player_api.php?username=test-user&password=test-pass&action=get_live_categories")
            assert response.status_code == 200, f"Categories endpoint failed: {response.status_code}"
            categories = json.loads(response.data)
            assert isinstance(categories, list), "Categories should be a list"
            print(f"   ✅ /player_api.php?action=get_live_categories: {len(categories)} categories")

        # Test live streams endpoint
        with app.test_client() as client:
            response = client.get("/player_api.php?username=test-user&password=test-pass&action=get_live_streams")
            assert response.status_code == 200, f"Streams endpoint failed: {response.status_code}"
            streams = json.loads(response.data)
            assert isinstance(streams, list), "Streams should be a list"
            print(f"   ✅ /player_api.php?action=get_live_streams: {len(streams)} streams")

        # Test 5: Test management API
        print("\n[5/5] Testing management API...")

        with app.test_client() as client:
            # List credentials
            response = client.get("/api/xtream-credentials")
            assert response.status_code == 200, "List credentials failed"
            credentials = json.loads(response.data)
            assert len(credentials) > 0, "No credentials found"
            print(f"   ✅ GET /api/xtream-credentials: {len(credentials)} credentials")

        print("\n" + "=" * 80)
        print("✅ All tests passed!")
        print("=" * 80)

        # Print usage example
        print("\n📝 Usage Example:")
        print(f"   Server: http://localhost:8000")
        print(f"   Username: test-user")
        print(f"   Password: test-pass")
        print(f"   Account: {test_account.name}")
        print("\nTest this in an IPTV client like TiviMate or IPTV Smarters!")

        return True


if __name__ == "__main__":
    try:
        success = test_xtream_api()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
