#!/usr/bin/env python3
"""
Build bundled team location registry from authoritative open datasets.

Offline build only — output is committed to data/team_locations/registry.json.
Run: python scripts/build_team_locations.py [--refresh]

MiLB teams (sportIds 11-14) are loaded from MLB Stats API (statsapi.mlb.com).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data" / "team_locations"
RAW_DIR = DATA_DIR / "raw"
REGISTRY_PATH = DATA_DIR / "registry.json"
META_PATH = DATA_DIR / "registry.meta.json"
OVERRIDES_PATH = DATA_DIR / "overrides.json"
ABBR_MAP_PATH = DATA_DIR / "abbr_map.json"
SR_PRO_TEAMS_PATH = DATA_DIR / "sr_pro_teams.json"
FB_LEAGUES_PATH = DATA_DIR / "fb_leagues.json"
TSDB_RAW_DIR = RAW_DIR / "thesportsdb"

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# League Wikidata IDs for pro sports
LEAGUE_QIDS = {
    "nba": "Q155223",
    "nhl": "Q1215892",
    "mlb": "Q1163715",
}

# nflverse team codes -> Sports Reference / sportsipy abbreviations
NFLVERSE_TO_SR = {
    "KC": "KAN",
    "NE": "NWE",
    "GB": "GNB",
    "NO": "NOR",
    "SF": "SFO",
    "TB": "TAM",
    "LV": "LVR",
    "LA": "LAR",
}

SOURCE_URLS = {
    "nfl_stadiums": "https://raw.githubusercontent.com/greerreNFL/Stadiums/main/data/stadiums.csv",
    "nfl_teams": "https://raw.githubusercontent.com/nflverse/nfldata/master/data/teams.csv",
    "nfl_games": "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv",
    "ncaaf_stadiums": (
        "https://raw.githubusercontent.com/gboeing/data-visualization/main/"
        "ncaa-football-stadiums/data/stadiums-geocoded.csv"
    ),
    "ipeds_zip": "https://nces.ed.gov/programs/edge/data/EDGE_GEOCODE_POSTSECSCH_2324.zip",
}

US_STATE_ABBR = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "district of columbia": "DC",
}


def _normalize_name(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _slug_key(text: str) -> str:
    """Sportsipy college slug style: uppercased, hyphens preserved."""
    return re.sub(r"[^A-Za-z0-9-]", "-", text.strip()).upper().strip("-")


def _fetch_url(url: str, refresh: bool, filename: str) -> str:
    path = RAW_DIR / filename
    if path.exists() and not refresh:
        return path.read_text(encoding="utf-8", errors="replace")
    try:
        import requests

        resp = requests.get(url, timeout=120, headers={"User-Agent": "iptv-proxy-v2-build/1.0"})
        resp.raise_for_status()
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(resp.text, encoding="utf-8")
        return resp.text
    except Exception as exc:
        if path.exists():
            print(f"Warning: fetch failed for {url}: {exc}; using cached {path}", file=sys.stderr)
            return path.read_text(encoding="utf-8", errors="replace")
        raise


def _fetch_wikidata(league_qid: str, refresh: bool, cache_name: str) -> List[Dict[str, Any]]:
    query = f"""
SELECT ?team ?teamLabel ?venueLabel ?cityLabel ?lat ?lon WHERE {{
  ?team wdt:P118 wd:{league_qid} .
  ?team wdt:P115 ?venue .
  ?venue wdt:P625 ?coord .
  BIND(STRAFTER(STR(?team), "entity/") AS ?teamItem)
  BIND(geof:latitude(?coord) AS ?lat)
  BIND(geof:longitude(?coord) AS ?lon)
  OPTIONAL {{ ?venue wdt:P131 ?city . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""
    path = RAW_DIR / cache_name
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    import requests

    params = urlencode({"query": query, "format": "json"})
    resp = requests.get(
        f"{WIKIDATA_SPARQL}?{params}",
        timeout=180,
        headers={"User-Agent": "iptv-proxy-v2-build/1.0", "Accept": "application/sparql-results+json"},
    )
    resp.raise_for_status()
    rows = resp.json().get("results", {}).get("bindings", [])
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return rows


def _iana_from_coords(lat: Optional[float], lon: Optional[float], tf) -> Optional[str]:
    if lat is None or lon is None or tf is None:
        return None
    try:
        return tf.timezone_at(lat=float(lat), lng=float(lon))
    except Exception:
        return None


def _state_abbr(state: Optional[str]) -> Optional[str]:
    if not state:
        return None
    s = state.strip()
    if len(s) == 2 and s.isalpha():
        return s.upper()
    return US_STATE_ABBR.get(s.lower())


def _registry_merge_key(sport: str, key: str) -> str:
    if sport in ("fb", "wnba", "milb"):
        return str(key)
    return str(key).upper()


def _entry(
    sport: str,
    key: str,
    name: str,
    city: Optional[str],
    state: Optional[str] = None,
    country: str = "US",
    venue_name: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    iana_timezone: Optional[str] = None,
    source: str = "",
    source_url: Optional[str] = None,
    *,
    aliases: Optional[List[str]] = None,
    thesportsdb_id: Optional[str] = None,
    fbref_squad_id: Optional[str] = None,
    league: Optional[str] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "sport": sport,
        "key": _registry_merge_key(sport, key),
        "name": name,
        "city": city,
        "state": _state_abbr(state),
        "country": country,
        "source": source,
    }
    if venue_name:
        row["venue_name"] = venue_name
    if latitude is not None:
        row["latitude"] = round(float(latitude), 6)
    if longitude is not None:
        row["longitude"] = round(float(longitude), 6)
    if iana_timezone:
        row["iana_timezone"] = iana_timezone
    if source_url:
        row["source_url"] = source_url
    if aliases:
        row["aliases"] = sorted(set(a.strip().lower() for a in aliases if a and str(a).strip()))
    if thesportsdb_id:
        row["thesportsdb_id"] = str(thesportsdb_id)
    if fbref_squad_id:
        row["fbref_squad_id"] = fbref_squad_id
    if league:
        row["league"] = league
    return row


def _load_abbr_map() -> Dict[str, Dict[str, List[str]]]:
    if not ABBR_MAP_PATH.exists():
        return {}
    data = json.loads(ABBR_MAP_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _load_overrides() -> List[Dict[str, Any]]:
    if not OVERRIDES_PATH.exists():
        return []
    data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    return list(data.get("entries", []))


def _load_sr_name_index() -> Dict[str, Dict[str, str]]:
    """Map normalized team name -> SR abbreviation per sport."""
    if not SR_PRO_TEAMS_PATH.exists():
        return {}
    data = json.loads(SR_PRO_TEAMS_PATH.read_text(encoding="utf-8"))
    index: Dict[str, Dict[str, str]] = {}
    for sport, teams in data.items():
        if sport.startswith("_") or not isinstance(teams, list):
            continue
        sport_index: Dict[str, str] = {}
        for team in teams:
            name = team.get("name", "")
            key = team.get("key", "")
            if name and key:
                sport_index[_normalize_name(name)] = key.upper()
        index[sport] = sport_index
    return index


def _match_key_from_name(
    sport: str,
    team_label: str,
    abbr_map: Dict[str, Dict[str, List[str]]],
    sr_index: Dict[str, Dict[str, str]],
) -> Optional[str]:
    norm = _normalize_name(team_label)
    sport_sr = sr_index.get(sport, {})
    if norm in sport_sr:
        return sport_sr[norm]

    sport_map = abbr_map.get(sport, {})
    for key, aliases in sport_map.items():
        names = [_normalize_name(key)] + [_normalize_name(a) for a in aliases]
        if norm in names:
            return key.upper()
    for key, aliases in sport_map.items():
        for alias in aliases:
            if _normalize_name(alias) == norm:
                return key.upper()
    for key, aliases in sport_map.items():
        for alias in aliases:
            if norm.startswith(_normalize_name(alias)) or _normalize_name(alias) in norm:
                return key.upper()
    return None


def _build_wikidata_entries(
    sport: str,
    league_qid: str,
    refresh: bool,
    abbr_map: Dict[str, Dict[str, List[str]]],
    sr_index: Dict[str, Dict[str, str]],
    tf,
) -> List[Dict[str, Any]]:
    rows = _fetch_wikidata(league_qid, refresh, f"wikidata_{sport}.json")
    entries: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        label = row.get("teamLabel", {}).get("value", "")
        team_uri = row.get("team", {}).get("value", "")
        team_q = team_uri.split("/")[-1] if team_uri else ""
        venue = row.get("venueLabel", {}).get("value")
        city = row.get("cityLabel", {}).get("value")
        lat = row.get("lat", {}).get("value")
        lon = row.get("lon", {}).get("value")
        lat_f = float(lat) if lat else None
        lon_f = float(lon) if lon else None

        key = _match_key_from_name(sport, label, abbr_map, sr_index)
        if not key:
            continue

        iana = _iana_from_coords(lat_f, lon_f, tf)
        source = f"wikidata:{team_q}" if team_q else "wikidata"
        ent = _entry(
            sport=sport,
            key=key,
            name=label,
            city=city,
            country="US",
            venue_name=venue,
            latitude=lat_f,
            longitude=lon_f,
            iana_timezone=iana,
            source=source,
            source_url=f"https://www.wikidata.org/wiki/{team_q}" if team_q else None,
        )
        entries[key] = ent
    return list(entries.values())


def _build_nfl_entries(refresh: bool, tf) -> List[Dict[str, Any]]:
    teams_csv = _fetch_url(SOURCE_URLS["nfl_teams"], refresh, "nfl_teams.csv")
    games_csv = _fetch_url(SOURCE_URLS["nfl_games"], refresh, "nfl_games.csv")
    stadiums_csv = _fetch_url(SOURCE_URLS["nfl_stadiums"], refresh, "nfl_stadiums.csv")

    stadium_by_id: Dict[str, Dict[str, str]] = {}
    reader = csv.DictReader(io.StringIO(stadiums_csv))
    for row in reader:
        sid = (row.get("stadium_id") or "").strip()
        if sid:
            stadium_by_id[sid] = row

    # Latest season only
    max_season = 0
    reader = csv.DictReader(io.StringIO(teams_csv))
    all_team_rows = list(reader)
    for row in all_team_rows:
        max_season = max(max_season, int(row.get("season") or 0))

    latest_team: Dict[str, Dict[str, str]] = {}
    for row in all_team_rows:
        if int(row.get("season") or 0) != max_season:
            continue
        abbr = (row.get("team") or row.get("team_abbr") or "").strip().upper()
        if not abbr:
            continue
        latest_team[abbr] = row

    # Most recent home stadium per team from games.csv
    team_stadium: Dict[str, str] = {}
    reader = csv.DictReader(io.StringIO(games_csv))
    games = sorted(
        [r for r in reader if (r.get("location") or "").strip().lower() == "home"],
        key=lambda r: r.get("gameday") or "",
        reverse=True,
    )
    for row in games:
        abbr = (row.get("home_team") or "").strip().upper()
        sid = (row.get("stadium_id") or "").strip()
        if abbr and sid and abbr not in team_stadium:
            team_stadium[abbr] = sid

    entries: List[Dict[str, Any]] = []
    for abbr, row in sorted(latest_team.items()):
        sr_abbr = NFLVERSE_TO_SR.get(abbr, abbr)
        name = (row.get("full") or row.get("team_name") or abbr).strip()
        sid = team_stadium.get(abbr, "")
        stad_row = stadium_by_id.get(sid, {})

        lat = stad_row.get("lat")
        lon = stad_row.get("lon")
        lat_f = float(lat) if lat else None
        lon_f = float(lon) if lon else None
        tz = stad_row.get("tz") or stad_row.get("timezone") or stad_row.get("iana_timezone")
        if not tz:
            tz = _iana_from_coords(lat_f, lon_f, tf)

        city = stad_row.get("city") or row.get("location") or row.get("short_location")
        state = stad_row.get("state")
        if city and "," in str(city):
            parts = [p.strip() for p in str(city).split(",")]
            city = parts[0]
            if not state and len(parts) > 1:
                state = _state_abbr(parts[1]) or parts[1]

        entries.append(
            _entry(
                sport="nfl",
                key=sr_abbr,
                name=name,
                city=city,
                state=state,
                venue_name=stad_row.get("stadium_name") or stad_row.get("stadium"),
                latitude=lat_f,
                longitude=lon_f,
                iana_timezone=tz,
                source="nflverse+greerreNFL",
            )
        )
    return entries


def _normalize_team_name_for_ncaa(team: str) -> str:
    t = team.lower()
    t = re.sub(
        r"\s+(wildcats|bulldogs|tigers|eagles|bears|cardinals|crimson|crimson tide|"
        r"longhorns|buckeyes|wolverines|spartans|hoosiers|boilermakers|jayhawks|"
        r"sooners|cowboys|razorbacks|gators|seminoles|hurricanes|hurricanes|"
        r"volunteers|gamecocks|tar heels|blue devils|tar heels|hokies|"
        r"cavaliers|hokies|terrapins|nittany lions|badgers|hawkeyes|cornhuskers|"
        r"golden gophers|fighting irish|trojans|bruins|ducks|beavers|huskies|"
        r"cougars|utes|buffaloes|sun devils|mountaineers|cyclones|red raiders|"
        r"horned frogs|mustangs|mean green|roadrunners|miners|lobos|"
        r"aggies|rebels|razorbacks|commodores|crimson tide|volunteers|"
        r"panthers|knights|owls|thundering herd|bearcats|billikens|"
        r"seawolves|phoenix|tribe|midshipmen|black knights|cadets|"
        r"falcons|ramblers|wolfpack|orange|orange|syracuse|"
        r"orange|demons|deacons|demon deacons|panthers|49ers|"
        r"patriots|minutemen|terriers|retrievers|greyhounds|jaspers|"
        r"gaels|stags|peacocks|friars|explorers|dukes|duquesne|"
        r"colonials|revolutionaries|terriers|bearkats|lobos|aggies|"
        r"redhawks|redbirds|salukis|shockers|hornets|hornets|hornets|"
        r"hornets|hornets|hornets|hornets)$",
        "",
        t,
    )
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _build_ncaaf_entries(refresh: bool, tf) -> List[Dict[str, Any]]:
    csv_text = _fetch_url(SOURCE_URLS["ncaaf_stadiums"], refresh, "ncaaf_stadiums.csv")
    entries: Dict[str, Dict[str, Any]] = {}
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        team = (row.get("team") or "").strip()
        if not team:
            continue
        city = (row.get("city") or "").strip()
        state = (row.get("state") or "").strip()
        stadium = (row.get("stadium") or "").strip()
        lat = row.get("latitude")
        lon = row.get("longitude")
        lat_f = float(lat) if lat else None
        lon_f = float(lon) if lon else None
        key = _slug_key(team.replace(" ", "-"))
        norm_team = _normalize_team_name_for_ncaa(team)
        if norm_team:
            key = _slug_key(norm_team.replace(" ", "-"))

        entries[key] = _entry(
            sport="ncaaf",
            key=key,
            name=team,
            city=city,
            state=state,
            venue_name=stadium,
            latitude=lat_f,
            longitude=lon_f,
            iana_timezone=_iana_from_coords(lat_f, lon_f, tf),
            source="gboeing-ncaaf-stadiums",
        )
    return list(entries.values())


def _fetch_ipeds_txt(refresh: bool) -> str:
    path = RAW_DIR / "ipeds_postsec.txt"
    if path.exists() and not refresh:
        return path.read_text(encoding="utf-8", errors="replace")
    try:
        import io as _io
        import zipfile

        import requests

        resp = requests.get(
            SOURCE_URLS["ipeds_zip"],
            timeout=180,
            headers={"User-Agent": "iptv-proxy-v2-build/1.0"},
        )
        resp.raise_for_status()
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(_io.BytesIO(resp.content)) as zf:
            txt_name = next(n for n in zf.namelist() if n.endswith(".TXT"))
            text = zf.read(txt_name).decode("utf-8", errors="replace")
        path.write_text(text, encoding="utf-8")
        return text
    except Exception as exc:
        if path.exists():
            print(f"Warning: IPEDS fetch failed: {exc}; using cached {path}", file=sys.stderr)
            return path.read_text(encoding="utf-8", errors="replace")
        raise


def _build_ncaab_entries(refresh: bool, tf) -> List[Dict[str, Any]]:
    """Match NCES IPEDS institution names to college keys."""
    txt = _fetch_ipeds_txt(refresh)
    entries: Dict[str, Dict[str, Any]] = {}
    for line in txt.splitlines():
        parts = line.split("|")
        if len(parts) < 12:
            continue
        name = parts[1].strip()
        city = parts[3].strip() or None
        state = parts[4].strip() or None
        lat_f = float(parts[10])
        lon_f = float(parts[11])
        norm = _normalize_name(name)
        key = _slug_key(re.sub(r"\s+(university|college|institute|school).*$", "", norm, flags=re.I))
        if len(key) < 3:
            continue
        iana = _iana_from_coords(lat_f, lon_f, tf)
        entries[key] = _entry(
            sport="ncaab",
            key=key,
            name=name,
            city=city,
            state=state,
            latitude=lat_f,
            longitude=lon_f,
            iana_timezone=iana,
            source="nces-ipeds-edge",
        )
    return list(entries.values())


def _build_milb_entries(refresh: bool, tf, season: Optional[int] = None) -> List[Dict[str, Any]]:
    """Build MiLB team entries from MLB Stats API (sportIds 11–14)."""
    from services.mlb_stats_api import MILB_SPORT_IDS, get_mlb_stats_client

    season = season or date.today().year
    client = get_mlb_stats_client()
    venue_cache: Dict[int, Dict[str, Any]] = {}
    entries: Dict[str, Dict[str, Any]] = {}

    for sport_id in MILB_SPORT_IDS:
        try:
            teams = client.get_teams(sport_id, season=season)
        except Exception as exc:
            print(f"Warning: MiLB teams sportId={sport_id} failed: {exc}", file=sys.stderr)
            continue
        level = {11: "Triple-A", 12: "Double-A", 13: "High-A", 14: "Single-A"}.get(sport_id, str(sport_id))
        for team in teams:
            team_id = team.get("id")
            name = team.get("name") or ""
            if team_id is None or not name:
                continue
            key = str(team_id)
            venue_info = team.get("venue") or {}
            venue_id = venue_info.get("id")
            lat_f = lon_f = None
            city = team.get("locationName")
            state = None
            country = "US"
            venue_name = venue_info.get("name")
            if venue_id is not None:
                vid = int(venue_id)
                if vid not in venue_cache or refresh:
                    try:
                        venue_cache[vid] = client.get_venue(vid) or {}
                    except Exception:
                        venue_cache[vid] = {}
                venue = venue_cache.get(vid) or {}
                if venue.get("name"):
                    venue_name = venue.get("name")
                loc = venue.get("location") or {}
                if loc.get("city"):
                    city = loc.get("city")
                state = loc.get("stateAbbrev") or loc.get("state")
                if loc.get("country"):
                    country = loc.get("country")
                coords = loc.get("defaultCoordinates") or {}
                lat = coords.get("latitude")
                lon = coords.get("longitude")
                if lat is not None and lon is not None:
                    lat_f = float(lat)
                    lon_f = float(lon)

            aliases: List[str] = []
            for field in ("teamName", "locationName", "clubName", "shortName"):
                val = team.get(field)
                if val:
                    aliases.append(str(val))
            loc_name = team.get("locationName") or ""
            club = team.get("clubName") or team.get("teamName") or ""
            if loc_name and club:
                aliases.append(f"{loc_name} {club}")

            league_name = (team.get("league") or {}).get("name")
            entries[key] = _entry(
                sport="milb",
                key=key,
                name=name,
                city=city,
                state=state,
                country=country or "US",
                venue_name=venue_name,
                latitude=lat_f,
                longitude=lon_f,
                iana_timezone=_iana_from_coords(lat_f, lon_f, tf),
                source="mlb_stats_api",
                source_url=f"https://statsapi.mlb.com/api/v1/teams/{team_id}",
                aliases=aliases,
                league=f"{level} | {league_name}" if league_name else level,
            )

    return list(entries.values())


def _merge_entries(*groups: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for group in groups:
        for ent in group:
            k = (ent["sport"], _registry_merge_key(ent["sport"], ent["key"]))
            if k not in merged:
                merged[k] = ent
            else:
                existing = merged[k]
                if not existing.get("city") and ent.get("city"):
                    merged[k] = ent
                elif not existing.get("iana_timezone") and ent.get("iana_timezone"):
                    existing["iana_timezone"] = ent["iana_timezone"]
                if ent.get("aliases"):
                    existing_aliases = set(existing.get("aliases") or [])
                    existing_aliases.update(ent.get("aliases") or [])
                    existing["aliases"] = sorted(existing_aliases)
    return merged


def _load_fb_leagues() -> List[Dict[str, str]]:
    if not FB_LEAGUES_PATH.exists():
        return []
    data = json.loads(FB_LEAGUES_PATH.read_text(encoding="utf-8"))
    return list(data.get("leagues", []))


def _configure_thesportsdb_for_build() -> str:
    """Configure SDK and return active API key (default '3')."""
    import os

    env_key = os.environ.get("THESPORTSDB_API_KEY", "").strip()
    if env_key:
        import thesportsdb.settings as tsd_settings

        tsd_settings.API_KEY = env_key
        return env_key
    try:
        sys.path.insert(0, str(ROOT))
        from services.thesportsdb_api import resolve_thesportsdb_api_key

        api_key = resolve_thesportsdb_api_key()
        if api_key:
            import thesportsdb.settings as tsd_settings

            tsd_settings.API_KEY = api_key
            return api_key
        from services.thesportsdb_service import configure_thesportsdb_api_key

        configure_thesportsdb_api_key()
        import thesportsdb.settings as tsd_settings

        return str(tsd_settings.API_KEY or "3")
    except Exception:
        import thesportsdb.settings as tsd_settings

        tsd_settings.API_KEY = "3"
        return "3"


def _tsdb_uses_v2_api(api_key: str) -> bool:
    from services.thesportsdb_api import uses_v2_api

    return uses_v2_api(api_key)


def _tsdb_v2_get(path: str, api_key: str) -> Optional[Dict[str, Any]]:
    from services.thesportsdb_api import v2_get

    return v2_get(path, api_key)


def _parse_stadium_location(location: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not location or not str(location).strip():
        return None, None
    parts = [p.strip() for p in str(location).split(",") if p.strip()]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    country = parts[-1]
    city = parts[-2] if len(parts) >= 2 else parts[0]
    return city, country


def _fb_iana_timezone(
    city: Optional[str],
    country: Optional[str],
    lat: Optional[float],
    lon: Optional[float],
    tf,
) -> Optional[str]:
    tz = _iana_from_coords(lat, lon, tf)
    if tz:
        return tz
    sys.path.insert(0, str(ROOT))
    from services.ppv.city_timezone_map import iana_for_city

    return iana_for_city(city, country)


def _fb_team_aliases(team: Dict[str, Any]) -> List[str]:
    aliases: List[str] = []
    for field in ("strTeamAlternate", "strTeamShort", "strKeywords"):
        raw = team.get(field)
        if not raw:
            continue
        for part in re.split(r"[,;/]", str(raw)):
            part = part.strip().lower()
            if part and len(part) >= 2:
                aliases.append(part)
    name = (team.get("strTeam") or "").strip().lower()
    if name:
        aliases.append(name)
    return sorted(set(aliases))


def _fetch_tsdb_team_info(team_id: str, refresh: bool, api_key: str) -> Optional[Dict[str, Any]]:
    path = TSDB_RAW_DIR / f"team_{team_id}.json"
    if path.exists() and not refresh:
        data = json.loads(path.read_text(encoding="utf-8"))
        teams_list = data.get("teams") or []
        if teams_list:
            return teams_list[0]
        lookup = data.get("lookup") or []
        return lookup[0] if lookup else None

    import time

    if _tsdb_uses_v2_api(api_key):
        result = _tsdb_v2_get(f"lookup/team/{team_id}", api_key)
        team = (result or {}).get("lookup", [{}])[0] if result else None
    else:
        from thesportsdb import teams as tsdb_teams

        result = tsdb_teams.teamInfo(team_id)
        if not isinstance(result, dict):
            return None
        team = (result.get("teams") or [None])[0]

    if not team:
        return None
    TSDB_RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache = {"teams": [team]} if "teams" in (result or {}) else result
    path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    time.sleep(0.35)
    return team


def _fetch_tsdb_league_teams(league_id: str, refresh: bool, api_key: str) -> List[Dict[str, Any]]:
    path = TSDB_RAW_DIR / f"league_{league_id}.json"
    if path.exists() and not refresh:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("teams") or data.get("list") or data.get("results") or [])

    import time

    if _tsdb_uses_v2_api(api_key):
        result = _tsdb_v2_get(f"list/teams/{league_id}", api_key)
        teams = list((result or {}).get("list") or [])
        cache = {"teams": teams}
    else:
        from thesportsdb import teams as tsdb_teams

        result = tsdb_teams.leagueTeams(league_id)
        if not isinstance(result, dict):
            return []
        teams = list(result.get("teams") or result.get("results") or [])
        cache = result

    TSDB_RAW_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    time.sleep(0.5)
    return teams


def _build_tsdb_league_entries(refresh: bool, tf, sport_default: str = "fb") -> List[Dict[str, Any]]:
    """Build registry entries from TheSportsDB league team lists."""
    leagues = _load_fb_leagues()
    if not leagues:
        return []

    api_key = _configure_thesportsdb_for_build()
    if _tsdb_uses_v2_api(api_key):
        print("Using TheSportsDB V2 API (premium key)", file=sys.stderr)

    entries: Dict[str, Dict[str, Any]] = {}
    for league in leagues:
        league_id = str(league.get("id", "")).strip()
        league_name = str(league.get("name") or "").strip()
        sport = str(league.get("sport") or sport_default).strip().lower()
        if not league_id:
            continue
        if sport == "wnba" and not _tsdb_uses_v2_api(api_key):
            print(
                f"Warning: WNBA league {league_id} requires premium V2 API; skipping",
                file=sys.stderr,
            )
            continue
        try:
            teams_list = _fetch_tsdb_league_teams(league_id, refresh, api_key)
        except Exception as exc:
            print(f"Warning: TheSportsDB league {league_id} failed: {exc}", file=sys.stderr)
            continue

        for stub in teams_list:
            team_id = str(stub.get("idTeam") or "").strip()
            if not team_id:
                continue
            entry_key = f"{sport}:{team_id}"
            if entry_key in entries:
                continue

            team = stub
            if not stub.get("strStadiumLocation") and not stub.get("strLocation"):
                try:
                    detailed = _fetch_tsdb_team_info(team_id, refresh, api_key)
                    if detailed:
                        team = detailed
                except Exception as exc:
                    print(f"Warning: TheSportsDB team {team_id} lookup failed: {exc}", file=sys.stderr)

            name = (team.get("strTeam") or stub.get("strTeam") or team_id).strip()
            location_raw = team.get("strStadiumLocation") or team.get("strLocation") or team.get("strStadium")
            city, country = _parse_stadium_location(location_raw)
            if not country:
                country = team.get("strCountry") or stub.get("strCountry")
            venue = team.get("strStadium") or stub.get("strStadium")
            lat = team.get("strStadiumLat") or team.get("strLatitude")
            lon = team.get("strStadiumLon") or team.get("strLongitude")
            lat_f = float(lat) if lat else None
            lon_f = float(lon) if lon else None
            iana = _fb_iana_timezone(city, country, lat_f, lon_f, tf)
            aliases = _fb_team_aliases(team)

            entries[entry_key] = _entry(
                sport=sport,
                key=team_id,
                name=name,
                city=city,
                country=country,
                venue_name=venue,
                latitude=lat_f,
                longitude=lon_f,
                iana_timezone=iana,
                source=f"thesportsdb:{team_id}",
                source_url=f"https://www.thesportsdb.com/team/{team_id}",
                aliases=aliases,
                thesportsdb_id=team_id,
                league=league_name or team.get("strLeague"),
            )

    return list(entries.values())


def _build_fb_entries(refresh: bool, tf) -> List[Dict[str, Any]]:
    """Backward-compatible alias for TheSportsDB league registry build."""
    return _build_tsdb_league_entries(refresh, tf)


def _tsdb_coverage_report(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-sport coverage stats for TheSportsDB-sourced registry entries."""
    by_sport: Dict[str, Dict[str, Any]] = {}
    for ent in entries:
        sport = ent.get("sport") or "unknown"
        if sport not in by_sport:
            by_sport[sport] = {
                "total": 0,
                "with_city": 0,
                "with_iana_timezone": 0,
                "by_league": {},
            }
        bucket = by_sport[sport]
        bucket["total"] += 1
        league = ent.get("league") or "unknown"
        bucket["by_league"][league] = bucket["by_league"].get(league, 0) + 1
        if ent.get("city"):
            bucket["with_city"] += 1
        if ent.get("iana_timezone"):
            bucket["with_iana_timezone"] += 1

    report: Dict[str, Any] = {}
    for sport, bucket in by_sport.items():
        total = bucket["total"]
        report[sport] = {
            "total": total,
            "with_city": bucket["with_city"],
            "with_iana_timezone": bucket["with_iana_timezone"],
            "by_league": bucket["by_league"],
            "city_pct": round(100.0 * bucket["with_city"] / total, 1) if total else 0.0,
            "tz_pct": round(100.0 * bucket["with_iana_timezone"] / total, 1) if total else 0.0,
        }
    return report


def build_registry(refresh: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    tf = None
    try:
        from timezonefinder import TimezoneFinder

        tf = TimezoneFinder()
    except ImportError:
        print("Warning: timezonefinder not installed; IANA TZ from coords disabled", file=sys.stderr)

    abbr_map = _load_abbr_map()
    sr_index = _load_sr_name_index()
    overrides = _load_overrides()

    all_entries: List[Dict[str, Any]] = []
    all_entries.extend(_build_nfl_entries(refresh, tf))
    for sport, qid in LEAGUE_QIDS.items():
        try:
            all_entries.extend(_build_wikidata_entries(sport, qid, refresh, abbr_map, sr_index, tf))
        except Exception as exc:
            print(f"Warning: Wikidata fetch for {sport} failed: {exc}", file=sys.stderr)

    try:
        all_entries.extend(_build_ncaaf_entries(refresh, tf))
    except Exception as exc:
        print(f"Warning: NCAAF build failed: {exc}", file=sys.stderr)

    try:
        all_entries.extend(_build_ncaab_entries(refresh, tf))
    except Exception as exc:
        print(f"Warning: NCAAB build failed: {exc}", file=sys.stderr)

    tsdb_entries: List[Dict[str, Any]] = []
    try:
        tsdb_entries = _build_tsdb_league_entries(refresh, tf)
        all_entries.extend(tsdb_entries)
    except Exception as exc:
        print(f"Warning: TheSportsDB league build failed: {exc}", file=sys.stderr)

    try:
        all_entries.extend(_build_milb_entries(refresh, tf))
    except Exception as exc:
        print(f"Warning: MiLB build failed: {exc}", file=sys.stderr)

    merged = _merge_entries(all_entries)
    for ovr in overrides:
        k = (ovr["sport"], _registry_merge_key(ovr["sport"], ovr["key"]))
        merged[k] = {**merged.get(k, {}), **ovr}

    entries = sorted(merged.values(), key=lambda e: (e["sport"], e["key"]))
    version = date.today().isoformat()
    registry = {"version": version, "entries": entries}

    coverage: Dict[str, int] = {}
    for ent in entries:
        coverage[ent["sport"]] = coverage.get(ent["sport"], 0) + 1

    meta = {
        "built_at": version,
        "entry_count": len(entries),
        "coverage_by_sport": coverage,
        "sources": list(SOURCE_URLS.values()) + [WIKIDATA_SPARQL, "thesportsdb", "mlb_stats_api"],
    }
    if tsdb_entries:
        meta["tsdb_coverage"] = _tsdb_coverage_report(tsdb_entries)
    return registry, meta


def main() -> int:
    parser = argparse.ArgumentParser(description="Build team location registry JSON")
    parser.add_argument("--refresh", action="store_true", help="Re-download raw source files")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    registry, meta = build_registry(refresh=args.refresh)
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    META_PATH.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {len(registry['entries'])} entries to {REGISTRY_PATH}")
    print("Coverage by sport:", meta["coverage_by_sport"])
    if meta.get("tsdb_coverage"):
        print("TheSportsDB coverage:", meta["tsdb_coverage"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
