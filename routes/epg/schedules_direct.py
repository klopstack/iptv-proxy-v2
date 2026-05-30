"""
Schedules Direct API integration routes
"""
import logging
from typing import Any

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import Account, EpgSource, SdLineup, SdStation, db
from services.schedules_direct import SchedulesDirectClient, SchedulesDirectError

logger = logging.getLogger(__name__)

# Create blueprint
schedules_direct_bp = Blueprint("schedules_direct", __name__, url_prefix="/api/epg/sd")

__all__ = ["schedules_direct_bp"]


# ============================================================================
# API Routes - Schedules Direct Integration
# ============================================================================


@schedules_direct_bp.route("/test", methods=["POST"])
@handle_errors(return_json=True, default_message="Error testing Schedules Direct credentials")
def test_sd_credentials():
    """Test Schedules Direct credentials

    Request body:
        username: SD username
        password: SD password
    """
    from services.schedules_direct import validate_credentials

    data = request.json

    if not data.get("username") or not data.get("password"):
        return jsonify({"error": "Username and password are required"}), 400

    result = validate_credentials(data["username"], data["password"])

    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 401


@schedules_direct_bp.route("/lineups/search", methods=["GET"])
@handle_errors(return_json=True, default_message="Error searching Schedules Direct lineups")
def search_sd_lineups():
    """Search for Schedules Direct lineups by location

    Query parameters:
        source_id: EPG source ID with SD credentials
        country: ISO country code (default: USA)
        postalcode: Postal/ZIP code to search
    """
    source_id = request.args.get("source_id", type=int)
    country = request.args.get("country", "USA")
    postalcode = request.args.get("postalcode")

    if not source_id:
        return jsonify({"success": False, "error": "source_id is required"}), 400

    source = EpgSource.query.get_or_404(source_id)

    if source.source_type != "schedules_direct":
        return jsonify({"success": False, "error": "Source is not a Schedules Direct source"}), 400

    if not source.sd_username or not source.sd_password:
        return jsonify({"success": False, "error": "Source does not have SD credentials configured"}), 400

    try:
        client = SchedulesDirectClient(source.sd_username, source.sd_password)
        client.authenticate()

        lineups = client.search_lineups(country=country, postalcode=postalcode)

        return jsonify(
            {
                "success": True,
                "country": country,
                "postalcode": postalcode,
                "lineups": lineups,
                "count": len(lineups),
            }
        )

    except SchedulesDirectError as e:
        return jsonify({"success": False, "error": str(e), "code": e.code}), 400


@schedules_direct_bp.route("/lineups", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching SD lineups")
def get_sd_lineups():
    """Get Schedules Direct lineups for an EPG source

    Query parameters:
        source_id: EPG source ID

    Returns:
        JSON object with:
        - lineups: Array of lineup objects
        - account_lineups: Number of lineups on SD account (from API)
        - max_lineups: Maximum lineups allowed (typically 4)
    """
    source_id = request.args.get("source_id", type=int)

    if not source_id:
        return jsonify({"success": False, "error": "source_id is required"}), 400

    source = EpgSource.query.get_or_404(source_id)

    # Get lineups from database
    lineups = SdLineup.query.filter_by(epg_source_id=source_id).all()

    # Convert to dictionaries and detach from session before making external calls
    lineup_data = [
        {
            "id": lineup.id,
            "lineup_id": lineup.lineup_id,
            "name": lineup.name,
            "location": lineup.location,
            "lineup_type": lineup.lineup_type,
            "transport": lineup.transport,
            "channel_count": lineup.channel_count,
            "last_sync": lineup.last_sync.isoformat() if lineup.last_sync else None,
        }
        for lineup in lineups
    ]

    # Store source credentials before closing session
    sd_username = source.sd_username
    sd_password = source.sd_password

    # Get account status to determine lineup limits
    account_lineups = 0
    max_lineups = 4  # SD default limit
    try:
        if sd_username and sd_password:
            client = SchedulesDirectClient(sd_username, sd_password)
            client.authenticate()
            status = client.get_status()
            account_lineups = len(status.get("lineups", []))
            account_info = status.get("account", {})
            max_lineups = account_info.get("maxLineups", 4)
    except Exception as e:
        logger.warning(f"Could not get SD account status: {e}")

    return jsonify(
        {
            "lineups": lineup_data,
            "account_lineups": account_lineups,
            "max_lineups": max_lineups,
        }
    )


@schedules_direct_bp.route("/lineups", methods=["POST"])
@handle_errors(return_json=True, default_message="Error adding SD lineup")
def add_sd_lineup():
    """Add a Schedules Direct lineup to an EPG source

    Request body:
        source_id: EPG source ID
        lineup_id: SD lineup ID (e.g., "USA-NY12345-X")
        name: Optional display name
        location: Optional location
        lineup_type: Optional type (Cable, Satellite, OTA)
    """
    from .common import sync_sd_lineup_impl

    data = request.json

    if not data.get("source_id") or not data.get("lineup_id"):
        return jsonify({"error": "source_id and lineup_id are required"}), 400

    source = EpgSource.query.get_or_404(data["source_id"])

    if source.source_type != "schedules_direct":
        return jsonify({"error": "Source is not a Schedules Direct source"}), 400

    # Check if lineup already exists in our database
    existing = SdLineup.query.filter_by(epg_source_id=source.id, lineup_id=data["lineup_id"]).first()

    if existing:
        return jsonify({"error": "Lineup already added to this source"}), 409

    # Store credentials before making external calls
    sd_username = source.sd_username
    sd_password = source.sd_password
    source_id = source.id

    # Check SD account lineup limit before adding
    try:
        if sd_username and sd_password:
            client = SchedulesDirectClient(sd_username, sd_password)
            client.authenticate()
            status = client.get_status()
            account_lineups = status.get("lineups", [])
            account_info = status.get("account", {})
            max_lineups = account_info.get("maxLineups", 4)

            # Check if lineup is already on the SD account
            account_lineup_ids = [lineup.get("lineup") for lineup in account_lineups]
            if data["lineup_id"] not in account_lineup_ids:
                # Need to add to SD account - check limit
                if len(account_lineups) >= max_lineups:
                    return (
                        jsonify(
                            {
                                "error": f"Schedules Direct account limit reached ({max_lineups} lineups). "
                                "Please remove a lineup before adding a new one.",
                                "limit_reached": True,
                                "current_count": len(account_lineups),
                                "max_lineups": max_lineups,
                            }
                        ),
                        400,
                    )
    except SchedulesDirectError as e:
        logger.warning(f"Could not check SD account limit: {e}")
        # Continue anyway - the add_lineup call will fail if at limit

    # Create lineup record
    lineup = SdLineup(
        epg_source_id=source_id,
        lineup_id=data["lineup_id"],
        name=data.get("name"),
        location=data.get("location"),
        lineup_type=data.get("lineup_type"),
        transport=data.get("transport"),
    )

    db.session.add(lineup)
    db.session.commit()

    # Optionally add to SD account and sync channels
    if request.args.get("sync", "false").lower() == "true":
        try:
            sync_result = sync_sd_lineup_impl(source, lineup)
            return jsonify(
                {
                    "success": True,
                    "lineup_id": lineup.id,
                    "message": f"Lineup added and synced ({sync_result['channels_synced']} channels)",
                    "sync_result": sync_result,
                }
            )
        except SchedulesDirectError as e:
            return jsonify(
                {
                    "success": True,
                    "lineup_id": lineup.id,
                    "message": "Lineup added but sync failed",
                    "sync_error": str(e),
                }
            )

    return (
        jsonify(
            {
                "success": True,
                "lineup_id": lineup.id,
                "message": "Lineup added successfully",
            }
        ),
        201,
    )


@schedules_direct_bp.route("/lineups/<int:lineup_id>/sync", methods=["POST"])
@handle_errors(return_json=True, default_message="Error syncing SD lineup")
def sync_sd_lineup(lineup_id):
    """Sync channels from a Schedules Direct lineup"""
    from .common import sync_sd_lineup_impl

    lineup = SdLineup.query.get_or_404(lineup_id)
    source = lineup.source

    if not source.sd_username or not source.sd_password:
        return jsonify({"error": "Source does not have SD credentials configured"}), 400

    try:
        from services.epg_sync_orchestrator import try_acquire_epg_sync_lock
        from services.sd_lineup_sync_progress import (
            PHASE_CHANNELS,
            PHASE_COMPLETE,
            PHASE_ERROR,
            PHASE_FETCHING,
            PHASE_QUEUED,
            SdLineupSyncProgress,
        )

        force = request.args.get("force", "false").lower() in ("1", "true", "yes")
        if not try_acquire_epg_sync_lock(source.id, force=force):
            return jsonify({"error": "Sync already in progress for this source"}), 409

        SdLineupSyncProgress.set_phase(lineup.id, PHASE_QUEUED, message="Waiting to start")

        def on_progress(phase: str, message: str = "", **counts: Any) -> None:
            mapped = {
                "fetching": PHASE_FETCHING,
                "channels": PHASE_CHANNELS,
            }.get(phase, phase)
            SdLineupSyncProgress.set_phase(lineup.id, mapped, message=message, **counts)

        try:
            result = sync_sd_lineup_impl(source, lineup, progress_callback=on_progress)
            total_synced = result["channels_synced"] + result["channels_updated"]
            SdLineupSyncProgress.set_phase(
                lineup.id,
                PHASE_COMPLETE,
                message=f"Synced {total_synced} channels ({result['channels_synced']} new, {result['channels_updated']} updated)",
                **result,
            )
        except Exception as exc:
            SdLineupSyncProgress.set_phase(lineup.id, PHASE_ERROR, message=str(exc))
            raise
        finally:
            # Release source lock (lineup-level sync uses source lock to enforce one-at-a-time).
            source.sync_in_progress = False
            db.session.commit()

        return jsonify(
            {
                "success": True,
                "message": f"Synced {total_synced} channels ({result['channels_synced']} new, {result['channels_updated']} updated)",
                **result,
            }
        )
    except SchedulesDirectError as e:
        return jsonify({"error": str(e), "code": e.code}), 400


@schedules_direct_bp.route("/lineups/<int:lineup_id>/status", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching SD lineup status")
def get_sd_lineup_status(lineup_id):
    from services.sd_lineup_sync_progress import SdLineupSyncProgress

    lineup = SdLineup.query.get_or_404(lineup_id)
    return jsonify({"success": True, "status": SdLineupSyncProgress.snapshot(lineup)})


@schedules_direct_bp.route("/lineups/status", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching SD lineup statuses")
def get_sd_lineup_statuses():
    from services.sd_lineup_sync_progress import SdLineupSyncProgress

    source_id = request.args.get("source_id", type=int)
    if not source_id:
        return jsonify({"error": "source_id is required"}), 400

    lineups = SdLineup.query.filter_by(epg_source_id=source_id).order_by(SdLineup.name, SdLineup.id).all()
    return jsonify({"success": True, "statuses": [SdLineupSyncProgress.snapshot(lineup) for lineup in lineups]})


@schedules_direct_bp.route("/lineups/<int:lineup_id>", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error removing SD lineup")
def remove_sd_lineup(lineup_id):
    """Remove a Schedules Direct lineup"""
    lineup = SdLineup.query.get_or_404(lineup_id)
    source = lineup.source

    # Remove from SD account first to free up the lineup slot
    if source.sd_username and source.sd_password:
        try:
            client = SchedulesDirectClient(source.sd_username, source.sd_password)
            client.authenticate()
            client.remove_lineup(lineup.lineup_id)
            logger.info(f"Removed lineup {lineup.lineup_id} from SD account")
        except SchedulesDirectError as e:
            # Log warning but continue with database deletion
            # Error code 2101 = LINEUP_NOT_FOUND means it was already removed
            if e.code != 2101:
                logger.warning(f"Could not remove lineup from SD account: {e}")
        except Exception as e:
            logger.warning(f"Error removing lineup from SD account: {e}")

    # Delete associated stations first (cascade should handle this, but being explicit)
    SdStation.query.filter_by(lineup_id=lineup_id).delete()

    db.session.delete(lineup)
    db.session.commit()

    return jsonify({"success": True, "message": "Lineup removed successfully"})


@schedules_direct_bp.route("/lineups/<int:lineup_id>/stations", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching SD stations")
def get_sd_lineup_stations(lineup_id):
    """Get stations in a Schedules Direct lineup

    Query parameters:
        search: Optional search term for name/callsign
    """
    lineup = SdLineup.query.get_or_404(lineup_id)

    search = request.args.get("search", "").strip()

    query = SdStation.query.filter_by(lineup_id=lineup_id)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                SdStation.callsign.ilike(search_term),
                SdStation.name.ilike(search_term),
            )
        )

    stations = query.order_by(SdStation.channel_number, SdStation.callsign).all()

    return jsonify(
        {
            "lineup_id": lineup.lineup_id,
            "lineup_name": lineup.name,
            "count": len(stations),
            "stations": [
                {
                    "id": s.id,
                    "station_id": s.station_id,
                    "channel_number": s.channel_number,
                    "callsign": s.callsign,
                    "name": s.name,
                    "affiliate": s.affiliate,
                    "logo_url": s.logo_url,
                }
                for s in stations
            ],
        }
    )


@schedules_direct_bp.route("/match/<int:account_id>", methods=["POST"])
@handle_errors(return_json=True, default_message="Error matching SD stations to channels")
def match_sd_stations(account_id):
    """Match Schedules Direct stations to IPTV channels

    This uses callsign and station name matching to find corresponding
    IPTV channels. It also handles XMLTV-style IDs (e.g., "ESPN.us" -> "ESPN").

    Request body:
        source_id: EPG source ID (required)
        lineup_id: SD lineup ID (optional - if not provided, uses all lineups)
        match_mode: 'exact', 'fuzzy', or 'all' (default: 'all')
        min_confidence: Minimum fuzzy match confidence (default: 0.8)
    """
    import re
    from difflib import SequenceMatcher

    from models import Channel

    def extract_callsign_from_xmltv_id(xmltv_id: str) -> str:
        """
        Extract callsign from XMLTV-style channel IDs.

        Examples:
            "ESPN.us" -> "ESPN"
            "AntennaTV.us" -> "AntennaTV"
            "I10021.json.schedulesdirect.org" -> "10021"
            "CNN" -> "CNN"
        """
        if not xmltv_id:
            return ""

        # Common patterns for XMLTV IDs:
        # 1. CALLSIGN.country (e.g., "ESPN.us", "BBC1.uk")
        # 2. I{station_id}.json.schedulesdirect.org (SD format)
        # 3. Just the callsign

        # Pattern: I{digits}.json.schedulesdirect.org
        sd_match = re.match(r"I(\d+)\.json\.schedulesdirect\.org", xmltv_id, re.IGNORECASE)
        if sd_match:
            return sd_match.group(1)

        # Pattern: CALLSIGN.tld or CALLSIGN.country
        dot_match = re.match(r"^([A-Za-z0-9]+(?:[A-Za-z0-9-]*[A-Za-z0-9])?)\..*$", xmltv_id)
        if dot_match:
            return dot_match.group(1)

        return xmltv_id

    Account.query.get_or_404(account_id)
    data = request.json or {}

    source_id = data.get("source_id")
    if not source_id:
        return jsonify({"error": "source_id is required"}), 400

    _source = EpgSource.query.get_or_404(source_id)  # noqa: F841 (validates source exists)
    lineup_id = data.get("lineup_id")
    match_mode = data.get("match_mode", "all")
    min_confidence = float(data.get("min_confidence", 0.8))

    # Get stations to match
    station_query = SdStation.query.join(SdLineup).filter(SdLineup.epg_source_id == source_id)
    if lineup_id:
        station_query = station_query.filter(SdStation.lineup_id == lineup_id)
    stations = station_query.all()

    # Get channels for this account
    channels = Channel.query.filter_by(account_id=account_id, is_active=True).all()

    # Build channel lookup structures
    # Include both exact name and extracted callsign from XMLTV ID
    channel_by_name_lower = {}
    channel_by_epg_id = {}
    channel_by_epg_callsign = {}  # Extracted callsign from XMLTV ID
    all_channels = []

    for ch in channels:
        name_lower = (ch.cleaned_name or ch.name).lower()
        channel_by_name_lower[name_lower] = ch

        if ch.epg_channel_id:
            epg_id_lower = ch.epg_channel_id.lower()
            channel_by_epg_id[epg_id_lower] = ch

            # Extract callsign from XMLTV-style ID
            extracted = extract_callsign_from_xmltv_id(ch.epg_channel_id)
            if extracted:
                channel_by_epg_callsign[extracted.lower()] = ch

        all_channels.append(
            {
                "channel": ch,
                "name_lower": name_lower,
                "name": ch.cleaned_name or ch.name,
                "epg_id": ch.epg_channel_id,
            }
        )

    matches = []
    unmatched_stations = []
    unmatched_channels = set(ch.id for ch in channels)

    for station in stations:
        match_found = False
        best_match = None
        best_confidence = 0
        match_type = None

        callsign = (station.callsign or "").strip()
        station_name = (station.name or "").strip()
        station_id = station.station_id  # Numeric SD station ID

        # Strategy 1: Exact callsign match against channel name
        if match_mode in ("exact", "all"):
            if callsign:
                callsign_lower = callsign.lower()

                # Check against channel names
                if callsign_lower in channel_by_name_lower:
                    best_match = channel_by_name_lower[callsign_lower]
                    best_confidence = 1.0
                    match_type = "exact_callsign_to_name"
                    match_found = True

                # Check against EPG IDs (exact)
                elif callsign_lower in channel_by_epg_id:
                    best_match = channel_by_epg_id[callsign_lower]
                    best_confidence = 1.0
                    match_type = "exact_callsign_to_epg_id"
                    match_found = True

                # Check against extracted callsigns from XMLTV IDs
                elif callsign_lower in channel_by_epg_callsign:
                    best_match = channel_by_epg_callsign[callsign_lower]
                    best_confidence = 1.0
                    match_type = "exact_callsign_to_xmltv"
                    match_found = True

        # Strategy 2: Match SD station ID to XMLTV ID containing it
        if not match_found and match_mode in ("exact", "all"):
            if station_id:
                # Check if any channel's XMLTV ID contains this station ID
                # e.g., "I10021.json.schedulesdirect.org" contains "10021"
                for ch_data in all_channels:
                    if ch_data["epg_id"] and station_id in ch_data["epg_id"]:
                        best_match = ch_data["channel"]
                        best_confidence = 1.0
                        match_type = "exact_station_id_in_xmltv"
                        match_found = True
                        break

        # Strategy 3: Exact station name match
        if not match_found and match_mode in ("exact", "all"):
            if station_name:
                name_lower = station_name.lower()
                if name_lower in channel_by_name_lower:
                    best_match = channel_by_name_lower[name_lower]
                    best_confidence = 1.0
                    match_type = "exact_name"
                    match_found = True

        # Strategy 4: Fuzzy matching
        if not match_found and match_mode in ("fuzzy", "all"):
            # Try fuzzy match against all channels
            search_terms = [callsign, station_name]
            search_terms = [t for t in search_terms if t]

            for term in search_terms:
                term_lower = term.lower()
                for ch_data in all_channels:
                    # Match against channel name
                    ratio = SequenceMatcher(None, term_lower, ch_data["name_lower"]).ratio()
                    if ratio >= min_confidence and ratio > best_confidence:
                        best_match = ch_data["channel"]
                        best_confidence = ratio
                        match_type = "fuzzy_name"
                        match_found = True

                    # Also match against extracted XMLTV callsign
                    if ch_data["epg_id"]:
                        extracted = extract_callsign_from_xmltv_id(ch_data["epg_id"])
                        if extracted:
                            ratio = SequenceMatcher(None, term_lower, extracted.lower()).ratio()
                            if ratio >= min_confidence and ratio > best_confidence:
                                best_match = ch_data["channel"]
                                best_confidence = ratio
                                match_type = "fuzzy_xmltv"
                                match_found = True

        if match_found and best_match:
            matches.append(
                {
                    "station_id": station.id,
                    "sd_station_id": station.station_id,
                    "station_callsign": station.callsign,
                    "station_name": station.name,
                    "channel_id": best_match.id,
                    "channel_name": best_match.cleaned_name or best_match.name,
                    "channel_epg_id": best_match.epg_channel_id,
                    "confidence": round(best_confidence, 3),
                    "match_type": match_type,
                }
            )
            unmatched_channels.discard(best_match.id)
        else:
            unmatched_stations.append(
                {
                    "station_id": station.id,
                    "sd_station_id": station.station_id,
                    "station_callsign": station.callsign,
                    "station_name": station.name,
                    "channel_number": station.channel_number,
                }
            )

    return jsonify(
        {
            "account_id": account_id,
            "source_id": source_id,
            "stats": {
                "total_stations": len(stations),
                "matched": len(matches),
                "unmatched_stations": len(unmatched_stations),
                "unmatched_channels": len(unmatched_channels),
            },
            "matches": matches,
            "unmatched_stations": unmatched_stations[:100],  # Limit for response size
        }
    )


@schedules_direct_bp.route("/status", methods=["GET"])
@handle_errors(return_json=True, default_message="Error checking SD status")
def get_sd_status():
    """Get Schedules Direct system status (no auth required)"""
    client = SchedulesDirectClient("", "")
    status = client.get_system_status()

    return jsonify(status)
