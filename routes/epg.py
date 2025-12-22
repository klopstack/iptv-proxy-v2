"""
EPG (Electronic Program Guide) management routes
"""
import json
import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import Account, ChannelEpgMapping, EpgChannel, EpgSource, SdLineup, SdStation, db
from services.epg_service import EpgService
from services.iptv_service import IPTVService
from services.schedules_direct import SchedulesDirectClient, SchedulesDirectError, validate_credentials

logger = logging.getLogger(__name__)

# Create blueprint
epg_bp = Blueprint("epg", __name__)


# ============================================================================
# API Routes - EPG Sources
# ============================================================================


@epg_bp.route("/api/epg/sources", methods=["GET"])
def get_epg_sources():
    """Get all EPG sources"""
    sources = EpgSource.query.order_by(EpgSource.priority, EpgSource.name).all()
    return jsonify(
        [
            {
                "id": s.id,
                "name": s.name,
                "source_type": s.source_type,
                "account_id": s.account_id,
                "account_name": s.account.name if s.account else None,
                "url": s.url,
                "priority": s.priority,
                "enabled": s.enabled,
                "last_sync": s.last_sync.isoformat() if s.last_sync else None,
                "last_sync_status": s.last_sync_status,
                "last_sync_message": s.last_sync_message,
                "channel_count": s.channel_count,
            }
            for s in sources
        ]
    )


@epg_bp.route("/api/epg/sources", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating EPG source")
def create_epg_source():
    """Create a new EPG source"""
    data = request.json

    if not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    if not data.get("source_type"):
        return jsonify({"error": "Source type is required"}), 400

    valid_types = ["provider", "schedules_direct", "xmltv_url", "xmltv_file"]
    if data["source_type"] not in valid_types:
        return jsonify({"error": f"Invalid source type. Must be one of: {valid_types}"}), 400

    # Validate account_id for provider type
    if data["source_type"] == "provider":
        if not data.get("account_id"):
            return jsonify({"error": "Account ID is required for provider sources"}), 400
        Account.query.get_or_404(data["account_id"])

    source = EpgSource(
        name=data["name"],
        source_type=data["source_type"],
        account_id=data.get("account_id"),
        url=data.get("url"),
        sd_username=data.get("sd_username"),
        sd_password=data.get("sd_password"),
        sd_lineup=data.get("sd_lineup"),
        priority=data.get("priority", 100),
        enabled=data.get("enabled", True),
    )

    db.session.add(source)
    db.session.commit()

    return (
        jsonify(
            {
                "id": source.id,
                "name": source.name,
                "source_type": source.source_type,
                "message": "EPG source created successfully",
            }
        ),
        201,
    )


@epg_bp.route("/api/epg/sources/<int:source_id>", methods=["PUT"])
@handle_errors(return_json=True, default_message="Error updating EPG source")
def update_epg_source(source_id):
    """Update an EPG source"""
    source = EpgSource.query.get_or_404(source_id)
    data = request.json

    if "name" in data:
        source.name = data["name"]
    if "url" in data:
        source.url = data["url"]
    if "priority" in data:
        source.priority = data["priority"]
    if "enabled" in data:
        source.enabled = data["enabled"]
    if "sd_username" in data:
        source.sd_username = data["sd_username"]
    if "sd_password" in data:
        source.sd_password = data["sd_password"]
    if "sd_lineup" in data:
        source.sd_lineup = data["sd_lineup"]

    db.session.commit()

    return jsonify({"success": True, "message": "EPG source updated"})


@epg_bp.route("/api/epg/sources/<int:source_id>", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error deleting EPG source")
def delete_epg_source(source_id):
    """Delete an EPG source and all its channels"""
    source = EpgSource.query.get_or_404(source_id)

    db.session.delete(source)
    db.session.commit()

    return jsonify({"success": True, "message": "EPG source deleted"})


@epg_bp.route("/api/epg/sources/<int:source_id>/sync", methods=["POST"])
@handle_errors(return_json=True, default_message="Error syncing EPG source")
def sync_epg_source(source_id):
    """Sync EPG data from a source"""
    source = EpgSource.query.get_or_404(source_id)

    if source.source_type == "provider":
        if not source.account:
            return jsonify({"error": "Provider source has no associated account"}), 400

        # Get XMLTV from provider
        account = source.account
        cred = account.get_primary_credential()
        if cred:
            service = IPTVService(account.server, cred.username, cred.password, account.user_agent or "okhttp/3.14.9")
        else:
            service = IPTVService(
                account.server, account.username, account.password, account.user_agent or "okhttp/3.14.9"
            )

        xml_content = service.get_xmltv()
        stats = EpgService.sync_epg_source(source, xml_content)

        return jsonify(
            {
                "success": True,
                "message": f"Synced {stats['channels_added'] + stats['channels_updated']} channels",
                "stats": stats,
            }
        )

    elif source.source_type == "xmltv_url":
        if not source.url:
            return jsonify({"error": "No URL configured for this source"}), 400

        import requests

        response = requests.get(source.url, timeout=120)
        response.raise_for_status()

        stats = EpgService.sync_epg_source(source, response.content)

        return jsonify(
            {
                "success": True,
                "message": f"Synced {stats['channels_added'] + stats['channels_updated']} channels",
                "stats": stats,
            }
        )

    elif source.source_type == "schedules_direct":
        # TODO: Implement Schedules Direct integration
        return jsonify({"error": "Schedules Direct integration not yet implemented"}), 501

    else:
        return jsonify({"error": f"Unknown source type: {source.source_type}"}), 400


# ============================================================================
# API Routes - EPG Channels
# ============================================================================


@epg_bp.route("/api/epg/channels", methods=["GET"])
def get_epg_channels():
    """Get EPG channels with optional filtering

    Query parameters:
    - source_id: Filter by EPG source
    - search: Search by channel ID or display name
    - limit: Max results (default 100)
    - offset: Pagination offset
    """
    source_id = request.args.get("source_id", type=int)
    search = request.args.get("search", "")
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    query = EpgChannel.query

    if source_id:
        query = query.filter_by(source_id=source_id)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                EpgChannel.channel_id.ilike(search_term),
                EpgChannel.display_name.ilike(search_term),
            )
        )

    total = query.count()
    channels = query.order_by(EpgChannel.display_name).offset(offset).limit(limit).all()

    return jsonify(
        {
            "total": total,
            "offset": offset,
            "limit": limit,
            "channels": [
                {
                    "id": c.id,
                    "source_id": c.source_id,
                    "channel_id": c.channel_id,
                    "display_name": c.display_name,
                    "icon_url": c.icon_url,
                    "program_count": c.program_count,
                    "first_program": c.first_program.isoformat() if c.first_program else None,
                    "last_program": c.last_program.isoformat() if c.last_program else None,
                    "mapping_count": len(c.channel_mappings),
                }
                for c in channels
            ],
        }
    )


# ============================================================================
# API Routes - EPG Matching
# ============================================================================


@epg_bp.route("/api/epg/match/<int:account_id>", methods=["POST"])
@handle_errors(return_json=True, default_message="Error matching channels to EPG")
def match_channels_to_epg(account_id):
    """Run automatic EPG matching for an account's channels"""
    Account.query.get_or_404(account_id)

    source_id = request.args.get("source_id", type=int)

    stats = EpgService.match_channels_to_epg(account_id, source_id)

    return jsonify(
        {
            "success": True,
            "message": f"Matched {stats['matched_exact_id'] + stats['matched_exact_name'] + stats['matched_fuzzy']} channels",
            "stats": stats,
        }
    )


@epg_bp.route("/api/epg/mappings", methods=["GET"])
def get_epg_mappings():
    """Get EPG mappings with optional filtering

    Query parameters:
    - account_id: Filter by account
    - unmapped_only: Show only unmapped channels if true
    - limit: Max results
    - offset: Pagination offset
    """
    from models import Channel

    account_id = request.args.get("account_id", type=int)
    unmapped_only = request.args.get("unmapped_only", "false").lower() == "true"
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    if unmapped_only:
        # Get channels without mappings
        mapped_ids = db.session.query(ChannelEpgMapping.channel_id).distinct()

        query = Channel.query.filter(Channel.is_active == True, ~Channel.id.in_(mapped_ids))  # noqa: E712

        if account_id:
            query = query.filter_by(account_id=account_id)

        total = query.count()
        channels = query.order_by(Channel.name).offset(offset).limit(limit).all()

        return jsonify(
            {
                "total": total,
                "offset": offset,
                "limit": limit,
                "unmapped_channels": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "cleaned_name": c.cleaned_name,
                        "epg_channel_id": c.epg_channel_id,
                        "account_id": c.account_id,
                    }
                    for c in channels
                ],
            }
        )
    else:
        # Get mappings
        query = db.session.query(ChannelEpgMapping).join(Channel, ChannelEpgMapping.channel_id == Channel.id)

        if account_id:
            query = query.filter(Channel.account_id == account_id)

        total = query.count()
        mappings = query.offset(offset).limit(limit).all()

        return jsonify(
            {
                "total": total,
                "offset": offset,
                "limit": limit,
                "mappings": [
                    {
                        "id": m.id,
                        "channel_id": m.channel_id,
                        "channel_name": m.channel.name if m.channel else None,
                        "epg_channel_id": m.epg_channel_id,
                        "epg_display_name": m.epg_channel.display_name if m.epg_channel else None,
                        "mapping_type": m.mapping_type,
                        "confidence": m.confidence,
                        "is_override": m.is_override,
                    }
                    for m in mappings
                ],
            }
        )


@epg_bp.route("/api/epg/mappings", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating EPG mapping")
def create_epg_mapping():
    """Create a manual EPG mapping"""
    from models import Channel

    data = request.json

    if not data.get("channel_id"):
        return jsonify({"error": "channel_id is required"}), 400
    if not data.get("epg_channel_id"):
        return jsonify({"error": "epg_channel_id is required"}), 400

    # Validate channel and EPG channel exist
    Channel.query.get_or_404(data["channel_id"])
    EpgChannel.query.get_or_404(data["epg_channel_id"])

    # Check for existing mapping
    existing = ChannelEpgMapping.query.filter_by(
        channel_id=data["channel_id"], epg_channel_id=data["epg_channel_id"]
    ).first()

    if existing:
        return jsonify({"error": "Mapping already exists", "mapping_id": existing.id}), 409

    mapping = ChannelEpgMapping(
        channel_id=data["channel_id"],
        epg_channel_id=data["epg_channel_id"],
        mapping_type="manual",
        confidence=1.0,
        is_override=True,  # Manual mappings are always overrides
    )

    db.session.add(mapping)
    db.session.commit()

    return (
        jsonify(
            {
                "success": True,
                "mapping_id": mapping.id,
                "message": "EPG mapping created",
            }
        ),
        201,
    )


@epg_bp.route("/api/epg/mappings/<int:mapping_id>", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error deleting EPG mapping")
def delete_epg_mapping(mapping_id):
    """Delete an EPG mapping"""
    mapping = ChannelEpgMapping.query.get_or_404(mapping_id)

    db.session.delete(mapping)
    db.session.commit()

    return jsonify({"success": True, "message": "EPG mapping deleted"})


# ============================================================================
# API Routes - EPG Coverage Stats
# ============================================================================


@epg_bp.route("/api/epg/coverage", methods=["GET"])
def get_epg_coverage():
    """Get overall EPG coverage statistics

    Query parameters:
    - account_id: Optional - filter to specific account
    """
    account_id = request.args.get("account_id", type=int)

    if account_id:
        Account.query.get_or_404(account_id)

    stats = EpgService.get_epg_coverage_stats(account_id)

    return jsonify(stats)


@epg_bp.route("/api/epg/coverage/categories/<int:account_id>", methods=["GET"])
def get_category_epg_coverage(account_id):
    """Get EPG coverage broken down by category for an account"""
    Account.query.get_or_404(account_id)

    coverage = EpgService.get_category_epg_coverage(account_id)

    return jsonify(
        {
            "account_id": account_id,
            "categories": coverage,
        }
    )


# ============================================================================
# API Routes - Provider EPG Source Helper
# ============================================================================


@epg_bp.route("/api/accounts/<int:account_id>/epg-source", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating provider EPG source")
def create_account_epg_source(account_id):
    """Create or get an EPG source for a provider account, then sync it"""
    Account.query.get_or_404(account_id)

    source = EpgService.create_provider_epg_source(account_id)

    # Optionally sync immediately
    if request.args.get("sync", "false").lower() == "true":
        account = source.account
        cred = account.get_primary_credential()
        if cred:
            service = IPTVService(account.server, cred.username, cred.password, account.user_agent or "okhttp/3.14.9")
        else:
            service = IPTVService(
                account.server, account.username, account.password, account.user_agent or "okhttp/3.14.9"
            )

        xml_content = service.get_xmltv()
        stats = EpgService.sync_epg_source(source, xml_content)

        return jsonify(
            {
                "success": True,
                "source_id": source.id,
                "message": f"EPG source created and synced ({stats['channels_added'] + stats['channels_updated']} channels)",
                "stats": stats,
            }
        )

    return jsonify(
        {
            "success": True,
            "source_id": source.id,
            "message": "EPG source created",
        }
    )


# ============================================================================
# API Routes - Schedules Direct Integration
# ============================================================================


@epg_bp.route("/api/epg/sd/test", methods=["POST"])
@handle_errors(return_json=True, default_message="Error testing Schedules Direct credentials")
def test_sd_credentials():
    """Test Schedules Direct credentials

    Request body:
        username: SD username
        password: SD password
    """
    data = request.json

    if not data.get("username") or not data.get("password"):
        return jsonify({"error": "Username and password are required"}), 400

    result = validate_credentials(data["username"], data["password"])

    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 401


@epg_bp.route("/api/epg/sd/lineups/search", methods=["GET"])
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


@epg_bp.route("/api/epg/sd/lineups", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching SD lineups")
def get_sd_lineups():
    """Get Schedules Direct lineups for an EPG source

    Query parameters:
        source_id: EPG source ID
    """
    source_id = request.args.get("source_id", type=int)

    if not source_id:
        return jsonify({"success": False, "error": "source_id is required"}), 400

    _source = EpgSource.query.get_or_404(source_id)  # noqa: F841 (validates source exists)

    # Get lineups from database
    lineups = SdLineup.query.filter_by(epg_source_id=source_id).all()

    return jsonify(
        [
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
    )


@epg_bp.route("/api/epg/sd/lineups", methods=["POST"])
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
    data = request.json

    if not data.get("source_id") or not data.get("lineup_id"):
        return jsonify({"error": "source_id and lineup_id are required"}), 400

    source = EpgSource.query.get_or_404(data["source_id"])

    if source.source_type != "schedules_direct":
        return jsonify({"error": "Source is not a Schedules Direct source"}), 400

    # Check if lineup already exists
    existing = SdLineup.query.filter_by(epg_source_id=source.id, lineup_id=data["lineup_id"]).first()

    if existing:
        return jsonify({"error": "Lineup already added to this source"}), 409

    # Create lineup record
    lineup = SdLineup(
        epg_source_id=source.id,
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


@epg_bp.route("/api/epg/sd/lineups/<int:lineup_id>/sync", methods=["POST"])
@handle_errors(return_json=True, default_message="Error syncing SD lineup")
def sync_sd_lineup(lineup_id):
    """Sync channels from a Schedules Direct lineup"""
    lineup = SdLineup.query.get_or_404(lineup_id)
    source = lineup.source

    if not source.sd_username or not source.sd_password:
        return jsonify({"error": "Source does not have SD credentials configured"}), 400

    try:
        result = sync_sd_lineup_impl(source, lineup)
        return jsonify(
            {
                "success": True,
                "message": f"Synced {result['channels_synced']} channels",
                **result,
            }
        )
    except SchedulesDirectError as e:
        return jsonify({"error": str(e), "code": e.code}), 400


def sync_sd_lineup_impl(source: EpgSource, lineup: SdLineup) -> dict:
    """Implementation of SD lineup sync"""
    from datetime import datetime

    client = SchedulesDirectClient(source.sd_username, source.sd_password)
    client.authenticate()

    # Get channels from SD
    channels = client.get_lineup_channels(lineup.lineup_id)

    channels_synced = 0
    channels_updated = 0

    for ch in channels:
        # Find or create station record
        station = SdStation.query.filter_by(lineup_id=lineup.id, station_id=ch["stationID"]).first()

        logo_url = ch.get("logo", {}).get("url") if ch.get("logo") else None
        broadcast_lang = json.dumps(ch.get("broadcastLanguage", []))

        if station:
            # Update existing
            station.channel_number = ch.get("channel")
            station.callsign = ch.get("callsign")
            station.name = ch.get("name")
            station.affiliate = ch.get("affiliate")
            station.broadcast_language = broadcast_lang
            station.logo_url = logo_url
            channels_updated += 1
        else:
            # Create new
            station = SdStation(
                lineup_id=lineup.id,
                station_id=ch["stationID"],
                channel_number=ch.get("channel"),
                callsign=ch.get("callsign"),
                name=ch.get("name"),
                affiliate=ch.get("affiliate"),
                broadcast_language=broadcast_lang,
                logo_url=logo_url,
            )
            db.session.add(station)
            channels_synced += 1

    # Update lineup stats
    lineup.channel_count = len(channels)
    lineup.last_sync = datetime.utcnow()

    db.session.commit()

    return {
        "channels_synced": channels_synced,
        "channels_updated": channels_updated,
        "total_channels": len(channels),
    }


@epg_bp.route("/api/epg/sd/lineups/<int:lineup_id>", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error removing SD lineup")
def remove_sd_lineup(lineup_id):
    """Remove a Schedules Direct lineup"""
    lineup = SdLineup.query.get_or_404(lineup_id)

    # Delete associated stations first (cascade should handle this, but being explicit)
    SdStation.query.filter_by(lineup_id=lineup_id).delete()

    db.session.delete(lineup)
    db.session.commit()

    return jsonify({"success": True, "message": "Lineup removed successfully"})


@epg_bp.route("/api/epg/sd/lineups/<int:lineup_id>/stations", methods=["GET"])
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


@epg_bp.route("/api/epg/sd/match/<int:account_id>", methods=["POST"])
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


@epg_bp.route("/api/epg/sd/status", methods=["GET"])
@handle_errors(return_json=True, default_message="Error checking SD status")
def get_sd_status():
    """Get Schedules Direct system status (no auth required)"""
    from services.schedules_direct import SchedulesDirectClient

    client = SchedulesDirectClient("", "")
    status = client.get_system_status()

    return jsonify(status)
