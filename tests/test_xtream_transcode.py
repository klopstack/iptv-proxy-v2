"""Tests for Xtream transcode redirect behavior."""

from unittest.mock import MagicMock, patch

import pytest

from models import Account, XtreamCredential, db


@pytest.fixture
def xtream_cred_with_transcode(app):
    with app.app_context():
        account = Account(name="Test", server="example.com", username="u", password="p", enabled=True)
        db.session.add(account)
        db.session.flush()
        cred = XtreamCredential(
            username="rvuser",
            password="rvpass",
            account_id=account.id,
            transcode_enabled=True,
            transcode_max_height=720,
            transcode_max_bitrate_kbps=8000,
            enabled=True,
        )
        db.session.add(cred)
        db.session.commit()
        yield cred, account


def test_xtream_live_redirect_includes_xc_and_forces_ts(app, client, xtream_cred_with_transcode):
    cred, account = xtream_cred_with_transcode
    channel = MagicMock()
    channel.stream_id = "1001"
    channel.account_id = account.id

    with patch("routes.xtream.get_channel_for_credential_stream", return_value=channel):
        response = client.get(f"/live/{cred.username}/{cred.password}/1001.m3u8", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["Location"]
    assert f"/stream/{account.id}/1001.ts" in location
    assert f"xc={cred.id}" in location


def test_xtream_live_passthrough_keeps_format(app, client, xtream_cred_with_transcode):
    cred, account = xtream_cred_with_transcode
    cred.transcode_enabled = False
    db.session.commit()

    channel = MagicMock()
    channel.stream_id = "1001"
    channel.account_id = account.id

    with patch("routes.xtream.get_channel_for_credential_stream", return_value=channel):
        response = client.get(f"/live/{cred.username}/{cred.password}/1001.m3u8", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["Location"]
    assert "/1001.m3u8" in location
    assert f"xc={cred.id}" in location
