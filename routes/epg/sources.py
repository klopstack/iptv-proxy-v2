"""
EPG Sources management routes - Source CRUD, syncing, coverage stats
"""
import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import Account, ChannelEpgMapping, EpgChannel, EpgSource, SdLineup, SdStation, db
from services.epg.coverage import get_category_epg_coverage, get_epg_coverage_stats

logger = logging.getLogger(__name__)

# Create blueprint
epg_sources_bp = Blueprint("epg_sources", __name__, url_prefix="/api/epg")

PROVIDER_SOURCE_TYPE = "provider"


def _serialize_epg_source(source, *, mapping_count=0):
    """Serialize an EpgSource for JSON responses."""
    return {
        "id": source.id,
        "name": source.name,
        "source_type": source.source_type,
        "account_id": source.account_id,
        "account_name": source.account.name if source.account else None,
        "url": source.url,
        "priority": source.priority,
        "enabled": source.enabled,
        "last_sync": source.last_sync.isoformat() if source.last_sync else None,
        "last_sync_status": source.last_sync_status,
        "last_sync_message": source.last_sync_message,
        "channel_count": source.channel_count,
        "used_mapping_count": mapping_count,
        "xmltv_grabber": source.xmltv_grabber,
        "xmltv_config_name": source.xmltv_config_name,
        "xmltv_days": source.xmltv_days,
        "xmltv_offset": source.xmltv_offset,
        "xmltv_extra_args": source.xmltv_extra_args,
        "deprecated": source.source_type == PROVIDER_SOURCE_TYPE,
    }


# ============================================================================
# API Routes
# ============================================================================


@epg_sources_bp.route("/sources", methods=["GET"])
def get_epg_sources():
    """Get all EPG sources with usage statistics"""
    sources = EpgSource.query.order_by(EpgSource.priority, EpgSource.name).all()

    # Get mapping counts per source (how many channels are using EPG from each source)
    mapping_counts = (
        db.session.query(EpgSource.id, db.func.count(ChannelEpgMapping.id).label("mapping_count"))
        .join(EpgChannel, EpgChannel.source_id == EpgSource.id)
        .join(ChannelEpgMapping, ChannelEpgMapping.epg_channel_id == EpgChannel.id)
        .group_by(EpgSource.id)
        .all()
    )
    mapping_count_map = {row.id: row.mapping_count for row in mapping_counts}

    return jsonify([_serialize_epg_source(s, mapping_count=mapping_count_map.get(s.id, 0)) for s in sources])


@epg_sources_bp.route("/sources", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating EPG source")
def create_epg_source():
    """Create a new EPG source"""
    data = request.json

    if not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    if not data.get("source_type"):
        return jsonify({"error": "Source type is required"}), 400

    valid_types = ["provider", "schedules_direct", "xmltv_url", "xmltv_file", "xmltv_grabber"]
    if data["source_type"] not in valid_types:
        return jsonify({"error": f"Invalid source type. Must be one of: {valid_types}"}), 400

    # Validate account_id for provider type
    if data["source_type"] == "provider":
        if not data.get("account_id"):
            return jsonify({"error": "Account ID is required for provider sources"}), 400
        Account.query.get_or_404(data["account_id"])

    # Validate xmltv_grabber fields
    if data["source_type"] == "xmltv_grabber":
        if not data.get("xmltv_grabber"):
            return jsonify({"error": "XMLTV grabber name is required"}), 400

    source = EpgSource(
        name=data["name"],
        source_type=data["source_type"],
        account_id=data.get("account_id"),
        url=data.get("url"),
        sd_username=data.get("sd_username"),
        sd_password=data.get("sd_password"),
        sd_lineup=data.get("sd_lineup"),
        xmltv_grabber=data.get("xmltv_grabber"),
        xmltv_config_name=data.get("xmltv_config_name"),
        xmltv_days=data.get("xmltv_days", 7),
        xmltv_offset=data.get("xmltv_offset", 0),
        xmltv_extra_args=data.get("xmltv_extra_args"),
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
                "deprecated": source.source_type == PROVIDER_SOURCE_TYPE,
                "message": "EPG source created successfully",
            }
        ),
        201,
    )


@epg_sources_bp.route("/sources/<int:source_id>", methods=["PUT"])
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
    if "xmltv_grabber" in data:
        source.xmltv_grabber = data["xmltv_grabber"]
    if "xmltv_config_name" in data:
        source.xmltv_config_name = data["xmltv_config_name"]
    if "xmltv_days" in data:
        source.xmltv_days = data["xmltv_days"]
    if "xmltv_offset" in data:
        source.xmltv_offset = data["xmltv_offset"]
    if "xmltv_extra_args" in data:
        source.xmltv_extra_args = data["xmltv_extra_args"]

    db.session.commit()

    return jsonify({"success": True, "message": "EPG source updated"})


@epg_sources_bp.route("/sources/<int:source_id>", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error deleting EPG source")
def delete_epg_source(source_id):
    """Delete an EPG source and all its channels"""
    source = EpgSource.query.get_or_404(source_id)

    # Schedules Direct sources have additional tables (sd_lineups/sd_stations).
    # Even though the FK is configured with ON DELETE CASCADE, being explicit here
    # avoids ORM-level relationship quirks and keeps deletes reliable.
    if source.source_type == "schedules_direct":
        lineup_ids = [row[0] for row in db.session.query(SdLineup.id).filter(SdLineup.epg_source_id == source.id).all()]
        if lineup_ids:
            SdStation.query.filter(SdStation.lineup_id.in_(lineup_ids)).delete(synchronize_session=False)
            SdLineup.query.filter(SdLineup.id.in_(lineup_ids)).delete(synchronize_session=False)

    db.session.delete(source)
    db.session.commit()

    return jsonify({"success": True, "message": "EPG source deleted"})


@epg_sources_bp.route("/sources/<int:source_id>/mappings", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting source mappings")
def get_source_mappings(source_id):
    """Get all channel mappings that use EPG data from this source"""
    from models import Category, Channel

    source = EpgSource.query.get_or_404(source_id)

    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    search = request.args.get("search", "")

    query = (
        db.session.query(ChannelEpgMapping, Channel, EpgChannel, Category)
        .join(EpgChannel, ChannelEpgMapping.epg_channel_id == EpgChannel.id)
        .join(Channel, ChannelEpgMapping.channel_id == Channel.id)
        .outerjoin(Category, Channel.category_id == Category.id)
        .filter(EpgChannel.source_id == source_id)
    )

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Channel.name.ilike(search_term),
                Channel.cleaned_name.ilike(search_term),
                EpgChannel.display_name.ilike(search_term),
            )
        )

    total = query.count()
    results = query.order_by(Channel.name).offset(offset).limit(limit).all()

    mappings = []
    for mapping, channel, epg_channel, category in results:
        mappings.append(
            {
                "mapping_id": mapping.id,
                "channel_id": channel.id,
                "channel_name": channel.name,
                "channel_clean_name": channel.cleaned_name,
                "channel_icon": channel.stream_icon,
                "category_id": category.id if category else None,
                "category_name": category.category_name if category else None,
                "account_id": channel.account_id,
                "epg_channel_id": epg_channel.id,
                "epg_channel_xmltv_id": epg_channel.channel_id,
                "epg_channel_name": epg_channel.display_name,
                "epg_channel_icon": epg_channel.icon_url,
                "mapping_type": mapping.mapping_type,
                "confidence": mapping.confidence,
            }
        )

    return jsonify(
        {
            "source_id": source.id,
            "source_name": source.name,
            "total": total,
            "offset": offset,
            "limit": limit,
            "mappings": mappings,
        }
    )


@epg_sources_bp.route("/sources/<int:source_id>/sync", methods=["POST"])
@handle_errors(return_json=True, default_message="Error syncing EPG source")
def sync_epg_source(source_id):
    """Sync EPG data from a source using EpgSyncService"""
    from services.epg_sync_service import EpgSyncService

    source = EpgSource.query.get_or_404(source_id)

    # Use the decomposed service to handle all source types
    success, message, stats = EpgSyncService.sync_source(source)

    # Update source sync status
    EpgSyncService.update_source_sync_status(source, success, message, stats)

    if success:
        return (
            jsonify(
                {
                    "success": True,
                    "message": message,
                    "stats": stats,
                }
            ),
            200,
        )
    else:
        return (
            jsonify(
                {
                    "success": False,
                    "error": message,
                }
            ),
            400,
        )


@epg_sources_bp.route("/coverage", methods=["GET"])
def get_epg_coverage():
    """Get overall EPG coverage statistics"""
    account_id = request.args.get("account_id", type=int)

    if account_id:
        Account.query.get_or_404(account_id)

    stats = get_epg_coverage_stats(account_id)

    return jsonify(stats)


@epg_sources_bp.route("/coverage/categories/<int:account_id>", methods=["GET"])
def get_category_epg_coverage_route(account_id):
    """Get EPG coverage broken down by category for an account"""
    Account.query.get_or_404(account_id)

    coverage = get_category_epg_coverage(account_id)

    return jsonify(
        {
            "account_id": account_id,
            "categories": coverage,
        }
    )
