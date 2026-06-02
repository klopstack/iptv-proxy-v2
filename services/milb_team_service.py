"""
MiLB team refresh from MLB Stats API into SportsTeam + location registry.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from services.mlb_stats_api import MILB_SPORT_IDS, get_mlb_stats_client
from services.team_location_registry import apply_location_to_sports_team, lookup, lookup_by_name

logger = logging.getLogger(__name__)


def _team_aliases(team: dict) -> List[str]:
    aliases: List[str] = []
    for field in ("name", "teamName", "locationName", "clubName", "shortName"):
        val = team.get(field)
        if val and isinstance(val, str):
            aliases.append(val.strip().lower())
    loc = team.get("locationName") or ""
    club = team.get("clubName") or team.get("teamName") or ""
    if loc and club:
        aliases.append(f"{loc} {club}".strip().lower())
    return sorted(set(a for a in aliases if a))


def refresh_milb_teams_from_mlb_api(season: Optional[int] = None) -> Dict[str, Any]:
    """
    Upsert SportsTeam rows for affiliated MiLB (sportIds 11–14).

    Location fields prefer bundled registry; API team/venue data fills gaps.
    """
    from models import SportsTeam, db

    season = season or date.today().year
    client = get_mlb_stats_client()
    stats: Dict[str, Any] = {
        "success": True,
        "season": season,
        "teams_added": 0,
        "teams_updated": 0,
        "sport_ids": list(MILB_SPORT_IDS),
    }

    try:
        api_teams = client.get_milb_teams(season=season)
    except Exception as exc:
        logger.error("MiLB team fetch failed: %s", exc)
        return {"success": False, "error": str(exc)}

    for team in api_teams:
        team_id = team.get("id")
        name = team.get("name") or ""
        if team_id is None or not name:
            continue
        abbrev = str(team_id)
        row = SportsTeam.query.filter_by(sport="milb", abbreviation=abbrev).first()
        created = row is None
        if created:
            row = SportsTeam(
                sport="milb",
                abbreviation=abbrev,
                name=name,
                source="mlb_stats_api",
            )
            db.session.add(row)
            stats["teams_added"] += 1
        else:
            stats["teams_updated"] += 1

        row.name = name
        row.source = "mlb_stats_api"
        row.division = (team.get("league") or {}).get("name")
        row.conference = team.get("_level")
        loc = team.get("locationName")
        if loc:
            row.city = loc
        row.set_aliases(_team_aliases(team))

        entry = lookup("milb", abbrev) or lookup_by_name("milb", name)
        if entry:
            apply_location_to_sports_team(row, entry)
            row.location_source = entry.source or "team_location_registry"

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("MiLB team refresh commit failed: %s", exc)
        return {"success": False, "error": str(exc)}

    stats["total_teams"] = SportsTeam.query.filter_by(sport="milb").count()
    return stats
