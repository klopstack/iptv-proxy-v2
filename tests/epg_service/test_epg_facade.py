"""Tests for EpgService facade delegation to coverage and related modules."""
import pytest

from models import Category, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db
from services.epg import EpgService

class TestGetEpgCoverageStats:
    """Tests for EpgService.get_epg_coverage_stats"""

    def test_empty_database(self, app):
        """Test coverage stats with empty database"""
        with app.app_context():
            stats = EpgService.get_epg_coverage_stats()
            assert stats["total_channels"] == 0
            assert stats["channels_with_epg_mapping"] == 0
            assert stats["coverage_percent"] == 0

    def test_coverage_with_channels(self, app, test_account, test_epg_source):
        """Test coverage stats with channels and mappings"""
        with app.app_context():
            # Create a channel
            category = Category(
                account_id=test_account,
                category_id="cat1",
                category_name="Test",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=test_account,
                stream_id="ch1",
                name="Test Channel",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.flush()

            # Create EPG channel
            source = db.session.get(EpgSource, test_epg_source.id)
            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="epg_ch1",
                display_name="EPG Channel",
            )
            db.session.add(epg_channel)
            db.session.flush()

            # Create mapping
            mapping = ChannelEpgMapping(
                channel_id=channel.id,
                epg_channel_id=epg_channel.id,
                mapping_type="manual",
                confidence=1.0,
            )
            db.session.add(mapping)
            db.session.commit()

            stats = EpgService.get_epg_coverage_stats()
            assert stats["total_channels"] >= 1
            assert stats["channels_with_epg_mapping"] >= 1
            assert stats["epg_sources"] >= 1


# ============================================================================
# Channel Matching Tests
# ============================================================================


