"""Tests for the memory/cache stats collector used by the dashboard summary."""

from unittest.mock import patch

import services.memory_stats as memory_stats


def test_get_process_rss_bytes_returns_int_or_none():
    rss = memory_stats.get_process_rss_bytes()
    assert rss is None or (isinstance(rss, int) and rss > 0)


def test_build_memory_stats_shape(app):
    with app.app_context():
        stats = memory_stats.build_memory_stats()

    assert "process" in stats
    assert "caches" in stats
    assert "rss_bytes" in stats["process"]
    assert "pid" in stats["process"]

    caches = stats["caches"]
    for key in ("iptv", "calendar", "reverse_matcher", "sportsipy", "context", "sofascore", "streams"):
        assert key in caches


def test_build_memory_stats_isolates_collector_failures(app):
    with app.app_context():
        with patch.object(memory_stats, "_calendar_cache_stats", side_effect=RuntimeError("boom")):
            stats = memory_stats.build_memory_stats()

    assert stats["caches"]["calendar"] == {"error": "boom"}
    # Other collectors still populate normally.
    assert "total_entries" in stats["caches"]["iptv"]


def test_stream_stats_without_active_service():
    """Stream stats report zeros when no stream service singleton exists."""
    import services.mediaflow_stream_service as mediaflow_mod
    import services.transcode_stream_service as transcode_mod

    with patch.object(mediaflow_mod, "_mediaflow_service", None), patch.object(
        transcode_mod, "_transcode_service", None
    ):
        result = memory_stats._stream_stats()

    assert result == {"active_streams": 0, "total_subscribers": 0}
