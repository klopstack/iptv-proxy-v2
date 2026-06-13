"""Tests for transcode stream service stream keys and integration."""

import subprocess
from pathlib import Path

import pytest

from services.transcode_profile import TranscodeProfile
from services.transcode_stream_service import TranscodeStreamService

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_CLIP_PATH = FIXTURES_DIR / "test_clip.ts"


@pytest.fixture(scope="module")
def test_video():
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    if TEST_CLIP_PATH.exists():
        return TEST_CLIP_PATH
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=3:size=640x480:rate=30",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=1000:duration=3",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        "-f",
        "mpegts",
        str(TEST_CLIP_PATH),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0 or not TEST_CLIP_PATH.exists():
        pytest.skip("Could not generate test clip")
    return TEST_CLIP_PATH


@pytest.fixture
def software_profile(monkeypatch):
    monkeypatch.setenv("TRANSCODE_HWACCEL", "software")
    import importlib

    import services.transcode_profile as tp

    importlib.reload(tp)
    tp._encoder_mode = None
    return TranscodeProfile(True, 480, 2000, 2, 64)


class TestTranscodeStreamKeys:
    def test_transcode_key_includes_profile_fingerprint(self, software_profile):
        service = TranscodeStreamService()
        key = service._get_stream_key(1, "12345", software_profile)
        assert key.startswith("1:12345:ts:t:")
        assert software_profile.fingerprint() in key

    def test_passthrough_and_transcode_keys_differ(self, software_profile):
        from services.mediaflow_stream_service import MediaFlowStreamService

        mf = MediaFlowStreamService()
        transcode = TranscodeStreamService()
        assert mf._get_stream_key(1, "12345", "ts") != transcode._get_stream_key(1, "12345", software_profile)


@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not available",
)
class TestTranscodeStreamIntegration:
    def test_transcode_produces_mpegts_output(self, software_profile, test_video, tmp_path):
        service = TranscodeStreamService()
        service.start()

        upstream = str(test_video)
        try:
            stream, subscriber = service.subscribe(
                account_id=1,
                stream_id="test",
                format="ts",
                upstream_url=upstream,
                credential_id=1,
                session_token="sess",
                transcode_profile=software_profile,
                user_agent="test",
            )
            output = tmp_path / "out.ts"
            chunks = 0
            with open(output, "wb") as f:
                for chunk in service.stream_chunks(stream, subscriber):
                    f.write(chunk)
                    chunks += 1
                    if chunks > 20:
                        break
            service.unsubscribe(stream, subscriber)
            assert output.stat().st_size > 0
        finally:
            service.stop()
