"""Legacy city/country → IANA map when team_location_registry has no entry.

Prefer ``SportsTeam.iana_timezone`` and ``assets/team_locations/registry.json`` for
US/FB/WNBA/MiLB; this module remains a fallback for older sportsipy-only paths.
"""

from __future__ import annotations

from typing import Optional

# US/CA major sports cities → IANA (multi-zone countries)
_US_CITY_TZ = {
    "new york": "America/New_York",
    "brooklyn": "America/New_York",
    "buffalo": "America/New_York",
    "boston": "America/New_York",
    "philadelphia": "America/New_York",
    "pittsburgh": "America/New_York",
    "washington": "America/New_York",
    "baltimore": "America/New_York",
    "miami": "America/New_York",
    "tampa": "America/New_York",
    "orlando": "America/New_York",
    "jacksonville": "America/New_York",
    "atlanta": "America/New_York",
    "charlotte": "America/New_York",
    "raleigh": "America/New_York",
    "detroit": "America/Detroit",
    "cleveland": "America/New_York",
    "cincinnati": "America/New_York",
    "indianapolis": "America/Indiana/Indianapolis",
    "chicago": "America/Chicago",
    "milwaukee": "America/Chicago",
    "minneapolis": "America/Chicago",
    "st. paul": "America/Chicago",
    "st louis": "America/Chicago",
    "kansas city": "America/Chicago",
    "dallas": "America/Chicago",
    "fort worth": "America/Chicago",
    "houston": "America/Chicago",
    "san antonio": "America/Chicago",
    "austin": "America/Chicago",
    "memphis": "America/Chicago",
    "nashville": "America/Chicago",
    "new orleans": "America/Chicago",
    "oklahoma city": "America/Chicago",
    "denver": "America/Denver",
    "phoenix": "America/Phoenix",
    "salt lake city": "America/Denver",
    "albuquerque": "America/Denver",
    "las vegas": "America/Los_Angeles",
    "los angeles": "America/Los_Angeles",
    "anaheim": "America/Los_Angeles",
    "san diego": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "oakland": "America/Los_Angeles",
    "san jose": "America/Los_Angeles",
    "sacramento": "America/Los_Angeles",
    "portland": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "vancouver": "America/Vancouver",
    "toronto": "America/Toronto",
    "montreal": "America/Toronto",
    "ottawa": "America/Toronto",
    "calgary": "America/Edmonton",
    "edmonton": "America/Edmonton",
    "winnipeg": "America/Winnipeg",
}

_COUNTRY_TZ = {
    "usa": "America/New_York",
    "united states": "America/New_York",
    "england": "Europe/London",
    "united kingdom": "Europe/London",
    "scotland": "Europe/London",
    "wales": "Europe/London",
    "uk": "Europe/London",
    "ireland": "Europe/Dublin",
    "netherlands": "Europe/Amsterdam",
    "holland": "Europe/Amsterdam",
    "belgium": "Europe/Brussels",
    "germany": "Europe/Berlin",
    "france": "Europe/Paris",
    "spain": "Europe/Madrid",
    "italy": "Europe/Rome",
    "portugal": "Europe/Lisbon",
    "canada": "America/Toronto",
    "australia": "Australia/Sydney",
    "japan": "Asia/Tokyo",
    "mexico": "America/Mexico_City",
    "brazil": "America/Sao_Paulo",
}

# EU football cities
_EU_CITY_TZ = {
    "london": "Europe/London",
    "manchester": "Europe/London",
    "liverpool": "Europe/London",
    "birmingham": "Europe/London",
    "glasgow": "Europe/London",
    "edinburgh": "Europe/London",
    "madrid": "Europe/Madrid",
    "barcelona": "Europe/Madrid",
    "paris": "Europe/Paris",
    "milan": "Europe/Rome",
    "rome": "Europe/Rome",
    "turin": "Europe/Rome",
    "munich": "Europe/Berlin",
    "berlin": "Europe/Berlin",
    "dortmund": "Europe/Berlin",
    "amsterdam": "Europe/Amsterdam",
    "lisbon": "Europe/Lisbon",
    "dublin": "Europe/Dublin",
}


def iana_for_city(city: Optional[str], country: Optional[str] = None) -> Optional[str]:
    """Resolve IANA timezone from venue or team city (+ optional country hint)."""
    if not city or not str(city).strip():
        if country:
            return _COUNTRY_TZ.get(country.strip().lower())
        return None

    key = city.strip().lower()
    if key in _US_CITY_TZ:
        return _US_CITY_TZ[key]
    if key in _EU_CITY_TZ:
        return _EU_CITY_TZ[key]

    if country:
        country_key = country.strip().lower()
        if country_key in ("usa", "united states", "us"):
            return _US_CITY_TZ.get(key)
        return _COUNTRY_TZ.get(country_key)

    return None


def iana_for_team_city(team_name: str) -> Optional[str]:
    """Best-effort IANA from team name city portion (e.g. 'Texas Rangers' → Dallas area)."""
    if not team_name:
        return None
    parts = team_name.strip().lower().split()
    if len(parts) < 2:
        return None

    # Try two-word city then one-word
    for n in (2, 1):
        if len(parts) >= n + 1:
            city = " ".join(parts[:n])
            tz = _US_CITY_TZ.get(city) or _EU_CITY_TZ.get(city)
            if tz:
                return tz
    return None
