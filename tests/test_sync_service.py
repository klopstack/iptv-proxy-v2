"""
Tests for Channel Sync Service

Uses shared fixtures from conftest.py for proper test isolation.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from models import Account, Category, Channel, Event, EventChannelLink, db
from services.sync_service import ChannelSyncService

# app fixture is provided by conftest.py


class TestChannelSyncService:
    """Test suite for ChannelSyncService"""

    def test_sync_account_not_found(self, app):
        """Test syncing non-existent account"""
        with app.app_context():
            result = ChannelSyncService.sync_account(99999)

            assert result["success"] is False
            assert "not found" in result["error"].lower()

    def test_sync_account_disabled(self, app):
        """Test syncing disabled account"""
        with app.app_context():
            # Create disabled account
            account = Account(
                name="Disabled Account", server="test.com:8080", username="test", password="test", enabled=False
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            result = ChannelSyncService.sync_account(account_id)

            assert result["success"] is False
            assert "disabled" in result["error"].lower()

    @patch("services.sync_service.get_iptv_service_for_account")
    def test_sync_account_success(self, mock_iptv_class, app):
        """Test successful account sync"""
        with app.app_context():
            # Create enabled account
            account = Account(
                name="Test Account", server="test.com:8080", username="test", password="test", enabled=True
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            # Mock IPTVService
            mock_service = Mock()
            mock_service.get_live_categories.return_value = [
                {"category_id": "1", "category_name": "Sports", "parent_id": 0}
            ]
            mock_service.get_live_streams.return_value = [
                {"stream_id": 101, "name": "ESPN", "category_id": "1", "stream_icon": "http://example.com/icon.png"}
            ]
            mock_iptv_class.return_value = mock_service

            result = ChannelSyncService.sync_account(account_id)

            assert result["success"] is True
            assert result["account_id"] == account_id
            assert result["categories_added"] >= 0
            assert result["channels_added"] >= 0

    @patch("services.sync_service.get_iptv_service_for_account")
    def test_sync_account_categories_error(self, mock_iptv_class, app):
        """Test sync with categories fetch error"""
        with app.app_context():
            account = Account(
                name="Test Account", server="test.com:8080", username="test", password="test", enabled=True
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            # Mock service to raise error on categories
            mock_service = Mock()
            mock_service.get_live_categories.side_effect = Exception("API Error")
            mock_service.get_live_streams.return_value = []
            mock_iptv_class.return_value = mock_service

            result = ChannelSyncService.sync_account(account_id)

            # Should still succeed but with errors noted
            assert "Categories sync error" in str(result.get("errors", []))

    @patch("services.sync_service.get_iptv_service_for_account")
    def test_sync_account_channels_error(self, mock_iptv_class, app):
        """Test sync with channels fetch error"""
        with app.app_context():
            account = Account(
                name="Test Account", server="test.com:8080", username="test", password="test", enabled=True
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            # Mock service to raise error on channels
            mock_service = Mock()
            mock_service.get_live_categories.return_value = []
            mock_service.get_live_streams.side_effect = Exception("Channels API Error")
            mock_iptv_class.return_value = mock_service

            result = ChannelSyncService.sync_account(account_id)

            # Should fail when channels sync fails
            assert result["success"] is False
            assert "Channels sync error" in str(result.get("errors", []))

    @patch("services.sync_service.get_iptv_service_for_account")
    def test_sync_categories_new(self, mock_iptv_class, app):
        """Test syncing new categories"""
        with app.app_context():
            account = Account(
                name="Test Account", server="test.com:8080", username="test", password="test", enabled=True
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            mock_service = Mock()
            mock_service.get_live_categories.return_value = [
                {"category_id": "1", "category_name": "Sports", "parent_id": 0},
                {"category_id": "2", "category_name": "Movies", "parent_id": 0},
            ]
            mock_service.get_live_streams.return_value = []
            mock_iptv_class.return_value = mock_service

            result = ChannelSyncService.sync_account(account_id)

            assert result["success"] is True
            assert result["categories_added"] == 2

            # Verify categories in DB
            categories = Category.query.filter_by(account_id=account_id).all()
            assert len(categories) == 2

    @patch("services.sync_service.get_iptv_service_for_account")
    def test_sync_categories_existing(self, mock_iptv_class, app):
        """Test syncing existing categories (updates)"""
        with app.app_context():
            account = Account(
                name="Test Account", server="test.com:8080", username="test", password="test", enabled=True
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            # Add existing category
            existing_cat = Category(
                account_id=account_id, category_id="1", category_name="Old Sports Name", parent_id=0
            )
            db.session.add(existing_cat)
            db.session.commit()

            mock_service = Mock()
            mock_service.get_live_categories.return_value = [
                {"category_id": "1", "category_name": "New Sports Name", "parent_id": 0}
            ]
            mock_service.get_live_streams.return_value = []
            mock_iptv_class.return_value = mock_service

            result = ChannelSyncService.sync_account(account_id)

            assert result["success"] is True
            assert result["categories_updated"] == 1

            # Verify category was updated
            updated_cat = Category.query.filter_by(account_id=account_id, category_id="1").first()
            assert updated_cat.category_name == "New Sports Name"

    @patch("services.sync_service.get_iptv_service_for_account")
    def test_sync_channels_new(self, mock_iptv_class, app):
        """Test syncing new channels"""
        with app.app_context():
            account = Account(
                name="Test Account", server="test.com:8080", username="test", password="test", enabled=True
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            mock_service = Mock()
            mock_service.get_live_categories.return_value = []
            mock_service.get_live_streams.return_value = [
                {"stream_id": 101, "name": "ESPN", "category_id": "1", "stream_icon": "http://example.com/icon.png"}
            ]
            mock_iptv_class.return_value = mock_service

            result = ChannelSyncService.sync_account(account_id)

            assert result["success"] is True
            assert result["channels_added"] == 1

            # Verify channel in DB
            channel = Channel.query.filter_by(account_id=account_id, stream_id="101").first()
            assert channel is not None
            assert channel.name == "ESPN"
            assert channel.is_active is True

    @patch("services.sync_service.get_iptv_service_for_account")
    def test_sync_channels_existing(self, mock_iptv_class, app):
        """Test syncing existing channels (updates)"""
        with app.app_context():
            account = Account(
                name="Test Account", server="test.com:8080", username="test", password="test", enabled=True
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            # Add existing channel
            existing_channel = Channel(
                account_id=account_id,
                stream_id="101",
                name="Old ESPN Name",
                category_id=None,
                is_active=True,
                last_seen=datetime.now(timezone.utc),
            )
            db.session.add(existing_channel)
            db.session.commit()

            mock_service = Mock()
            mock_service.get_live_categories.return_value = []
            mock_service.get_live_streams.return_value = [
                {
                    "stream_id": 101,
                    "name": "New ESPN Name",
                    "category_id": "1",
                    "stream_icon": "http://example.com/icon.png",
                }
            ]
            mock_iptv_class.return_value = mock_service

            result = ChannelSyncService.sync_account(account_id)

            assert result["success"] is True
            assert result["channels_updated"] == 1

            # Verify channel was updated
            updated_channel = Channel.query.filter_by(account_id=account_id, stream_id="101").first()
            assert updated_channel.name == "New ESPN Name"

    @patch("services.sync_service.get_iptv_service_for_account")
    def test_sync_deactivates_old_channels(self, mock_iptv_class, app):
        """Test that channels not seen in sync are deactivated"""
        with app.app_context():
            account = Account(
                name="Test Account", server="test.com:8080", username="test", password="test", enabled=True
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            # Add old channel that won't be in sync
            old_channel = Channel(
                account_id=account_id,
                stream_id="999",
                name="Old Channel",
                category_id=None,
                is_active=True,
                last_seen=datetime.now(timezone.utc) - timedelta(hours=1),  # Old timestamp
            )
            db.session.add(old_channel)
            db.session.commit()

            mock_service = Mock()
            mock_service.get_live_categories.return_value = []
            mock_service.get_live_streams.return_value = []  # Empty - no channels
            mock_iptv_class.return_value = mock_service

            result = ChannelSyncService.sync_account(account_id)

            assert result["success"] is True
            assert result["channels_deactivated"] >= 0  # Should deactivate old channel

            # Verify old channel was deactivated
            deactivated = Channel.query.filter_by(account_id=account_id, stream_id="999").first()
            assert deactivated.is_active is False

    @patch("services.sync_service.get_iptv_service_for_account")
    def test_sync_all_enabled_accounts(self, mock_iptv_class, app):
        """Test syncing all enabled accounts"""
        with app.app_context():
            # Create multiple accounts
            account1 = Account(name="Account1", server="test.com", username="u1", password="p1", enabled=True)
            account2 = Account(name="Account2", server="test.com", username="u2", password="p2", enabled=False)
            account3 = Account(name="Account3", server="test.com", username="u3", password="p3", enabled=True)

            db.session.add_all([account1, account2, account3])
            db.session.commit()

            mock_service = Mock()
            mock_service.get_live_categories.return_value = []
            mock_service.get_live_streams.return_value = []
            mock_iptv_class.return_value = mock_service

            results = ChannelSyncService.sync_all_accounts()

            # Should sync only enabled accounts (account1 and account3)
            assert len(results) == 2
            synced_names = [r["account_name"] for r in results]
            assert "Account1" in synced_names
            assert "Account3" in synced_names
            assert "Account2" not in synced_names

    @patch("services.sync_service.get_iptv_service_for_account")
    def test_ppv_channel_name_change_resets_enrichment(self, mock_iptv_class, app):
        """Test that PPV channel name change resets enrichment status and removes event links"""
        with app.app_context():
            account = Account(
                name="Test Account", server="test.com:8080", username="test", password="test", enabled=True
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            # Create PPV category
            category = Category(account_id=account_id, category_id="ppv", category_name="PPV", parent_id=0)
            db.session.add(category)
            db.session.commit()

            # Add existing PPV channel with enrichment data
            existing_channel = Channel(
                account_id=account_id,
                stream_id="101",
                name="UFC 300: Jones vs Miocic",
                cleaned_name="UFC 300: Jones vs Miocic",
                category_id=category.id,
                is_ppv=True,
                is_active=True,
                last_seen=datetime.now(timezone.utc),
                ppv_enrichment_status="matched",
                ppv_enrichment_queue_id="queue_12345",
                ppv_enrichment_attempts=1,
                thesportsdb_id="123456",
            )
            db.session.add(existing_channel)
            db.session.commit()
            channel_id = existing_channel.id

            # Create an event and link it to the channel
            event = Event(
                external_id="123456",
                source=Event.SOURCE_THESPORTSDB,
                home_team_id="1",
                home_team_name="Jon Jones",
                away_team_id="2",
                away_team_name="Stipe Miocic",
                scheduled_at=datetime.now(timezone.utc),
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(event)
            db.session.commit()

            link = EventChannelLink(
                event_id=event.id,
                channel_id=channel_id,
                match_confidence=0.9,
                match_method="calendar_browse",
            )
            db.session.add(link)
            db.session.commit()

            # Verify link exists
            links_before = EventChannelLink.query.filter_by(channel_id=channel_id).count()
            assert links_before == 1

            # Mock IPTVService to return channel with new name (different event)
            mock_service = Mock()
            mock_service.get_live_categories.return_value = [
                {"category_id": "ppv", "category_name": "PPV", "parent_id": 0}
            ]
            mock_service.get_live_streams.return_value = [
                {
                    "stream_id": 101,
                    "name": "UFC 301: New Fight Card",  # Name changed!
                    "category_id": "ppv",
                }
            ]
            mock_iptv_class.return_value = mock_service

            result = ChannelSyncService.sync_account(account_id)

            assert result["success"] is True
            assert result["channels_updated"] == 1

            # Verify channel was enqueued for re-enrichment
            updated_channel = db.session.get(Channel, channel_id)
            assert updated_channel.name == "UFC 301: New Fight Card"
            assert updated_channel.ppv_enrichment_status == "queued"  # Enqueued for enrichment
            assert updated_channel.ppv_enrichment_queue_id is not None  # Has a queue ID
            assert updated_channel.ppv_enrichment_queue_id.startswith("sync_")
            assert updated_channel.ppv_enrichment_attempts == 0
            assert updated_channel.ppv_enrichment_error is None
            assert updated_channel.thesportsdb_id is None

            # Verify event link was removed
            links_after = EventChannelLink.query.filter_by(channel_id=channel_id).count()
            assert links_after == 0

    @patch("services.sync_service.get_iptv_service_for_account")
    def test_non_ppv_channel_name_change_does_not_reset_enrichment(self, mock_iptv_class, app):
        """Test that non-PPV channel name change does NOT reset enrichment fields"""
        with app.app_context():
            account = Account(
                name="Test Account", server="test.com:8080", username="test", password="test", enabled=True
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            # Add existing non-PPV channel with enrichment status (shouldn't be touched)
            existing_channel = Channel(
                account_id=account_id,
                stream_id="201",
                name="ESPN HD",
                cleaned_name="ESPN HD",
                is_ppv=False,
                is_active=True,
                last_seen=datetime.now(timezone.utc),
                ppv_enrichment_status="matched",  # Has enrichment status somehow
                ppv_enrichment_queue_id="queue_999",
            )
            db.session.add(existing_channel)
            db.session.commit()
            channel_id = existing_channel.id

            # Mock IPTVService to return channel with new name
            mock_service = Mock()
            mock_service.get_live_categories.return_value = []
            mock_service.get_live_streams.return_value = [
                {
                    "stream_id": 201,
                    "name": "ESPN 4K",  # Name changed
                    "category_id": "",
                }
            ]
            mock_iptv_class.return_value = mock_service

            result = ChannelSyncService.sync_account(account_id)

            assert result["success"] is True

            # Verify enrichment status was NOT reset for non-PPV channel
            updated_channel = db.session.get(Channel, channel_id)
            assert updated_channel.name == "ESPN 4K"
            assert updated_channel.ppv_enrichment_status == "matched"
            assert updated_channel.ppv_enrichment_queue_id == "queue_999"
