"""Tests for upstream VOD passthrough helpers."""

from services.xtream_vod_service import rewrite_vod_stream_icons, vod_passthrough_available


class DummyAccount:
    def __init__(self, *, enabled=True):
        self.enabled = enabled


def test_vod_passthrough_available_requires_account_link():
    account = DummyAccount()
    assert vod_passthrough_available(vod_passthrough=True, account=account, account_id=1)
    assert not vod_passthrough_available(vod_passthrough=True, account=account, account_id=None)
    assert not vod_passthrough_available(vod_passthrough=False, account=account, account_id=1)
    assert not vod_passthrough_available(
        vod_passthrough=True,
        account=DummyAccount(enabled=False),
        account_id=1,
    )


def test_rewrite_vod_stream_icons_proxies_cover(monkeypatch):
    class FakeCache:
        def get_proxy_url(self, url, proxy_base):
            return f"{proxy_base}/icon?url={url}"

    monkeypatch.setattr(
        "services.xtream_vod_service.ImageCacheService.get_instance",
        lambda: FakeCache(),
    )

    streams = [{"stream_id": 1, "name": "Movie", "stream_icon": "http://cdn/icon.png", "cover": "http://cdn/icon.png"}]
    rewritten = rewrite_vod_stream_icons(streams, proxy_base="http://proxy")

    assert rewritten[0]["stream_icon"] == "http://proxy/icon?url=http://cdn/icon.png"
    assert rewritten[0]["cover"] == rewritten[0]["stream_icon"]
