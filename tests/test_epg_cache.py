"""
Tests for services/epg/cache.py

Tests the EPG XML cache service including:
- Saving and loading cached EPG data
- Cache metadata operations
- Cache validity checking
- Cache cleanup operations
"""
import gzip
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Sample EPG XML for testing
SAMPLE_EPG_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<tv generator-info-name="test">
  <channel id="ch1">
    <display-name>Channel 1</display-name>
  </channel>
  <programme start="20260106120000 +0000" stop="20260106130000 +0000" channel="ch1">
    <title>Test Show</title>
  </programme>
</tv>
"""


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_cache_dir(temp_cache_dir):
    """Mock the EPG cache directory to use temp directory."""
    with patch.dict(os.environ, {"EPG_CACHE_DIR": temp_cache_dir}):
        yield temp_cache_dir


class TestGetCacheDir:
    """Tests for get_cache_dir function."""

    def test_creates_directory_if_not_exists(self, temp_cache_dir):
        """Test that cache directory is created if it doesn't exist."""
        from services.epg.cache import get_cache_dir

        new_dir = os.path.join(temp_cache_dir, "new_subdir")
        with patch.dict(os.environ, {"EPG_CACHE_DIR": new_dir}):
            result = get_cache_dir()
            assert result.exists()
            assert result == Path(new_dir)

    def test_returns_existing_directory(self, mock_cache_dir):
        """Test that existing directory is returned correctly."""
        from services.epg.cache import get_cache_dir

        result = get_cache_dir()
        assert result.exists()
        assert str(result) == mock_cache_dir


class TestGetCachePaths:
    """Tests for cache path functions."""

    def test_get_cache_path(self, mock_cache_dir):
        """Test get_cache_path returns correct path."""
        from services.epg.cache import get_cache_path

        path = get_cache_path(123)
        assert path.name == "epg_source_123.xml.gz"
        assert str(path.parent) == mock_cache_dir

    def test_get_cache_meta_path(self, mock_cache_dir):
        """Test get_cache_meta_path returns correct path."""
        from services.epg.cache import get_cache_meta_path

        path = get_cache_meta_path(456)
        assert path.name == "epg_source_456.meta"
        assert str(path.parent) == mock_cache_dir


class TestSaveToCache:
    """Tests for save_to_cache function."""

    def test_save_basic(self, mock_cache_dir):
        """Test basic cache save operation."""
        from services.epg.cache import get_cache_path, save_to_cache

        result = save_to_cache(1, SAMPLE_EPG_XML)

        assert result is True

        # Verify file exists and is gzipped
        cache_path = get_cache_path(1)
        assert cache_path.exists()

        # Verify content can be decompressed
        compressed = cache_path.read_bytes()
        decompressed = gzip.decompress(compressed)
        assert decompressed == SAMPLE_EPG_XML

    def test_save_creates_metadata(self, mock_cache_dir):
        """Test that save creates metadata file."""
        from services.epg.cache import get_cache_meta_path, save_to_cache

        save_to_cache(2, SAMPLE_EPG_XML)

        meta_path = get_cache_meta_path(2)
        assert meta_path.exists()

        meta = json.loads(meta_path.read_text())
        assert meta["source_id"] == 2
        assert meta["original_size"] == len(SAMPLE_EPG_XML)
        assert "content_hash" in meta
        assert "cached_at" in meta

    def test_save_returns_false_on_error(self, mock_cache_dir):
        """Test that save returns False on write error."""
        from services.epg.cache import save_to_cache

        # Make directory read-only to cause write error
        os.chmod(mock_cache_dir, 0o444)

        try:
            result = save_to_cache(3, SAMPLE_EPG_XML)
            assert result is False
        finally:
            # Restore permissions
            os.chmod(mock_cache_dir, 0o755)


class TestLoadFromCache:
    """Tests for load_from_cache function."""

    def test_load_existing_cache(self, mock_cache_dir):
        """Test loading existing cached data."""
        from services.epg.cache import load_from_cache, save_to_cache

        # Save first
        save_to_cache(1, SAMPLE_EPG_XML)

        # Load
        result = load_from_cache(1)

        assert result == SAMPLE_EPG_XML

    def test_load_nonexistent_cache(self, mock_cache_dir):
        """Test loading non-existent cache returns None."""
        from services.epg.cache import load_from_cache

        result = load_from_cache(999)
        assert result is None

    def test_load_corrupt_cache(self, mock_cache_dir):
        """Test loading corrupt cache returns None."""
        from services.epg.cache import get_cache_path, load_from_cache

        # Write invalid gzip data
        cache_path = get_cache_path(4)
        cache_path.write_bytes(b"not valid gzip data")

        result = load_from_cache(4)
        assert result is None


class TestGetCacheInfo:
    """Tests for get_cache_info function."""

    def test_get_info_existing(self, mock_cache_dir):
        """Test getting info for existing cache."""
        from services.epg.cache import get_cache_info, save_to_cache

        save_to_cache(1, SAMPLE_EPG_XML)

        info = get_cache_info(1)

        assert info is not None
        assert info["source_id"] == 1
        assert info["original_size"] == len(SAMPLE_EPG_XML)
        assert "compressed_size" in info
        assert "content_hash" in info

    def test_get_info_nonexistent(self, mock_cache_dir):
        """Test getting info for non-existent cache."""
        from services.epg.cache import get_cache_info

        info = get_cache_info(999)
        assert info is None


class TestIsCacheValid:
    """Tests for is_cache_valid function."""

    def test_valid_cache(self, mock_cache_dir):
        """Test that recent cache is valid."""
        from services.epg.cache import is_cache_valid, save_to_cache

        save_to_cache(1, SAMPLE_EPG_XML)

        result = is_cache_valid(1, max_age_hours=24)
        assert result is True

    def test_expired_cache(self, mock_cache_dir):
        """Test that old cache is invalid."""
        from services.epg.cache import get_cache_meta_path, is_cache_valid, save_to_cache

        save_to_cache(1, SAMPLE_EPG_XML)

        # Modify metadata to show old timestamp
        meta_path = get_cache_meta_path(1)
        meta = json.loads(meta_path.read_text())
        old_time = datetime.now(timezone.utc) - timedelta(hours=48)
        meta["cached_at"] = old_time.isoformat()
        meta_path.write_text(json.dumps(meta))

        result = is_cache_valid(1, max_age_hours=24)
        assert result is False

    def test_nonexistent_cache_invalid(self, mock_cache_dir):
        """Test that non-existent cache is invalid."""
        from services.epg.cache import is_cache_valid

        result = is_cache_valid(999, max_age_hours=24)
        assert result is False


class TestDeleteCache:
    """Tests for delete_cache function."""

    def test_delete_existing(self, mock_cache_dir):
        """Test deleting existing cache."""
        from services.epg.cache import delete_cache, get_cache_meta_path, get_cache_path, save_to_cache

        save_to_cache(1, SAMPLE_EPG_XML)

        # Verify files exist
        assert get_cache_path(1).exists()
        assert get_cache_meta_path(1).exists()

        result = delete_cache(1)

        assert result is True
        assert not get_cache_path(1).exists()
        assert not get_cache_meta_path(1).exists()

    def test_delete_nonexistent(self, mock_cache_dir):
        """Test deleting non-existent cache succeeds."""
        from services.epg.cache import delete_cache

        result = delete_cache(999)
        assert result is True


class TestClearAllCache:
    """Tests for clear_all_cache function."""

    def test_clear_multiple_caches(self, mock_cache_dir):
        """Test clearing all cached data."""
        from services.epg.cache import clear_all_cache, get_cache_path, save_to_cache

        # Save multiple caches
        save_to_cache(1, SAMPLE_EPG_XML)
        save_to_cache(2, SAMPLE_EPG_XML)
        save_to_cache(3, SAMPLE_EPG_XML)

        deleted = clear_all_cache()

        assert deleted >= 6  # 3 data files + 3 meta files
        assert not get_cache_path(1).exists()
        assert not get_cache_path(2).exists()
        assert not get_cache_path(3).exists()

    def test_clear_empty_cache(self, mock_cache_dir):
        """Test clearing empty cache dir."""
        from services.epg.cache import clear_all_cache

        deleted = clear_all_cache()
        assert deleted == 0


class TestGetCacheStats:
    """Tests for get_cache_stats function."""

    def test_stats_with_data(self, mock_cache_dir):
        """Test getting stats with cached data."""
        from services.epg.cache import get_cache_stats, save_to_cache

        # Save some caches
        save_to_cache(1, SAMPLE_EPG_XML)
        save_to_cache(2, SAMPLE_EPG_XML * 2)  # Larger

        stats = get_cache_stats()

        assert stats["cache_dir"] == mock_cache_dir
        assert stats["file_count"] == 2
        assert stats["total_size_bytes"] > 0
        assert stats["total_size_mb"] >= 0
        assert stats["oldest_cache"] is not None
        assert stats["newest_cache"] is not None
        assert stats["oldest_cache"].endswith("Z")
        assert stats["newest_cache"].endswith("Z")

    def test_stats_empty_cache(self, mock_cache_dir):
        """Test getting stats for empty cache."""
        from services.epg.cache import get_cache_stats

        stats = get_cache_stats()

        assert stats["file_count"] == 0
        assert stats["total_size_bytes"] == 0
        assert stats["oldest_cache"] is None
        assert stats["newest_cache"] is None
