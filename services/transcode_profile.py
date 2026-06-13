"""
Per-client transcode profile and FFmpeg encode argument builder.

Hardware acceleration order: QSV (Intel Quick Sync) -> VAAPI -> libx264 software.
Live MPEG-TS is decoded in software (IPTV streams are often corrupt at join); encode
uses QSV or VAAPI. On Linux, QSV is initialized via a VAAPI parent device (see Intel
Media SDK wiki: init_hw_device vaapi + qsv@va).
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from models.account import XtreamCredential

logger = logging.getLogger(__name__)

TRANSCODE_HWACCEL = os.environ.get("TRANSCODE_HWACCEL", "auto").lower()
TRANSCODE_DRI_DEVICE = os.environ.get("TRANSCODE_DRI_DEVICE") or os.environ.get(
    "TRANSCODE_VAAPI_DEVICE", "/dev/dri/renderD128"
)
# Frames pre-allocated for QSV hwupload (MFX requires a fixed pool size).
_QSV_HWUPLOAD_FRAMES = int(os.environ.get("TRANSCODE_QSV_HWUPLOAD_FRAMES", "64"))

# Tuning for live IPTV MPEG-TS (tolerate corrupt packets, start quickly).
_MPEGTS_INPUT_FLAGS = [
    "-fflags",
    "+genpts+discardcorrupt",
    "-flags",
    "low_delay",
    "-probesize",
    "500000",
    "-analyzeduration",
    "1000000",
]

# Cached encoder mode after first probe: "vaapi", "qsv", or "software"
_encoder_mode: Optional[str] = None


@dataclass(frozen=True)
class TranscodeProfile:
    """Client-specific transcode limits."""

    enabled: bool
    max_height: int
    max_bitrate_kbps: int
    audio_channels: int
    audio_bitrate_kbps: int

    @classmethod
    def from_xtream_credential(cls, cred: "XtreamCredential") -> Optional["TranscodeProfile"]:
        if not cred.transcode_enabled:
            return None
        return cls(
            enabled=True,
            max_height=cred.transcode_max_height or 720,
            max_bitrate_kbps=cred.transcode_max_bitrate_kbps or 8000,
            audio_channels=cred.transcode_audio_channels or 2,
            audio_bitrate_kbps=cred.transcode_audio_bitrate_kbps or 128,
        )

    def fingerprint(self) -> str:
        payload = (
            f"h{self.max_height}:v{self.max_bitrate_kbps}:"
            f"a{self.audio_channels}:{self.audio_bitrate_kbps}:{get_encoder_mode()}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:8]

    def build_ffmpeg_args(self, upstream_url: str, user_agent: str) -> List[str]:
        mode = get_encoder_mode()
        video_bitrate = max(500, self.max_bitrate_kbps - self.audio_bitrate_kbps)
        maxrate = f"{self.max_bitrate_kbps}k"
        bufsize = f"{self.max_bitrate_kbps * 2}k"
        v_bitrate = f"{video_bitrate}k"
        height = self.max_height
        audio_ch = str(self.audio_channels)
        audio_br = f"{self.audio_bitrate_kbps}k"

        is_remote = upstream_url.startswith("http://") or upstream_url.startswith("https://")

        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning"]

        if is_remote:
            cmd.extend(
                [
                    "-user_agent",
                    user_agent,
                    "-headers",
                    "Accept: */*\r\nConnection: keep-alive\r\n",
                    "-rw_timeout",
                    "30000000",
                    "-timeout",
                    "30000000",
                    "-reconnect",
                    "1",
                    "-reconnect_streamed",
                    "1",
                    "-reconnect_delay_max",
                    "5",
                    "-reconnect_on_network_error",
                    "1",
                    "-reconnect_on_http_error",
                    "5xx",
                    "-tcp_nodelay",
                    "1",
                ]
            )

        output_tail = [
            "-c:a",
            "aac",
            "-ac",
            audio_ch,
            "-b:a",
            audio_br,
            "-f",
            "mpegts",
            "-mpegts_flags",
            "+pat_pmt_at_frames",
            "pipe:1",
        ]

        if mode == "vaapi":
            return (
                cmd
                + [
                    "-init_hw_device",
                    f"vaapi=va:{TRANSCODE_DRI_DEVICE}",
                    "-filter_hw_device",
                    "va",
                ]
                + _MPEGTS_INPUT_FLAGS
                + [
                    "-i",
                    upstream_url,
                    "-vf",
                    f"format=nv12,hwupload,scale_vaapi=w=-2:h=min(ih\\,{height})",
                    "-c:v",
                    "h264_vaapi",
                    "-b:v",
                    v_bitrate,
                    "-maxrate",
                    maxrate,
                    "-bufsize",
                    bufsize,
                    "-g",
                    "50",
                ]
                + output_tail
            )

        if mode == "qsv":
            return (
                cmd
                + [
                    "-init_hw_device",
                    f"vaapi=va:{TRANSCODE_DRI_DEVICE}",
                    "-init_hw_device",
                    "qsv=hw@va",
                    "-filter_hw_device",
                    "hw",
                ]
                + _MPEGTS_INPUT_FLAGS
                + [
                    "-i",
                    upstream_url,
                    "-vf",
                    (
                        f"format=nv12,hwupload=extra_hw_frames={_QSV_HWUPLOAD_FRAMES},"
                        f"format=qsv,scale_qsv=w=-2:h=min(ih\\,{height})"
                    ),
                    "-c:v",
                    "h264_qsv",
                    "-preset",
                    "veryfast",
                    "-b:v",
                    v_bitrate,
                    "-maxrate",
                    maxrate,
                    "-bufsize",
                    bufsize,
                    "-g",
                    "50",
                ]
                + output_tail
            )

        # Software fallback
        return (
            cmd
            + _MPEGTS_INPUT_FLAGS
            + [
                "-i",
                upstream_url,
                "-vf",
                f"scale=w=-2:h=min(ih\\,{height})",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-b:v",
                v_bitrate,
                "-maxrate",
                maxrate,
                "-bufsize",
                bufsize,
                "-g",
                "50",
            ]
            + output_tail
        )


def _ffmpeg_encoders() -> str:
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.stdout + result.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("Could not probe ffmpeg encoders: %s", exc)
        return ""


def _probe_encoder_pipeline(args: List[str]) -> bool:
    """Return True when ffmpeg can initialize the given encode pipeline."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("Could not probe transcode encoder pipeline: %s", exc)
        return False


def _probe_qsv_encoder() -> bool:
    if "h264_qsv" not in _ffmpeg_encoders():
        return False
    return _probe_encoder_pipeline(
        [
            "-init_hw_device",
            f"vaapi=va:{TRANSCODE_DRI_DEVICE}",
            "-init_hw_device",
            "qsv=hw@va",
            "-filter_hw_device",
            "hw",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=0.1:size=64x64:rate=1",
            "-vf",
            f"hwupload=extra_hw_frames={min(_QSV_HWUPLOAD_FRAMES, 16)},format=qsv",
            "-c:v",
            "h264_qsv",
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ]
    )


def _probe_vaapi_encoder() -> bool:
    if "h264_vaapi" not in _ffmpeg_encoders():
        return False
    return _probe_encoder_pipeline(
        [
            "-init_hw_device",
            f"vaapi=va:{TRANSCODE_DRI_DEVICE}",
            "-filter_hw_device",
            "va",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=0.1:size=64x64:rate=1",
            "-vf",
            "format=nv12,hwupload",
            "-c:v",
            "h264_vaapi",
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ]
    )


def _detect_encoder_mode() -> str:
    if TRANSCODE_HWACCEL == "software":
        return "software"

    want_qsv = TRANSCODE_HWACCEL in ("auto", "qsv")
    want_vaapi = TRANSCODE_HWACCEL in ("auto", "vaapi")

    if want_qsv and _probe_qsv_encoder():
        logger.info(
            "Transcode hardware acceleration: QSV (h264_qsv via %s)",
            TRANSCODE_DRI_DEVICE,
        )
        return "qsv"
    if want_vaapi and _probe_vaapi_encoder():
        logger.info(
            "Transcode hardware acceleration: VAAPI (h264_vaapi via %s)",
            TRANSCODE_DRI_DEVICE,
        )
        return "vaapi"

    logger.warning(
        "No hardware transcode encoder available (TRANSCODE_HWACCEL=%s, device=%s); using libx264",
        TRANSCODE_HWACCEL,
        TRANSCODE_DRI_DEVICE,
    )
    return "software"


def get_encoder_mode() -> str:
    global _encoder_mode
    if _encoder_mode is None:
        _encoder_mode = _detect_encoder_mode()
    return _encoder_mode


def validate_transcode_fields(
    *,
    transcode_enabled: bool,
    transcode_max_height: Optional[int],
    transcode_max_bitrate_kbps: Optional[int],
    transcode_audio_channels: Optional[int],
    transcode_audio_bitrate_kbps: Optional[int],
) -> None:
    if transcode_max_height is not None and not (360 <= transcode_max_height <= 2160):
        raise ValueError("transcode_max_height must be between 360 and 2160")
    if transcode_max_bitrate_kbps is not None and not (500 <= transcode_max_bitrate_kbps <= 50000):
        raise ValueError("transcode_max_bitrate_kbps must be between 500 and 50000")
    if transcode_audio_channels is not None and transcode_audio_channels not in (1, 2):
        raise ValueError("transcode_audio_channels must be 1 or 2")
    if transcode_audio_bitrate_kbps is not None and not (32 <= transcode_audio_bitrate_kbps <= 512):
        raise ValueError("transcode_audio_bitrate_kbps must be between 32 and 512")
    if transcode_enabled and transcode_max_height is None:
        raise ValueError("transcode_max_height is required when transcode is enabled")
