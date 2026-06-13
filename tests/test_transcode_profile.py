"""Tests for transcode profile and FFmpeg argument builder."""

import importlib

import pytest

import services.transcode_profile as transcode_profile_mod
from services.transcode_profile import TranscodeProfile, validate_transcode_fields


@pytest.fixture
def software_encoder(monkeypatch):
    monkeypatch.setenv("TRANSCODE_HWACCEL", "software")
    importlib.reload(transcode_profile_mod)
    transcode_profile_mod._encoder_mode = None
    yield transcode_profile_mod
    transcode_profile_mod._encoder_mode = None
    importlib.reload(transcode_profile_mod)


class TestTranscodeProfile:
    def test_fingerprint_stable_for_same_settings(self, software_encoder):
        p1 = TranscodeProfile(True, 720, 8000, 2, 128)
        p2 = TranscodeProfile(True, 720, 8000, 2, 128)
        assert p1.fingerprint() == p2.fingerprint()

    def test_fingerprint_differs_when_settings_change(self, software_encoder):
        p1 = TranscodeProfile(True, 720, 8000, 2, 128)
        p2 = TranscodeProfile(True, 480, 8000, 2, 128)
        assert p1.fingerprint() != p2.fingerprint()

    def test_build_ffmpeg_args_software_includes_libx264(self, software_encoder):
        profile = TranscodeProfile(True, 720, 8000, 2, 128)
        args = profile.build_ffmpeg_args("http://example.com/stream.ts", "test-ua")
        assert "libx264" in args
        assert "http://example.com/stream.ts" in args
        assert "test-ua" in args
        assert "mpegts" in args

    def test_from_xtream_credential_disabled_returns_none(self):
        class Cred:
            transcode_enabled = False

        assert TranscodeProfile.from_xtream_credential(Cred()) is None

    def test_from_xtream_credential_enabled(self):
        class Cred:
            transcode_enabled = True
            transcode_max_height = 720
            transcode_max_bitrate_kbps = 5000
            transcode_audio_channels = 2
            transcode_audio_bitrate_kbps = 96

        profile = TranscodeProfile.from_xtream_credential(Cred())
        assert profile is not None
        assert profile.max_bitrate_kbps == 5000


class TestValidateTranscodeFields:
    def test_invalid_height_raises(self):
        with pytest.raises(ValueError, match="transcode_max_height"):
            validate_transcode_fields(
                transcode_enabled=True,
                transcode_max_height=200,
                transcode_max_bitrate_kbps=8000,
                transcode_audio_channels=2,
                transcode_audio_bitrate_kbps=128,
            )

    def test_invalid_bitrate_raises(self):
        with pytest.raises(ValueError, match="transcode_max_bitrate"):
            validate_transcode_fields(
                transcode_enabled=True,
                transcode_max_height=720,
                transcode_max_bitrate_kbps=100,
                transcode_audio_channels=2,
                transcode_audio_bitrate_kbps=128,
            )
