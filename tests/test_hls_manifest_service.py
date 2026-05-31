"""Tests for HLS manifest URL rewriting."""

from services.hls_manifest_service import rewrite_hls_manifest


class TestRewriteHlsManifest:
    def test_rewrites_mediaflow_segment_urls_to_absolute_paths(self):
        manifest = """#EXTM3U
#EXT-X-VERSION:3
#EXTINF:10.0,
http://localhost:8888/proxy/stream?d=https%3A%2F%2Fprovider.example%2Fseg.ts&api_password=secret
"""
        rewritten = rewrite_hls_manifest(
            manifest,
            mediaflow_base_url="http://localhost:8888",
            public_proxy_base="http://iptv-proxy:8000",
        )

        assert "http://iptv-proxy:8000/stream/mediaflow/proxy/stream?d=" in rewritten
        assert "localhost:8888" not in rewritten

    def test_rewrites_uri_attributes(self):
        manifest = '#EXT-X-KEY:METHOD=AES-128,URI="http://localhost:8888/proxy/stream?d=key.bin"'
        rewritten = rewrite_hls_manifest(
            manifest,
            mediaflow_base_url="http://localhost:8888",
            public_proxy_base="http://iptv-proxy:8000",
        )

        assert rewritten == (
            '#EXT-X-KEY:METHOD=AES-128,URI="http://iptv-proxy:8000/stream/mediaflow/proxy/stream?d=key.bin"'
        )

    def test_rewrites_alternate_mediaflow_host(self):
        manifest = "http://mediaflow-proxy:8888/proxy/hls/manifest.m3u8?d=nested.m3u8"
        rewritten = rewrite_hls_manifest(
            manifest,
            mediaflow_base_url="http://localhost:8888",
            public_proxy_base="http://iptv-proxy:8000",
        )

        assert rewritten.startswith("http://iptv-proxy:8000/stream/mediaflow/proxy/hls/manifest.m3u8")

    def test_rewrites_public_host_proxy_urls(self):
        manifest = "http://iptv.stonecrusher.us/proxy/hls/segment.ts?" "d=http%3A%2F%2F185.245.1.20%2Fhls%2Fseg.ts"
        rewritten = rewrite_hls_manifest(
            manifest,
            mediaflow_base_url="http://mediaflow-proxy:8888",
            public_proxy_base="https://iptv.stonecrusher.us",
        )

        assert rewritten.startswith("https://iptv.stonecrusher.us/stream/mediaflow/proxy/hls/segment.ts")

    def test_fixes_hostname_only_relative_urls(self):
        manifest = (
            "iptv.stonecrusher.us/stream/mediaflow/proxy/hls/segment.ts?" "d=http%3A%2F%2F185.245.1.20%2Fhls%2Fseg.ts"
        )
        rewritten = rewrite_hls_manifest(
            manifest,
            mediaflow_base_url="http://mediaflow-proxy:8888",
            public_proxy_base="https://iptv.stonecrusher.us",
        )

        assert rewritten.startswith("https://iptv.stonecrusher.us/stream/mediaflow/proxy/hls/segment.ts")

    def test_uses_root_relative_paths_without_public_base(self):
        manifest = "http://localhost:8888/proxy/stream?d=https%3A%2F%2Fprovider.example%2Fseg.ts"
        rewritten = rewrite_hls_manifest(
            manifest,
            mediaflow_base_url="http://localhost:8888",
            public_proxy_base="",
        )

        assert rewritten.startswith("/stream/mediaflow/proxy/stream?d=")

    def test_leaves_upstream_urls_unchanged(self):
        manifest = "https://provider.example/live/segment.ts"
        rewritten = rewrite_hls_manifest(
            manifest,
            mediaflow_base_url="http://localhost:8888",
            public_proxy_base="http://iptv-proxy:8000",
        )

        assert rewritten == manifest

    def test_rewrites_root_relative_proxy_paths(self):
        manifest = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=5000000
/proxy/hls/manifest.m3u8?d=https%3A%2F%2Fprovider.example%2F1080.m3u8
/proxy/stream.ts?d=https%3A%2F%2Fprovider.example%2Fseg.ts
"""
        rewritten = rewrite_hls_manifest(
            manifest,
            mediaflow_base_url="http://mediaflow-proxy:8888",
            public_proxy_base="http://iptv-proxy:8000",
        )

        assert "http://iptv-proxy:8000/stream/mediaflow/proxy/hls/manifest.m3u8?d=" in rewritten
        assert "http://iptv-proxy:8000/stream/mediaflow/proxy/stream.ts?d=" in rewritten
        assert "/proxy/hls/" not in rewritten.replace("/stream/mediaflow/proxy/hls/", "")

    def test_rewrites_encrypted_token_proxy_paths(self):
        manifest = (
            "http://localhost:8888/_token_abc123/proxy/hls/manifest.m3u8?"
            "d=https%3A%2F%2Fprovider.example%2Fvariant.m3u8"
        )
        rewritten = rewrite_hls_manifest(
            manifest,
            mediaflow_base_url="http://localhost:8888",
            public_proxy_base="http://iptv-proxy:8000",
        )

        assert rewritten.startswith("http://iptv-proxy:8000/stream/mediaflow/_token_abc123/proxy/hls/manifest.m3u8")
        assert "localhost:8888" not in rewritten
