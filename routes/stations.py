"""
Station Database API Routes - FCC facility data and channel enrichment
"""
import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors

logger = logging.getLogger(__name__)

# Create blueprint
stations_bp = Blueprint("stations", __name__)


# ============================================================================
# FCC Facility Data Routes
# ============================================================================


@stations_bp.route("/api/fcc/facilities/sync", methods=["POST"])
@handle_errors(return_json=True, default_message="Error syncing FCC facility data")
def sync_fcc_facilities():
    """Download and sync FCC TV facility data.

    This downloads the latest facility.dat from the FCC LMS database
    and syncs TV station records to the local database.

    Returns:
        JSON with sync statistics
    """
    from services.fcc_facility_service import FccFacilityService

    result = FccFacilityService.full_sync()

    if result["success"]:
        return jsonify(result)
    else:
        return jsonify({"error": result["message"]}), 500


@stations_bp.route("/api/fcc/facilities/stats", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting FCC facility stats")
def get_fcc_stats():
    """Get statistics about FCC facility data.

    Returns:
        JSON with counts and data freshness info
    """
    from services.fcc_facility_service import FccFacilityService

    stats = FccFacilityService.get_stats()
    return jsonify(stats)


@stations_bp.route("/api/fcc/facilities/lookup/callsign/<string:callsign>", methods=["GET"])
@handle_errors(return_json=True, default_message="Error looking up callsign")
def lookup_fcc_callsign(callsign):
    """Look up FCC facility by callsign.

    Args:
        callsign: Station callsign (e.g., "KABC-TV", "WNBC")

    Returns:
        JSON with facility info or 404 if not found
    """
    from services.fcc_facility_service import FccFacilityService

    facility = FccFacilityService.lookup_by_callsign(callsign)

    if facility:
        return jsonify(
            {
                "callsign": facility.callsign,
                "city": facility.community_city,
                "state": facility.community_state,
                "network": facility.network_affiliation,
                "dma": facility.nielsen_dma,
                "channel": facility.channel,
                "virtual_channel": facility.tv_virtual_channel,
                "service_code": facility.service_code,
                "active": facility.active,
            }
        )
    else:
        return jsonify({"error": f"No facility found for callsign: {callsign}"}), 404


@stations_bp.route("/api/fcc/facilities/lookup/city", methods=["GET"])
@handle_errors(return_json=True, default_message="Error looking up city")
def lookup_fcc_city():
    """Look up FCC facilities by city and state.

    Query params:
        city: City name (required)
        state: State code (required)
        network: Optional network filter

    Returns:
        JSON with list of facilities in that city
    """
    from services.fcc_facility_service import FccFacilityService

    city = request.args.get("city")
    state = request.args.get("state")
    network = request.args.get("network")

    if not city or not state:
        return jsonify({"error": "city and state parameters are required"}), 400

    facilities = FccFacilityService.lookup_by_city_state(city, state, network)

    return jsonify(
        {
            "city": city.upper(),
            "state": state.upper(),
            "count": len(facilities),
            "facilities": [
                {
                    "callsign": f.callsign,
                    "network": f.network_affiliation,
                    "channel": f.channel,
                    "virtual_channel": f.tv_virtual_channel,
                    "service_code": f.service_code,
                }
                for f in facilities
            ],
        }
    )


@stations_bp.route("/api/fcc/facilities/lookup/dma", methods=["GET"])
@handle_errors(return_json=True, default_message="Error looking up DMA")
def lookup_fcc_dma():
    """Look up FCC facilities by DMA (market) name.

    Query params:
        dma: DMA market name (e.g., "New York", "Los Angeles")

    Returns:
        JSON with list of facilities in that DMA
    """
    from services.fcc_facility_service import FccFacilityService

    dma = request.args.get("dma")

    if not dma:
        return jsonify({"error": "dma parameter is required"}), 400

    facilities = FccFacilityService.lookup_by_dma(dma)

    return jsonify(
        {
            "dma": dma,
            "count": len(facilities),
            "facilities": [
                {
                    "callsign": f.callsign,
                    "city": f.community_city,
                    "state": f.community_state,
                    "network": f.network_affiliation,
                    "channel": f.channel,
                }
                for f in facilities
            ],
        }
    )


@stations_bp.route("/api/fcc/facilities/dmas", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting DMA list")
def get_dma_list():
    """Get list of all DMA (market) names.

    Returns:
        JSON with list of unique DMA names and counts
    """
    from services.fcc_facility_service import FccFacilityService

    dmas = FccFacilityService.get_dma_list()
    return jsonify({"count": len(dmas), "dmas": dmas})


# ============================================================================
# Channel Enrichment Routes
# ============================================================================


@stations_bp.route("/api/fcc/enrichment/preview/<int:account_id>", methods=["GET"])
@handle_errors(return_json=True, default_message="Error previewing channel enrichment")
def preview_channel_enrichment(account_id):
    """Preview potential FCC-based enrichment for channels.

    Analyzes channels for an account and shows what callsign/tag
    enrichment would be applied based on FCC data.

    Args:
        account_id: Account ID to preview enrichment for

    Query params:
        limit: Number of results per page (default: 50)
        offset: Starting offset for pagination (default: 0)

    Returns:
        JSON with matched channels and their potential enrichments
    """
    from models import Account
    from services.fcc_facility_service import FccFacilityService

    account = Account.query.get_or_404(account_id)

    # Get pagination params
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    # Get all matches (cached in service)
    all_matches = FccFacilityService.preview_channel_enrichment(account_id)
    total = len(all_matches)

    # Apply pagination
    matches = all_matches[offset : offset + limit]
    has_more = (offset + limit) < total

    return jsonify(
        {
            "account_id": account_id,
            "account_name": account.name,
            "total_matches": total,
            "matches": matches,
            "showing": len(matches),
            "offset": offset,
            "has_more": has_more,
        }
    )


@stations_bp.route("/api/fcc/enrichment/apply/<int:account_id>", methods=["POST"])
@handle_errors(return_json=True, default_message="Error applying channel enrichment")
def apply_channel_enrichment(account_id):
    """Apply FCC-based enrichment to channels.

    Creates tags for channels based on FCC data matches:
    - Network affiliation tags (e.g., "ABC", "CBS", "NBC")
    - DMA/Market tags (e.g., "New York", "Los Angeles")
    - State tags (e.g., "CA", "NY")

    Args:
        account_id: Account ID to apply enrichment to

    Query params:
        create_network_tags: bool - Create network affiliation tags (default: true)
        create_dma_tags: bool - Create DMA/market tags (default: true)
        create_state_tags: bool - Create state tags (default: false)

    Returns:
        JSON with enrichment results
    """
    from models import Account
    from services.fcc_facility_service import FccFacilityService

    Account.query.get_or_404(account_id)

    # Get options from request
    data = request.get_json() or {}
    options = {
        "create_network_tags": data.get("create_network_tags", True),
        "create_dma_tags": data.get("create_dma_tags", True),
        "create_state_tags": data.get("create_state_tags", False),
    }

    result = FccFacilityService.apply_channel_enrichment(account_id, options)

    return jsonify(result)


@stations_bp.route("/api/fcc/networks", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting network list")
def get_network_list():
    """Get list of all network affiliations.

    Returns:
        JSON with list of unique network names and counts
    """
    from services.fcc_facility_service import FccFacilityService

    networks = FccFacilityService.get_network_list()
    return jsonify({"count": len(networks), "networks": networks})


@stations_bp.route("/api/fcc/channels/by-callsign/<string:callsign>", methods=["GET"])
@handle_errors(return_json=True, default_message="Error searching channels by callsign")
def get_channels_by_callsign(callsign):
    """Find channels that match a given callsign.

    Searches across all accounts for channels containing the callsign
    in their name (typically in parentheses like "(KABC)").

    Args:
        callsign: Station callsign to search for (e.g., "KABC", "WNBC")

    Returns:
        JSON with matching channels grouped by account
    """
    from models import Account, Channel

    callsign = callsign.upper().strip()

    # Search patterns - look for callsign in parentheses or as word
    # e.g., "(KABC)", "KABC-TV", "KABC "
    search_patterns = [
        f"%({callsign})%",  # (KABC)
        f"%({callsign}-%",  # (KABC-TV)
        f"% {callsign} %",  # space-delimited
        f"% {callsign}-%",  # KABC-TV
    ]

    # Query channels matching any pattern
    from sqlalchemy import or_

    conditions = [Channel.name.ilike(p) for p in search_patterns]
    channels = (
        Channel.query.filter(Channel.is_active == True, or_(*conditions))  # noqa: E712
        .order_by(Channel.account_id, Channel.name)
        .limit(100)
        .all()
    )

    # Group by account
    accounts_dict = {}
    for channel in channels:
        if channel.account_id not in accounts_dict:
            account = Account.query.get(channel.account_id)
            accounts_dict[channel.account_id] = {
                "account_id": channel.account_id,
                "account_name": account.name if account else "Unknown",
                "server": account.server if account else "",
                "channels": [],
            }
        accounts_dict[channel.account_id]["channels"].append(
            {
                "id": channel.id,
                "stream_id": channel.stream_id,
                "name": channel.name,
                "cleaned_name": channel.cleaned_name,
            }
        )

    return jsonify(
        {
            "callsign": callsign,
            "total_channels": len(channels),
            "accounts": list(accounts_dict.values()),
        }
    )
