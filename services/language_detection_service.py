"""Detect broadcast language from channel names and network defaults."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from models import Channel, db

logger = logging.getLogger(__name__)

UNKNOWN_LANG = "und"

# (compiled pattern, ISO 639-1 code, confidence)
EXPLICIT_PATTERNS: Sequence[Tuple[re.Pattern[str], str, float]] = (
    (re.compile(r"\(Español\)|\(Spanish\)|\[ES\]| LATAM ", re.IGNORECASE), "es", 0.95),
    (re.compile(r"\(English\)|\[EN\]|\(In English\)", re.IGNORECASE), "en", 0.95),
    (re.compile(r"\(Français\)|\(French\)|\[FR\]", re.IGNORECASE), "fr", 0.95),
    (re.compile(r"\(Deutsch\)|\(German\)|\[DE\]", re.IGNORECASE), "de", 0.95),
    (re.compile(r"\(Português\)|\(Portuguese\)|\[PT\]", re.IGNORECASE), "pt", 0.95),
    (re.compile(r"\(Italiano\)|\(Italian\)|\[IT\]", re.IGNORECASE), "it", 0.95),
    (re.compile(r"\sES\s*$", re.IGNORECASE), "es", 0.85),
)

# Applied only when no explicit marker matches.
NETWORK_DEFAULTS: Sequence[Tuple[re.Pattern[str], str, float]] = (
    (re.compile(r"Peacock", re.IGNORECASE), "en", 0.75),
    (re.compile(r"beIN", re.IGNORECASE), "ar", 0.75),
    (re.compile(r"DAZN\s+DE|DAZN\s*DE", re.IGNORECASE), "de", 0.75),
)


@dataclass(frozen=True)
class LanguageDetectionResult:
    broadcast_language: Optional[str]
    language_source: Optional[str]
    language_confidence: Optional[float]


def detect_broadcast_language(
    channel_name: str,
    *,
    category_name: str = "",
) -> LanguageDetectionResult:
    """Detect broadcast language from channel name using explicit patterns and network defaults."""
    name = channel_name or ""

    for pattern, lang, confidence in EXPLICIT_PATTERNS:
        if pattern.search(name):
            return LanguageDetectionResult(lang, "explicit_name", confidence)

    for pattern, lang, confidence in NETWORK_DEFAULTS:
        if pattern.search(name):
            return LanguageDetectionResult(lang, "network_default", confidence)

    return LanguageDetectionResult(None, None, None)


def apply_language_detection(channel: Channel, *, commit: bool = False) -> bool:
    """Run detection on one channel and persist when the result changes."""
    category_name = ""
    if channel.category:
        category_name = channel.category.category_name or ""

    result = detect_broadcast_language(channel.name, category_name=category_name)
    changed = False

    if result.broadcast_language != channel.broadcast_language:
        channel.broadcast_language = result.broadcast_language
        changed = True
    if result.language_source != channel.language_source:
        channel.language_source = result.language_source
        changed = True
    if result.language_confidence != channel.language_confidence:
        channel.language_confidence = result.language_confidence
        changed = True

    if changed and commit:
        db.session.commit()

    return changed


def detect_languages_for_channels(channels: Iterable[Channel], *, commit: bool = True) -> int:
    """Batch-detect broadcast language; returns count of channels updated."""
    updated = 0
    for channel in channels:
        if apply_language_detection(channel):
            updated += 1

    if updated and commit:
        db.session.commit()

    return updated


def detect_languages_for_account(account_id: int) -> dict:
    """Detect languages for all active channels on an account."""
    channels = Channel.query.filter_by(account_id=account_id, is_active=True).all()
    updated = detect_languages_for_channels(channels)
    return {"channels_checked": len(channels), "channels_updated": updated}


def detect_languages_for_channel_ids(channel_ids: Iterable[int]) -> dict:
    """Detect languages for specific channel IDs (e.g. after PPV enrichment)."""
    ids = list(channel_ids)
    if not ids:
        return {"channels_checked": 0, "channels_updated": 0}

    channels = Channel.query.filter(Channel.id.in_(ids)).all()
    updated = detect_languages_for_channels(channels)
    return {"channels_checked": len(channels), "channels_updated": updated}
