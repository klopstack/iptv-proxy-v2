"""
Tests for the QualityService - quality ranking and duplicate collapsing.
"""

from services.quality_service import QUALITY_RANKS, QualityService


class TestQualityScore:
    """Tests for get_quality_score function"""

    def test_empty_tags(self):
        """Empty tags should return 0 score"""
        assert QualityService.get_quality_score([]) == 0
        assert QualityService.get_quality_score(None) == 0

    def test_no_quality_tags(self):
        """Tags without quality indicators should return 0"""
        assert QualityService.get_quality_score(["US", "PRIME", "NEWS"]) == 0

    def test_single_quality_tag(self):
        """Single quality tag should return its rank"""
        assert QualityService.get_quality_score(["4K"]) == QUALITY_RANKS["4K"]
        assert QualityService.get_quality_score(["HD"]) == QUALITY_RANKS["HD"]
        assert QualityService.get_quality_score(["60FPS"]) == QUALITY_RANKS["60FPS"]
        assert QualityService.get_quality_score(["RAW"]) == QUALITY_RANKS["RAW"]

    def test_multiple_quality_tags_are_additive(self):
        """Multiple quality tags should have additive scores"""
        # RAW + 60FPS should score higher than either alone
        raw_score = QUALITY_RANKS["RAW"]
        fps60_score = QUALITY_RANKS["60FPS"]
        combined = QualityService.get_quality_score(["RAW", "60FPS"])
        assert combined == raw_score + fps60_score

        # 4K + RAW + 60FPS should be even higher
        score_4k = QUALITY_RANKS["4K"]
        full_combo = QualityService.get_quality_score(["4K", "RAW", "60FPS"])
        assert full_combo == score_4k + raw_score + fps60_score

    def test_mixed_quality_and_non_quality_tags(self):
        """Mixed tags should only consider quality tags"""
        score_4k = QUALITY_RANKS["4K"]
        assert QualityService.get_quality_score(["US", "4K", "PRIME"]) == score_4k
        score_hd = QUALITY_RANKS["HD"]
        assert QualityService.get_quality_score(["NEWS", "HD", "CNN"]) == score_hd

    def test_case_insensitivity(self):
        """Quality tags should be case-insensitive"""
        assert QualityService.get_quality_score(["4k"]) == QUALITY_RANKS["4K"]
        assert QualityService.get_quality_score(["hd"]) == QUALITY_RANKS["HD"]
        assert QualityService.get_quality_score(["Raw"]) == QUALITY_RANKS["RAW"]

    def test_framerate_hierarchy(self):
        """60FPS should score higher than 25FPS"""
        fps60 = QualityService.get_quality_score(["60FPS"])
        fps25 = QualityService.get_quality_score(["25FPS"])
        assert fps60 > fps25

    def test_raw_60fps_vs_plain_60fps(self):
        """RAW + 60FPS should score higher than just 60FPS"""
        raw_60 = QualityService.get_quality_score(["RAW", "60FPS"])
        plain_60 = QualityService.get_quality_score(["60FPS"])
        assert raw_60 > plain_60


class TestGetQualityTags:
    """Tests for get_quality_tags function"""

    def test_empty_tags(self):
        """Empty input returns empty list"""
        assert QualityService.get_quality_tags([]) == []

    def test_no_quality_tags(self):
        """Non-quality tags return empty list"""
        assert QualityService.get_quality_tags(["US", "PRIME"]) == []

    def test_extracts_quality_tags(self):
        """Should extract only quality-related tags"""
        result = QualityService.get_quality_tags(["US", "4K", "PRIME", "HD", "NEWS"])
        assert "4K" in result
        assert "HD" in result
        assert "US" not in result
        assert "PRIME" not in result


class TestCollapseDuplicates:
    """Tests for collapse_duplicates function"""

    def test_empty_list(self):
        """Empty list returns empty list"""
        assert QualityService.collapse_duplicates([]) == []

    def test_no_duplicates(self):
        """Unique channels are preserved"""
        channels = [
            {"name": "ESPN", "cleaned_name": "ESPN", "stream_id": "1", "tags": ["HD"]},
            {"name": "CNN", "cleaned_name": "CNN", "stream_id": "2", "tags": ["HD"]},
        ]
        result = QualityService.collapse_duplicates(channels)
        assert len(result) == 2

    def test_collapses_exact_duplicates(self):
        """Channels with same cleaned_name are collapsed"""
        channels = [
            {"name": "ESPN HD", "cleaned_name": "ESPN", "stream_id": "1", "tags": ["HD"]},
            {"name": "ESPN 4K", "cleaned_name": "ESPN", "stream_id": "2", "tags": ["4K"]},
            {"name": "ESPN RAW", "cleaned_name": "ESPN", "stream_id": "3", "tags": ["RAW"]},
        ]
        result = QualityService.collapse_duplicates(channels)
        assert len(result) == 1
        # Should keep 4K version (highest quality)
        assert result[0]["tags"] == ["4K"]
        assert result[0]["stream_id"] == "2"

    def test_keeps_highest_quality(self):
        """Should keep the highest quality version"""
        # Test RAW+HD vs plain HD - RAW adds quality bonus
        channels = [
            {"name": "ESPN HD", "cleaned_name": "ESPN", "stream_id": "1", "tags": ["HD"]},
            {"name": "ESPN RAW HD", "cleaned_name": "ESPN", "stream_id": "2", "tags": ["RAW", "HD"]},
        ]
        result = QualityService.collapse_duplicates(channels)
        assert len(result) == 1
        assert "RAW" in result[0]["tags"]

    def test_60fps_vs_25fps(self):
        """60FPS should be preferred over no-fps tag (25fps default)"""
        channels = [
            {"name": "ESPN", "cleaned_name": "ESPN", "stream_id": "1", "tags": ["HD"]},
            {"name": "ESPN 60FPS", "cleaned_name": "ESPN", "stream_id": "2", "tags": ["HD", "60FPS"]},
        ]
        result = QualityService.collapse_duplicates(channels)
        assert len(result) == 1
        assert "60FPS" in result[0]["tags"]

    def test_raw_60fps_vs_60fps(self):
        """RAW + 60FPS should be preferred over just 60FPS"""
        channels = [
            {"name": "ESPN 60FPS", "cleaned_name": "ESPN", "stream_id": "1", "tags": ["60FPS"]},
            {"name": "ESPN RAW 60FPS", "cleaned_name": "ESPN", "stream_id": "2", "tags": ["RAW", "60FPS"]},
        ]
        result = QualityService.collapse_duplicates(channels)
        assert len(result) == 1
        assert result[0]["tags"] == ["RAW", "60FPS"]

    def test_duplicate_count_metadata(self):
        """Collapsed channels should have duplicate_count metadata"""
        channels = [
            {"name": "ESPN HD", "cleaned_name": "ESPN", "stream_id": "1", "tags": ["HD"]},
            {"name": "ESPN 4K", "cleaned_name": "ESPN", "stream_id": "2", "tags": ["4K"]},
            {"name": "ESPN RAW", "cleaned_name": "ESPN", "stream_id": "3", "tags": ["RAW"]},
        ]
        result = QualityService.collapse_duplicates(channels)
        assert result[0]["duplicate_count"] == 2
        assert result[0]["collapsed_from"] is not None
        assert len(result[0]["collapsed_from"]) == 2

    def test_no_duplicate_count_for_single(self):
        """Single channels should have 0 duplicate_count"""
        channels = [
            {"name": "ESPN", "cleaned_name": "ESPN", "stream_id": "1", "tags": ["HD"]},
        ]
        result = QualityService.collapse_duplicates(channels)
        assert result[0]["duplicate_count"] == 0
        assert result[0]["collapsed_from"] is None

    def test_case_insensitive_grouping(self):
        """Cleaned names should be compared case-insensitively"""
        channels = [
            {"name": "ESPN HD", "cleaned_name": "ESPN", "stream_id": "1", "tags": ["HD"]},
            {"name": "espn 4K", "cleaned_name": "espn", "stream_id": "2", "tags": ["4K"]},
        ]
        result = QualityService.collapse_duplicates(channels)
        assert len(result) == 1

    def test_multiple_groups(self):
        """Multiple different channels should each keep their best"""
        channels = [
            {"name": "ESPN HD", "cleaned_name": "ESPN", "stream_id": "1", "tags": ["HD"]},
            {"name": "ESPN 4K", "cleaned_name": "ESPN", "stream_id": "2", "tags": ["4K"]},
            {"name": "CNN HD", "cleaned_name": "CNN", "stream_id": "3", "tags": ["HD"]},
            # RAW + HD beats plain HD (35 + 40 = 75 vs 40)
            {"name": "CNN RAW HD", "cleaned_name": "CNN", "stream_id": "4", "tags": ["RAW", "HD"]},
        ]
        result = QualityService.collapse_duplicates(channels)
        assert len(result) == 2

        # Find ESPN and CNN in result
        espn = next((ch for ch in result if "espn" in ch["cleaned_name"].lower()), None)
        cnn = next((ch for ch in result if "cnn" in ch["cleaned_name"].lower()), None)

        assert espn is not None
        assert cnn is not None
        assert espn["tags"] == ["4K"]  # 4K is highest for ESPN
        assert set(cnn["tags"]) == {"RAW", "HD"}  # RAW+HD (75) beats plain HD (40)

    def test_uses_name_when_no_cleaned_name(self):
        """Falls back to name when cleaned_name is missing"""
        channels = [
            {"name": "ESPN HD", "stream_id": "1", "tags": ["HD"]},
            {"name": "ESPN HD", "stream_id": "2", "tags": ["4K"]},
        ]
        result = QualityService.collapse_duplicates(channels)
        assert len(result) == 1
        assert result[0]["tags"] == ["4K"]


class TestSortByQuality:
    """Tests for sort_by_quality function"""

    def test_empty_list(self):
        """Empty list returns empty list"""
        assert QualityService.sort_by_quality([]) == []

    def test_sorts_descending(self):
        """Should sort highest quality first"""
        channels = [
            {"name": "ESPN HD", "tags": ["HD"]},
            {"name": "ESPN 4K", "tags": ["4K"]},
            {"name": "ESPN SD", "tags": []},
        ]
        result = QualityService.sort_by_quality(channels)
        assert result[0]["name"] == "ESPN 4K"
        assert result[1]["name"] == "ESPN HD"
        assert result[2]["name"] == "ESPN SD"


class TestGetDuplicatesInfo:
    """Tests for get_duplicates_info function"""

    def test_empty_list(self):
        """Empty list returns zeros"""
        result = QualityService.get_duplicates_info([])
        assert result["total_channels"] == 0
        assert result["unique_channels"] == 0
        assert result["duplicate_count"] == 0
        assert result["duplicate_groups"] == []

    def test_no_duplicates(self):
        """No duplicates returns correct counts"""
        channels = [
            {"name": "ESPN", "cleaned_name": "ESPN", "stream_id": "1", "tags": ["HD"]},
            {"name": "CNN", "cleaned_name": "CNN", "stream_id": "2", "tags": ["HD"]},
        ]
        result = QualityService.get_duplicates_info(channels)
        assert result["total_channels"] == 2
        assert result["unique_channels"] == 2
        assert result["duplicate_count"] == 0
        assert result["duplicate_groups"] == []

    def test_with_duplicates(self):
        """Duplicates are correctly identified"""
        channels = [
            {"name": "ESPN HD", "cleaned_name": "ESPN", "stream_id": "1", "tags": ["HD"]},
            {"name": "ESPN 4K", "cleaned_name": "ESPN", "stream_id": "2", "tags": ["4K"]},
            {"name": "CNN", "cleaned_name": "CNN", "stream_id": "3", "tags": ["HD"]},
        ]
        result = QualityService.get_duplicates_info(channels)
        assert result["total_channels"] == 3
        assert result["unique_channels"] == 2
        assert result["duplicate_count"] == 1
        assert len(result["duplicate_groups"]) == 1

        # Check the duplicate group
        group = result["duplicate_groups"][0]
        assert group["count"] == 2
        assert len(group["channels"]) == 2

        # Best should be marked
        best = next(ch for ch in group["channels"] if ch["is_best"])
        assert best["tags"] == ["4K"]
