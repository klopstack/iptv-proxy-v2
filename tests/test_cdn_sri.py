"""Tests for CDN Subresource Integrity on admin templates."""

from pathlib import Path

BASE_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "base.html"

CDN_ASSETS = (
    "bootstrap@5.3.0/dist/css/bootstrap.min.css",
    "bootstrap-icons@1.11.0/font/bootstrap-icons.css",
    "bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js",
)


def test_base_template_cdn_assets_have_sri():
    content = BASE_TEMPLATE.read_text(encoding="utf-8")
    for asset in CDN_ASSETS:
        assert asset in content
        start = content.index(asset)
        tag = content.rfind("<", 0, start)
        tag_end = content.index(">", start)
        snippet = content[tag:tag_end]
        assert 'integrity="sha384-' in snippet
        assert 'crossorigin="anonymous"' in snippet
