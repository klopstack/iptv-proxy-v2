"""
Per-client transcode profile and FFmpeg encode argument builder.

Hardware acceleration order: VAAPI (Intel Arc) -> QSV -> libx264 software fallback.
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
                    "-hwaccel",
                    "vaapi",
                    "-hwaccel_device",
                    "/dev/dri/renderD128",
                    "-hwaccel_output_format",
                    "vaapi",
                    "-i",
                    upstream_url,
                    "-vf",
                    f"scale_vaapi=w=-2:h=min(ih\\,{height})",
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
                    "-hwaccel",
                    "qsv",
                    "-hwaccel_output_format",
                    "qsv",
                    "-i",
                    upstream_url,
                    "-vf",
                    f"scale_qsv=w=-2:h=min(ih\\,{height})",
                    "-c:v",
                    "h264_qsv",
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


def _detect_encoder_mode() -> str:
    if TRANSCODE_HWACCEL == "software":
        return "software"

    encoders = _ffmpeg_encoders()
    prefer_vaapi = TRANSCODE_HWACCEL in ("auto", "vaapi")
    prefer_qsv = TRANSCODE_HWACCEL in ("auto", "qsv")

    if prefer_vaapi and "h264_vaapi" in encoders:
        logger.info("Transcode hardware acceleration: VAAPI (h264_vaapi)")
        return "vaapi"
    if prefer_qsv and "h264_qsv" in encoders:
        logger.info("Transcode hardware acceleration: QSV (h264_qsv)")
        return "qsv"

    logger.warning(
        "No hardware transcode encoder available (TRANSCODE_HWACCEL=%s); using libx264",
        TRANSCODE_HWACCEL,
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
