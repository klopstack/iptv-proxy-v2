"""Tests for TextProcessor component."""

from services.reverse_event_matcher.text_processor import TextProcessor


class TestTextProcessor:
    """Test suite for TextProcessor."""

    def test_normalize_text_basic(self):
        """Test basic text normalization."""
        processor = TextProcessor()

        # Basic normalization: lowercase, remove punctuation, normalize whitespace
        assert processor.normalize_text("HELLO WORLD") == "hello world"
        assert processor.normalize_text("Hello, World!") == "hello world"
        assert processor.normalize_text("  Multiple   Spaces  ") == "multiple spaces"

    def test_normalize_text_timestamps(self):
        """Test removal of timestamps."""
        processor = TextProcessor()

        # Start timestamp
        text = "Lakers vs Celtics start:2025-12-28 01:55:00"
        result = processor.normalize_text(text)
        assert "2025" not in result
        assert "01:55:00" not in result
        assert "lakers" in result
        assert "celtics" in result

        # Stop timestamp
        text = "Event stop:2025-12-28 07:00:00"
        result = processor.normalize_text(text)
        assert "2025" not in result
        assert "07:00:00" not in result

    def test_normalize_text_timezones(self):
        """Test removal of timezone indicators."""
        processor = TextProcessor()

        # Multi-timezone format
        text = "Fight at 11PM UK / 6PM ET / 3PM PT"
        result = processor.normalize_text(text)
        assert "uk" not in result
        assert "et" not in result
        assert "pt" not in result
        assert "fight" in result

        # Standalone timezone abbreviations
        text = "Game UTC at stadium"
        result = processor.normalize_text(text)
        assert "utc" not in result
        assert "game" in result
        assert "stadium" in result

    def test_normalize_text_dates(self):
        """Test removal of date patterns."""
        processor = TextProcessor()

        # ISO date
        text = "Event on 2025-12-28 at venue"
        result = processor.normalize_text(text)
        assert "2025" not in result
        assert "event" in result
        assert "venue" in result

        # Time format
        text = "Match at 3:30pm today"
        result = processor.normalize_text(text)
        assert "3:30" not in result
        assert "match" in result
        assert "today" in result

    def test_normalize_text_caching(self):
        """Test that caching works correctly."""
        processor = TextProcessor()

        text = "LAKERS VS CELTICS"
        cache_key = "test1"

        # First call should normalize and cache
        result1 = processor.normalize_text(text, cache_key=cache_key)
        assert result1 == "lakers vs celtics"

        # Second call should return cached result
        result2 = processor.normalize_text(text, cache_key=cache_key)
        assert result2 == result1

        # Verify cache contains the key
        stats = processor.get_cache_stats()
        assert stats["normalized_cache_size"] == 1

    def test_normalize_text_empty_input(self):
        """Test handling of empty/None input."""
        processor = TextProcessor()

        assert processor.normalize_text("") == ""
        assert processor.normalize_text("   ") == ""

    def test_extract_significant_words_basic(self):
        """Test basic word extraction."""
        processor = TextProcessor()

        text = "Lakers vs Celtics at stadium"
        words = processor.extract_significant_words(text)

        # Should include significant words (length >= 4)
        assert "lakers" in words
        assert "celtics" in words
        assert "stadium" in words

        # Should exclude short words and stop words
        assert "vs" not in words  # Too short
        assert "at" not in words  # Stop word

    def test_extract_significant_words_stop_words(self):
        """Test that stop words are filtered out."""
        processor = TextProcessor()

        text = "The lakers celtics is on ESPN with home stadium"
        words = processor.extract_significant_words(text)

        # Stop words should be excluded
        assert "the" not in words
        assert "is" not in words
        assert "on" not in words
        assert "with" not in words
        assert "home" not in words
        assert "espn" not in words  # Network name

        # Significant words should be included
        assert "lakers" in words
        assert "celtics" in words
        assert "stadium" in words

    def test_extract_significant_words_min_length(self):
        """Test minimum word length filtering."""
        processor = TextProcessor()

        text = "a an the cat dog bird elephant"
        words = processor.extract_significant_words(text)

        # Words < 4 chars should be excluded
        assert "a" not in words
        assert "an" not in words
        assert "the" not in words
        assert "cat" not in words
        assert "dog" not in words

        # Words >= 4 chars should be included
        assert "bird" in words
        assert "elephant" in words

    def test_extract_significant_words_caching(self):
        """Test word extraction caching."""
        processor = TextProcessor()

        text = "LAKERS CELTICS WARRIORS"
        cache_key = "test2"

        # First call should extract and cache
        words1 = processor.extract_significant_words(text, cache_key=cache_key)
        assert "lakers" in words1
        assert "celtics" in words1
        assert "warriors" in words1

        # Second call should return cached result
        words2 = processor.extract_significant_words(text, cache_key=cache_key)
        assert words2 == words1

        # Verify cache contains the key
        stats = processor.get_cache_stats()
        assert stats["words_cache_size"] == 1

    def test_clear_cache(self):
        """Test cache clearing."""
        processor = TextProcessor()

        # Add some cached items
        processor.normalize_text("test1", cache_key="key1")
        processor.extract_significant_words("test2", cache_key="key2")

        stats = processor.get_cache_stats()
        assert stats["normalized_cache_size"] == 1
        assert stats["words_cache_size"] == 1

        # Clear caches
        processor.clear_cache()

        stats = processor.get_cache_stats()
        assert stats["normalized_cache_size"] == 0
        assert stats["words_cache_size"] == 0

    def test_real_world_channel_names(self):
        """Test with real-world messy channel names."""
        processor = TextProcessor()

        # Complex channel with timestamps and timezones
        channel = (
            "US: UFC 300 - SERRANO VS TELLEZ "
            "start:2025-12-28 01:55:00 stop:2025-12-28 07:00:00 "
            "11PM UK / 6PM ET / 3PM PT"
        )

        normalized = processor.normalize_text(channel)
        words = processor.extract_significant_words(channel)

        # Should extract meaningful content
        assert "serrano" in words
        assert "tellez" in words

        # Should remove metadata
        assert "start" not in normalized
        assert "2025" not in normalized
        assert "11pm" not in normalized

        # Stop words and short words should be excluded
        assert "vs" not in words
        assert "the" not in words

    def test_normalization_consistency(self):
        """Test that normalization is consistent."""
        processor = TextProcessor()

        # Different formats of same content
        text1 = "Lakers vs. Celtics"
        text2 = "LAKERS VS CELTICS"
        text3 = "Lakers  vs  Celtics"

        result1 = processor.normalize_text(text1)
        result2 = processor.normalize_text(text2)
        result3 = processor.normalize_text(text3)

        # All should normalize to same result
        assert result1 == result2 == result3 == "lakers vs celtics"
