"""Tests for transcode stream service stream keys and integration."""

import shutil
import subprocess
from pathlib import Path

import pytest

from services.transcode_profile import TranscodeProfile
from services.transcode_stream_service import TranscodeStreamService

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_CLIP_PATH = FIXTURES_DIR / "test_clip.ts"
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


@pytest.fixture(scope="module")
def test_video():
    if not FFMPEG_AVAILABLE:
        pytest.skip("ffmpeg not available")
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


class TestTranscodeChunkSize:
    def test_default_transcode_chunk_size(self, monkeypatch):
        monkeypatch.delenv("TRANSCODE_CHUNK_SIZE", raising=False)
        import importlib

        import services.transcode_stream_service as tss

        importlib.reload(tss)
        assert tss.TRANSCODE_CHUNK_SIZE == 8192

    def test_transcode_chunk_size_from_env(self, monkeypatch):
        monkeypatch.setenv("TRANSCODE_CHUNK_SIZE", "4096")
        import importlib

        import services.transcode_stream_service as tss

        importlib.reload(tss)
        assert tss.TRANSCODE_CHUNK_SIZE == 4096

    @pytest.mark.parametrize("invalid_value", ["not-a-number", "0", "-1"])
    def test_transcode_chunk_size_invalid_env_falls_back_to_default(self, monkeypatch, invalid_value):
        monkeypatch.setenv("TRANSCODE_CHUNK_SIZE", invalid_value)
        import importlib

        import services.transcode_stream_service as tss

        importlib.reload(tss)
        assert tss.TRANSCODE_CHUNK_SIZE == 8192

    def test_ffmpeg_popen_uses_transcode_chunk_size(self, monkeypatch, software_profile):
        monkeypatch.setenv("TRANSCODE_CHUNK_SIZE", "4096")
        import importlib

        import services.transcode_stream_service as tss

        importlib.reload(tss)

        captured = {}

        class FakeStdout:
            def read(self, size):
                return b""

        class FakeProcess:
            stdout = FakeStdout()
            stderr = None

            def poll(self):
                return 0

            def terminate(self):
                pass

            def wait(self, timeout=None):
                return 0

        def fake_popen(cmd, stdout=None, stderr=None, bufsize=None):
            captured["bufsize"] = bufsize
            return FakeProcess()

        monkeypatch.setattr(subprocess, "Popen", fake_popen)

        service = tss.TranscodeStreamService()
        stream = tss.TranscodeStream(
            stream_key="1:test:ts:t:fp",
            account_id=1,
            stream_id="test",
            format="ts",
            upstream_url="http://example/stream.ts",
            credential_id=1,
            session_token="sess",
            transcode_profile=software_profile,
        )
        service._start_ffmpeg(stream)
        assert captured["bufsize"] == 4096


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


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not available")
class TestTranscodeStreamIntegration:
    def test_subscribe_defers_ffmpeg_until_stream_chunks(self, software_profile, test_video):
        service = TranscodeStreamService()
        service.start()
        try:
            stream, subscriber = service.subscribe(
                account_id=1,
                stream_id="test",
                format="ts",
                upstream_url=str(test_video),
                credential_id=1,
                session_token="sess",
                transcode_profile=software_profile,
                user_agent="test",
            )
            assert stream.process is None
            assert not stream.ffmpeg_started

            chunks = list(service.stream_chunks(stream, subscriber))
            service.unsubscribe(stream, subscriber)

            assert stream.ffmpeg_started
            assert sum(len(c) for c in chunks) > 0
        finally:
            service.stop()

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
            with output.open("rb") as f:
                assert f.read(1) == b"\x47"
        finally:
            service.stop()
