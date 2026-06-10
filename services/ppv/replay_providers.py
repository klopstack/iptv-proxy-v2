"""Detect intentional replay/archive IPTV providers (FloSports, etc.)."""

from __future__ import annotations

import re
from typing import Optional

# FloSports / FLSP college and minor-league replay feeds
REPLAY_PROVIDER_PATTERNS = [
    re.compile(r"\bFlo\s*\(\s*FLSP\s*\)", re.IGNORECASE),
    re.compile(r"\(\s*US\s*\)\s*\(\s*Flo\b", re.IGNORECASE),
    re.compile(r"\bUS\s*\(\s*Flo\s+\d+", re.IGNORECASE),
    re.compile(r"\|\s*\[.*\|\s*Flo\b", re.IGNORECASE),
]

METADATA_KEY_REPLAY_ARCHIVE = "replay_archive"


def is_replay_archive_provider(channel_name: str) -> bool:
    """True when the title prefix identifies an intentional archive replay feed."""
    if not channel_name or not channel_name.strip():
        return False
    return any(pattern.search(channel_name) for pattern in REPLAY_PROVIDER_PATTERNS)


def replay_provider_id(channel_name: str) -> Optional[str]:
    """Return a stable provider id for metrics/routing, or None."""
    if not is_replay_archive_provider(channel_name):
        return None
    if re.search(r"\bFlo\s*\(\s*FLSP\s*\)", channel_name, re.IGNORECASE):
        return "flosp"
    if re.search(r"\bFlo\b", channel_name, re.IGNORECASE):
        return "flo"
    return "replay_archive"
