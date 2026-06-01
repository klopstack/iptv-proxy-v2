"""Validate PPV channel extractions against calendar events."""

from typing import Optional, Tuple

from services.ppv.matching.context import SportLeagueContext, event_league_matches_context, sport_key_from_league_name
from services.reverse_event_matcher.text_processor import TextProcessor
from services.thesportsdb_calendar_scraper import CalendarEvent

_text_processor = TextProcessor()

# Words that appear in many team names and must not be the sole basis for a match
AMBIGUOUS_TEAM_WORDS = frozenset(
    {
        "united",
        "city",
        "fc",
        "sc",
        "cf",
        "ac",
        "real",
        "sporting",
        "athletic",
        "inter",
        "dynamo",
        "rangers",
        "wild",
        "national",
        "state",
        "north",
        "south",
        "east",
        "west",
        "central",
        "royal",
        "club",
        "team",
    }
)

_sports_team_mapping_cache: dict[str, dict[str, str]] = {}


def _compact_name(name: str) -> str:
    """Normalize and compact a team name for abbreviation matching."""
    normalized = _text_processor.normalize_text(name)
    return normalized.replace(" ", "").replace("-", "")


def _abbreviation_matches(short_name: str, full_name: str) -> bool:
    """
    Match abbreviated feed names to full team names (e.g. D-backs -> Diamondbacks).

    Requires at least 5 characters to avoid matching overly generic fragments.
    """
    compact_short = _compact_name(short_name)
    compact_full = _compact_name(full_name)
    if len(compact_short) < 5:
        return False
    return compact_short in compact_full


def _mascot_matches(full_name: str, nickname: str) -> bool:
    """True when a short nickname matches the mascot (last word) of a full team name."""
    if not full_name or not nickname:
        return False

    full_words = full_name.split()
    nick = nickname.strip()
    if len(full_words) < 2 or len(nick.split()) != 1:
        return False

    mascot = full_words[-1]
    if mascot.lower() != nick.lower():
        return False

    return mascot.lower() not in AMBIGUOUS_TEAM_WORDS


def _mascot_matches_for_event_validation(full_name: str, nickname: str) -> bool:
    """Mascot match without global ambiguity guard (event-bound validation only)."""
    if not full_name or not nickname:
        return False

    full_words = full_name.split()
    nick = nickname.strip()
    if len(full_words) < 2 or len(nick.split()) != 1:
        return False

    return full_words[-1].lower() == nick.lower()


def _get_sports_team_mapping(sport_key: str) -> dict[str, str]:
    """Load alias -> abbreviation mapping for a sport (cached, no-op if empty)."""
    key = sport_key.lower()
    if key in _sports_team_mapping_cache:
        return _sports_team_mapping_cache[key]

    mapping: dict[str, str] = {}
    try:
        from models import SportsTeam

        mapping = SportsTeam.get_team_mapping(key)
    except Exception:
        mapping = {}

    _sports_team_mapping_cache[key] = mapping
    return mapping


def _sports_team_aliases_match(name_a: str, name_b: str, sport_key: str) -> bool:
    """True when both names resolve to the same SportsTeam abbreviation."""
    mapping = _get_sports_team_mapping(sport_key)
    if not mapping:
        return False

    na = _text_processor.normalize_text(name_a)
    nb = _text_processor.normalize_text(name_b)
    abbrev_a = mapping.get(na)
    abbrev_b = mapping.get(nb)
    return bool(abbrev_a and abbrev_b and abbrev_a == abbrev_b)


def team_names_match(name_a: str, name_b: str) -> bool:
    """Return True when two team names refer to the same side."""
    if not name_a or not name_b:
        return False

    na = _text_processor.normalize_text(name_a)
    nb = _text_processor.normalize_text(name_b)
    if not na or not nb:
        return False

    if na == nb:
        return True

    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if shorter in longer:
        shorter_words = set(shorter.split())
        if shorter_words <= AMBIGUOUS_TEAM_WORDS:
            return False
        return True

    if _abbreviation_matches(na, nb) or _abbreviation_matches(nb, na):
        return True

    if _mascot_matches(na, nb) or _mascot_matches(nb, na):
        return True

    words_a = _text_processor.extract_significant_words(na)
    words_b = _text_processor.extract_significant_words(nb)
    if not words_a or not words_b:
        return False

    overlap = words_a & words_b
    if not overlap:
        return False

    # Reject matches based only on ambiguous shared words (e.g. "Manchester" alone)
    distinctive_overlap = overlap - AMBIGUOUS_TEAM_WORDS
    if not distinctive_overlap:
        return False

    # Require the distinctive part of each name to appear in the other
    min_words = min(len(words_a), len(words_b))
    return len(distinctive_overlap) >= max(1, min_words)


def team_names_match_for_event_validation(
    name_a: str,
    name_b: str,
    *,
    sport_key: Optional[str] = None,
) -> bool:
    """Event-bound team name matching with relaxed mascot rules and optional SportsTeam lookup."""
    if not name_a or not name_b:
        return False

    if team_names_match(name_a, name_b):
        return True

    na = _text_processor.normalize_text(name_a)
    nb = _text_processor.normalize_text(name_b)

    if _mascot_matches_for_event_validation(na, nb) or _mascot_matches_for_event_validation(nb, na):
        return True

    if sport_key and _sports_team_aliases_match(name_a, name_b, sport_key):
        return True

    return False


def _resolve_sport_key(context: Optional[SportLeagueContext], event: CalendarEvent) -> Optional[str]:
    if context and context.primary_sport_key:
        return context.primary_sport_key
    return sport_key_from_league_name(event.league_name)


def competitors_match_event(
    competitors: Tuple[str, str],
    event: CalendarEvent,
    *,
    context: Optional[SportLeagueContext] = None,
) -> bool:
    """Both extracted competitors must match the event teams (home/away order independent)."""
    home = event.home_team
    away = event.away_team
    if not home or not away:
        return False
    if home.lower() == "unknown" or away.lower() == "unknown":
        return False

    if context is not None and not context.is_empty:
        if not event_league_matches_context(event.league_name, context):
            return False

    sport_key = _resolve_sport_key(context, event)
    c1, c2 = competitors
    return (
        team_names_match_for_event_validation(c1, home, sport_key=sport_key)
        and team_names_match_for_event_validation(c2, away, sport_key=sport_key)
    ) or (
        team_names_match_for_event_validation(c1, away, sport_key=sport_key)
        and team_names_match_for_event_validation(c2, home, sport_key=sport_key)
    )


def is_weak_match_type(match_type: str) -> bool:
    """Match types that must not be used when channel names include both competitors."""
    return match_type in (
        "league_only",
        "league_plus_word",
        "league_plus_words",
        "one_team",
        "word_overlap",
    )
