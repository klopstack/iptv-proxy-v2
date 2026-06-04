"""Validate PPV channel extractions against calendar events."""

from itertools import permutations
from typing import List, Optional, Sequence, Tuple, Union

from services.ppv.matching.context import SportLeagueContext, event_league_matches_context, sport_key_from_league_name
from services.ppv.matching.mlb_teams import resolve_mlb_abbrev
from services.reverse_event_matcher.match_strategy import MIN_TEAM_NAME_LENGTH
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


def _mlb_abbrev_matches(short_name: str, full_name: str) -> bool:
    """True when a two- or three-letter token is a known MLB code for the full team name."""
    resolved = resolve_mlb_abbrev(short_name)
    if not resolved:
        return False
    return team_names_match(resolved, full_name)


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
    if len(shorter) >= MIN_TEAM_NAME_LENGTH and shorter in longer:
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

    if sport_key == "mlb":
        if _mlb_abbrev_matches(name_a, name_b) or _mlb_abbrev_matches(name_b, name_a):
            return True

    return False


def _resolve_sport_key(context: Optional[SportLeagueContext], event: CalendarEvent) -> Optional[str]:
    if context and context.primary_sport_key:
        return context.primary_sport_key
    return sport_key_from_league_name(event.league_name)


def _split_doubles_side(side: str) -> List[str]:
    if " / " in side:
        return [p.strip() for p in side.split(" / ") if p.strip()]
    if "/" in side:
        return [p.strip() for p in side.split("/") if p.strip()]
    return [side.strip()] if side.strip() else []


def _calendar_doubles_players(event: CalendarEvent) -> Optional[List[str]]:
    home_parts = _split_doubles_side(event.home_team or "")
    away_parts = _split_doubles_side(event.away_team or "")
    if len(home_parts) != 2 or len(away_parts) != 2:
        return None
    return home_parts + away_parts


def _four_players_match(
    channel_players: Sequence[str],
    calendar_players: Sequence[str],
    *,
    sport_key: Optional[str],
) -> bool:
    if len(channel_players) != 4 or len(calendar_players) != 4:
        return False

    cal = list(calendar_players)
    for perm in permutations(cal):
        if all(
            team_names_match_for_event_validation(ch, cal_name, sport_key=sport_key)
            for ch, cal_name in zip(channel_players, perm)
        ):
            return True
    return False


def competitors_match_event_doubles(
    players: Sequence[str],
    event: CalendarEvent,
    *,
    context: Optional[SportLeagueContext] = None,
) -> bool:
    """All four extracted players must match a doubles calendar row (home/away order independent)."""
    if len(players) != 4:
        return False

    home = event.home_team
    away = event.away_team
    if not home or not away:
        return False
    if home.lower() == "unknown" or away.lower() == "unknown":
        return False

    calendar_players = _calendar_doubles_players(event)
    if not calendar_players:
        return False

    if context is not None and not context.is_empty:
        if not event_league_matches_context(event.league_name, context):
            return False

    sport_key = _resolve_sport_key(context, event) or "tennis"
    return _four_players_match(players, calendar_players, sport_key=sport_key)


def competitors_match_event(
    competitors: Union[Tuple[str, str], Tuple[str, str, str, str]],
    event: CalendarEvent,
    *,
    context: Optional[SportLeagueContext] = None,
    players: Optional[Sequence[str]] = None,
) -> bool:
    """Extracted competitors must match the event teams (home/away order independent)."""
    if players and len(players) == 4:
        return competitors_match_event_doubles(players, event, context=context)

    if len(competitors) == 4:
        return competitors_match_event_doubles(competitors, event, context=context)

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
    c1, c2 = competitors  # type: ignore[misc]
    if " / " in c1 or " / " in c2:
        side1 = _split_doubles_side(c1)
        side2 = _split_doubles_side(c2)
        if len(side1) == 2 and len(side2) == 2:
            flat = side1 + side2
            cal_players = _calendar_doubles_players(event)
            if cal_players:
                return _four_players_match(flat, cal_players, sport_key=sport_key or "tennis")

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
