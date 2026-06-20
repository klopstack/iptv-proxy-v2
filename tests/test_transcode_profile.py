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


@pytest.fixture
def vaapi_encoder(monkeypatch):
    monkeypatch.setenv("TRANSCODE_HWACCEL", "vaapi")
    importlib.reload(transcode_profile_mod)
    transcode_profile_mod._encoder_mode = "vaapi"
    yield transcode_profile_mod
    transcode_profile_mod._encoder_mode = None
    importlib.reload(transcode_profile_mod)


@pytest.fixture
def qsv_encoder(monkeypatch):
    monkeypatch.setenv("TRANSCODE_HWACCEL", "qsv")
    importlib.reload(transcode_profile_mod)
    transcode_profile_mod._encoder_mode = "qsv"
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
        assert "+genpts+discardcorrupt" in args
        assert "resend_headers" in " ".join(args)
        assert "48000" in args

    def test_build_ffmpeg_args_vaapi_uses_sw_decode_hw_encode(self, vaapi_encoder):
        profile = TranscodeProfile(True, 720, 8000, 2, 128)
        args = profile.build_ffmpeg_args("http://example.com/stream.ts", "test-ua")
        joined = " ".join(args)
        assert "h264_vaapi" in args
        assert "hwupload" in joined
        assert "-hwaccel" not in args
        assert "-init_hw_device" in args
        assert "vaapi=va:" in joined

    def test_build_ffmpeg_args_qsv_uses_vaapi_parent_and_hwupload_pool(self, qsv_encoder):
        profile = TranscodeProfile(True, 720, 8000, 2, 128)
        args = profile.build_ffmpeg_args("http://example.com/stream.ts", "test-ua")
        joined = " ".join(args)
        assert "h264_qsv" in args
        assert "qsv=hw@va" in joined
        assert "extra_hw_frames=" in joined
        assert "format=qsv" in joined
        assert "scale=w=-2:h=min(ih\\,720)" in joined
        assert "scale_qsv" not in joined
        assert "-hwaccel" not in args
        assert "-preset" in args
        assert args[args.index("-preset") + 1] == "veryfast"

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


class TestDetectEncoderMode:
    def test_auto_prefers_qsv_when_both_available(self, monkeypatch):
        monkeypatch.setenv("TRANSCODE_HWACCEL", "auto")
        importlib.reload(transcode_profile_mod)
        transcode_profile_mod._encoder_mode = None
        monkeypatch.setattr(transcode_profile_mod, "_probe_qsv_encoder", lambda: True)
        monkeypatch.setattr(transcode_profile_mod, "_probe_vaapi_encoder", lambda: True)
        assert transcode_profile_mod.get_encoder_mode() == "qsv"

    def test_auto_falls_back_to_vaapi_when_qsv_unavailable(self, monkeypatch):
        monkeypatch.setenv("TRANSCODE_HWACCEL", "auto")
        importlib.reload(transcode_profile_mod)
        transcode_profile_mod._encoder_mode = None
        monkeypatch.setattr(transcode_profile_mod, "_probe_qsv_encoder", lambda: False)
        monkeypatch.setattr(transcode_profile_mod, "_probe_vaapi_encoder", lambda: True)
        assert transcode_profile_mod.get_encoder_mode() == "vaapi"

    def test_qsv_mode_does_not_select_vaapi(self, monkeypatch):
        monkeypatch.setenv("TRANSCODE_HWACCEL", "qsv")
        importlib.reload(transcode_profile_mod)
        transcode_profile_mod._encoder_mode = None
        monkeypatch.setattr(transcode_profile_mod, "_probe_qsv_encoder", lambda: False)
        monkeypatch.setattr(transcode_profile_mod, "_probe_vaapi_encoder", lambda: True)
        assert transcode_profile_mod.get_encoder_mode() == "software"


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
