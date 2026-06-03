"""Shared team entry lookup for context provider standings maps."""

from __future__ import annotations

from typing import Any, Dict, Optional


def lookup_team_entry(
    all_teams: Dict[str, Dict[str, Any]],
    team_name: str,
    team_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Find a team standings entry by exact name, team id, or partial name match.

    Provider standings payloads use ``{"_all_teams": {key_lower: {"record": ..., "standing": ...}}}``.
    Keys are typically lowercased team names or external team ids.
    """
    if not all_teams:
        return None

    if team_id:
        entry = all_teams.get(str(team_id).lower())
        if entry:
            return entry

    key = (team_name or "").lower()
    if not key:
        return None

    entry = all_teams.get(key)
    if entry:
        return entry

    for k, v in all_teams.items():
        if key in k or k in key:
            return v
    return None
