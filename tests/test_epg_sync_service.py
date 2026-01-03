"""
Tests for EpgSyncService - EPG source synchronization dispatcher

Tests the dispatcher logic that routes to correct sync methods.
Individual sync methods are integration tests tested via route tests.
"""
from unittest.mock import Mock

from services.epg_sync_service import EpgSyncService


class TestSyncSourceDispatcher:
    """Test the dispatcher method that routes to correct sync method"""

    def test_sync_source_handles_invalid_type(self):
        """Invalid source type returns error"""
        source = Mock()
        source.source_type = "invalid_type"

        success, message, stats = EpgSyncService.sync_source(source)

        assert success is False
        assert "unknown" in message.lower()

    def test_sync_source_handles_none_type(self):
        """None source type returns error"""
        source = Mock()
        source.source_type = None

        success, message, stats = EpgSyncService.sync_source(source)

        assert success is False
