"""
Tests for PPV (Pay-Per-View) channel detection and EPG handling
"""
from models import Account, Category, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db
from services.epg_service import EpgService, is_ppv_channel


class TestPPVDetection:
    """Test PPV channel detection"""

    def test_ppv_category_detected(self, app):
        """Test that PPV category is detected"""
        with app.app_context():
            account = Account(
                name="Test Account",
                server="http://test.com",
                username="user",
                password="pass",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="100", category_name="PPV EVENTS")
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="PPV Event Channel",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            assert is_ppv_channel(channel) is True

    def test_pay_per_view_category_detected(self, app):
        """Test that PAY-PER-VIEW category is detected"""
        with app.app_context():
            account = Account(
                name="Test Account",
                server="http://test.com",
                username="user",
                password="pass",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            category = Category(
                account_id=account.id,
                category_id="101",
                category_name="US| PAY-PER-VIEW",
            )
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="1002",
                name="Boxing Event",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            assert is_ppv_channel(channel) is True

    def test_ufc_ppv_category_detected(self, app):
        """Test that UFC PPV category is detected"""
        with app.app_context():
            account = Account(
                name="Test Account", server="http://test.com", username="user", password="pass", enabled=True
            )
            db.session.add(account)
            db.session.commit()

            # Real IPTV providers use "UFC PPV" not "UFC EVENTS" for PPV categories
            category = Category(account_id=account.id, category_id="102", category_name="US| UFC PPV")
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id, stream_id="1003", name="UFC 300", category_id=category.id, is_active=True
            )
            db.session.add(channel)
            db.session.commit()

            assert is_ppv_channel(channel) is True

    def test_wwe_ppv_category_detected(self, app):
        """Test that WWE PPV category is detected"""
        with app.app_context():
            account = Account(
                name="Test Account", server="http://test.com", username="user", password="pass", enabled=True
            )
            db.session.add(account)
            db.session.commit()

            # Real IPTV providers use "WWE PPV" not "WWE EVENTS" for PPV categories
            category = Category(account_id=account.id, category_id="103", category_name="US| WWE PPV")
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id, stream_id="1004", name="WrestleMania", category_id=category.id, is_active=True
            )
            db.session.add(channel)
            db.session.commit()

            assert is_ppv_channel(channel) is True

    def test_normal_category_not_ppv(self, app):
        """Test that normal categories are not detected as PPV"""
        with app.app_context():
            account = Account(
                name="Test Account", server="http://test.com", username="user", password="pass", enabled=True
            )
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="200", category_name="US| ENTERTAINMENT")
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id, stream_id="2001", name="ESPN", category_id=category.id, is_active=True
            )
            db.session.add(channel)
            db.session.commit()

            assert is_ppv_channel(channel) is False

    def test_channel_without_category_not_ppv(self, app):
        """Test that channels without a category are not detected as PPV"""
        with app.app_context():
            account = Account(
                name="Test Account", server="http://test.com", username="user", password="pass", enabled=True
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id, stream_id="3001", name="Uncategorized Channel", category_id=None, is_active=True
            )
            db.session.add(channel)
            db.session.commit()

            assert is_ppv_channel(channel) is False


class TestPPVEPGMatching:
    """Test that PPV channels are skipped during EPG matching"""

    def test_ppv_channels_skipped_in_matching(self, app):
        """Test that PPV channels are skipped during EPG matching"""
        with app.app_context():
            account = Account(
                name="Test Account", server="http://test.com", username="user", password="pass", enabled=True
            )
            db.session.add(account)
            db.session.commit()

            # Create PPV category
            ppv_category = Category(account_id=account.id, category_id="100", category_name="PPV EVENTS")
            db.session.add(ppv_category)

            # Create normal category
            normal_category = Category(account_id=account.id, category_id="200", category_name="US| SPORTS")
            db.session.add(normal_category)
            db.session.commit()

            # Create PPV channel
            ppv_channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="UFC 300 Main Event",
                category_id=ppv_category.id,
                is_active=True,
            )
            db.session.add(ppv_channel)

            # Create normal channel
            normal_channel = Channel(
                account_id=account.id, stream_id="2001", name="ESPN", category_id=normal_category.id, is_active=True
            )
            db.session.add(normal_channel)
            db.session.commit()

            # Create EPG source
            epg_source = EpgSource(
                name="Test EPG", source_type="xmltv_url", url="http://test.com/epg.xml", enabled=True
            )
            db.session.add(epg_source)
            db.session.commit()

            # Create EPG channel that could match
            epg_channel = EpgChannel(source_id=epg_source.id, channel_id="ESPN.us", display_name="ESPN")
            db.session.add(epg_channel)
            db.session.commit()

            # Run EPG matching
            stats = EpgService.match_channels_to_epg(account.id)

            # Check stats
            assert stats["skipped_ppv"] == 1, "PPV channel should be skipped"
            assert stats["total_channels"] == 2, "Should process both channels"

            # Check that PPV channel has no mapping
            ppv_mapping = ChannelEpgMapping.query.filter_by(channel_id=ppv_channel.id).first()
            assert ppv_mapping is None, "PPV channel should have no EPG mapping"

    def test_ppv_stats_in_response(self, app):
        """Test that PPV skip stats are included in matching response"""
        with app.app_context():
            account = Account(
                name="Test Account", server="http://test.com", username="user", password="pass", enabled=True
            )
            db.session.add(account)
            db.session.commit()

            # Create PPV category with multiple channels
            ppv_category = Category(account_id=account.id, category_id="100", category_name="PPV")
            db.session.add(ppv_category)
            db.session.commit()

            # Create multiple PPV channels
            for i in range(3):
                channel = Channel(
                    account_id=account.id,
                    stream_id=f"ppv_{i}",
                    name=f"PPV Event {i}",
                    category_id=ppv_category.id,
                    is_active=True,
                )
                db.session.add(channel)
            db.session.commit()

            # Run EPG matching
            stats = EpgService.match_channels_to_epg(account.id)

            # Verify PPV channels were skipped
            assert stats["skipped_ppv"] == 3, "All PPV channels should be skipped"
            assert stats["total_channels"] == 3
            assert stats["unmatched"] == 0, "PPV channels shouldn't count as unmatched"

    def test_filtered_channels_excluded_by_default(self, app):
        """Test that filtered out (is_visible=False) channels are not matched by default"""
        with app.app_context():
            account = Account(
                name="Test Account",
                server="http://test.com",
                username="user",
                password="pass",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="200", category_name="Sports")
            db.session.add(category)
            db.session.commit()

            # Create visible channel
            visible_channel = Channel(
                account_id=account.id,
                stream_id="2001",
                name="ESPN",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(visible_channel)

            # Create filtered out channels
            for i in range(3):
                channel = Channel(
                    account_id=account.id,
                    stream_id=f"200{i+2}",
                    name=f"Filtered Channel {i}",
                    category_id=category.id,
                    is_active=True,
                    is_visible=False,
                )
                db.session.add(channel)
            db.session.commit()

            # Create EPG source
            epg_source = EpgSource(name="Test EPG", source_type="xmltv_url", enabled=True)
            db.session.add(epg_source)
            db.session.commit()

            # Create EPG channel
            epg_channel = EpgChannel(source_id=epg_source.id, channel_id="ESPN.us", display_name="ESPN")
            db.session.add(epg_channel)
            db.session.commit()

            # Run EPG matching (default: include_filtered=False)
            stats = EpgService.match_channels_to_epg(account.id)

            # Should only process visible channel
            assert stats["total_channels"] == 1, "Should only process visible channel by default"

            # Run EPG matching with include_filtered=True
            stats_all = EpgService.match_channels_to_epg(account.id, include_filtered=True)

            # Should process all channels
            assert stats_all["total_channels"] == 4, "Should process all channels when include_filtered=True"
