"""
EventContext assembler.

Builds an EventContext for a given Event by querying the provider registry.
For each data type the assembler tries providers in priority order and uses
the first non-None result.  Missing data types are recorded so gaps are
visible in the resulting context and in the persisted event_metadata.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Optional

from services.ppv.context.base import DataType, EventContext, TeamContext
from services.ppv.context.registry import get_registry

if TYPE_CHECKING:
    from models import Event

logger = logging.getLogger(__name__)


def build_event_context(event: "Event") -> EventContext:
    """
    Assemble an EventContext for *event* by querying registered providers.

    Args:
        event: SQLAlchemy Event model instance (must have sport, league_name,
               home_team_name, away_team_name populated).

    Returns:
        EventContext with as much data as available providers can supply.
        Fields with no provider coverage are None / empty list.
    """
    sport = event.sport or ""
    league = event.league_name or ""
    home_name = event.home_team_name or ""
    away_name = event.away_team_name or ""
    home_id = event.home_team_id or None
    away_id = event.away_team_id or None
    event_date = event.scheduled_at.strftime("%Y-%m-%d") if event.scheduled_at else None
    external_id = event.external_id or None

    registry = get_registry()
    data_sources: list[str] = []
    missing_data: list[str] = []

    # ------------------------------------------------------------------ standings
    home_ctx = TeamContext(name=home_name)
    away_ctx = TeamContext(name=away_name)

    standings_providers = registry.get_providers_for(sport, league, DataType.STANDINGS)
    standings_fetched = False
    for provider in standings_providers:
        try:
            standings_result = provider.get_standings(sport, league)
            if standings_result:
                # All providers return {"_all_teams": {team_name_lower: {"record":..., "standing":...}}}
                all_teams = standings_result.get("_all_teams", {})
                for team_ctx, team_name in ((home_ctx, home_name), (away_ctx, away_name)):
                    name_lower = team_name.lower()
                    entry = all_teams.get(name_lower)
                    if not entry:
                        # Try partial match
                        for k, v in all_teams.items():
                            if name_lower in k or k in name_lower:
                                entry = v
                                break
                    if entry:
                        team_ctx.record = entry.get("record")
                        team_ctx.standing = entry.get("standing")
                data_sources.append(f"{provider.name}:standings")
                standings_fetched = True
                break
        except Exception as exc:
            logger.warning("Provider %s raised during get_standings: %s", provider.name, exc)

    if not standings_fetched:
        missing_data.append(DataType.STANDINGS.value)

    # ------------------------------------------------------------------ head-to-head
    h2h_lines: list[str] = []
    h2h_providers = registry.get_providers_for(sport, league, DataType.HEAD_TO_HEAD)
    h2h_fetched = False
    for provider in h2h_providers:
        try:
            h2h_result = provider.get_head_to_head(
                home_team=home_name,
                away_team=away_name,
                sport=sport,
                home_team_id=home_id,
                away_team_id=away_id,
            )
            if h2h_result is not None:
                h2h_lines = h2h_result
                if h2h_result:
                    data_sources.append(f"{provider.name}:head_to_head")
                h2h_fetched = True
                break
        except Exception as exc:
            logger.warning("Provider %s raised during get_head_to_head: %s", provider.name, exc)

    if not h2h_fetched:
        missing_data.append(DataType.HEAD_TO_HEAD.value)

    # ------------------------------------------------------------------ team form
    form_providers_home = registry.get_providers_for(sport, league, DataType.TEAM_FORM)
    for provider in form_providers_home:
        try:
            home_form_result = provider.get_team_form(team_name=home_name, sport=sport, team_id=home_id)
            if home_form_result is not None:
                home_ctx.recent_form = home_form_result
                if home_form_result:
                    data_sources.append(f"{provider.name}:team_form:home")
                break
        except Exception as exc:
            logger.warning("Provider %s raised during get_team_form(home): %s", provider.name, exc)

    form_providers_away = registry.get_providers_for(sport, league, DataType.TEAM_FORM)
    for provider in form_providers_away:
        try:
            away_form_result = provider.get_team_form(team_name=away_name, sport=sport, team_id=away_id)
            if away_form_result is not None:
                away_ctx.recent_form = away_form_result
                if away_form_result:
                    data_sources.append(f"{provider.name}:team_form:away")
                break
        except Exception as exc:
            logger.warning("Provider %s raised during get_team_form(away): %s", provider.name, exc)

    if not form_providers_home:
        missing_data.append(DataType.TEAM_FORM.value)

    # ------------------------------------------------------------------ fighter record (combat sports)
    if sport.lower() in ("boxing", "mma", "wrestling", "combat sports", "fighting"):
        fighter_providers = registry.get_providers_for(sport, league, DataType.FIGHTER_RECORD)
        for provider in fighter_providers:
            try:
                home_record = provider.get_fighter_record(home_name, sport, fighter_id=home_id)
                if not home_record:
                    home_form = provider.get_team_form(team_name=home_name, sport=sport, team_id=home_id)
                    if home_form:
                        home_record = home_form[0] if len(home_form) == 1 else ", ".join(home_form)
                if home_record:
                    home_ctx.extra = home_record
                    data_sources.append(f"{provider.name}:fighter_record:home")

                away_record = provider.get_fighter_record(away_name, sport, fighter_id=away_id)
                if not away_record:
                    away_form = provider.get_team_form(team_name=away_name, sport=sport, team_id=away_id)
                    if away_form:
                        away_record = away_form[0] if len(away_form) == 1 else ", ".join(away_form)
                if away_record:
                    away_ctx.extra = away_record
                    data_sources.append(f"{provider.name}:fighter_record:away")
                if home_ctx.extra or away_ctx.extra:
                    break
            except Exception as exc:
                logger.warning("Provider %s raised during get fighter_record: %s", provider.name, exc)

    # ------------------------------------------------------------------ event notes
    event_notes: Optional[str] = None
    notes_providers = registry.get_providers_for(sport, league, DataType.EVENT_NOTES)
    notes_fetched = False
    for provider in notes_providers:
        try:
            notes_result = provider.get_event_notes(
                home_team=home_name,
                away_team=away_name,
                sport=sport,
                event_date=event_date,
                event_id=external_id,
            )
            if notes_result:
                event_notes = notes_result
                data_sources.append(f"{provider.name}:event_notes")
                notes_fetched = True
                break
        except Exception as exc:
            logger.warning("Provider %s raised during get_event_notes: %s", provider.name, exc)

    if not notes_fetched:
        missing_data.append(DataType.EVENT_NOTES.value)

    # Deduplicate data_sources while preserving order
    seen: set[str] = set()
    unique_sources: list[str] = []
    for s in data_sources:
        if s not in seen:
            seen.add(s)
            unique_sources.append(s)

    context = EventContext(
        sport=sport,
        league=league,
        home_team=home_ctx,
        away_team=away_ctx,
        head_to_head=h2h_lines,
        event_notes=event_notes,
        data_sources=unique_sources,
        missing_data=list(dict.fromkeys(missing_data)),
    )

    logger.debug(
        "Built EventContext for %s vs %s: sources=%s missing=%s",
        home_name,
        away_name,
        unique_sources,
        missing_data,
    )

    return context


def persist_context_metadata(event: "Event", context: EventContext) -> None:
    """
    Merge context provenance into event.event_metadata (JSON column).

    Stored under the "context" key so it coexists with any existing metadata.
    """
    try:
        existing: dict[str, Any] = {}
        if event.event_metadata:
            try:
                decoded = json.loads(event.event_metadata)
                if isinstance(decoded, dict):
                    existing = decoded
            except (json.JSONDecodeError, TypeError):
                existing = {}

        existing["context"] = {
            "data_sources": context.data_sources,
            "missing_data": context.missing_data,
        }
        event.event_metadata = json.dumps(existing)
    except Exception as exc:
        logger.warning("Could not persist context metadata for event %s: %s", event.id, exc)
