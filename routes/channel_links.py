"""
Channel link management routes

Handles API endpoints for managing channel links (duplicate/variant relationships).
"""
import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import Channel, ChannelLink, db

logger = logging.getLogger(__name__)

# Create blueprint
channel_links_bp = Blueprint("channel_links", __name__)


def channel_link_to_dict(link):
    """Convert a ChannelLink to a dictionary with related channel info."""
    return {
        "id": link.id,
        "channel_id": link.channel_id,
        "channel_name": link.channel.name if link.channel else None,
        "channel_account_id": link.channel.account_id if link.channel else None,
        "source_channel_id": link.source_channel_id,
        "source_channel_name": link.source_channel.name if link.source_channel else None,
        "source_channel_account_id": link.source_channel.account_id if link.source_channel else None,
        "time_offset_hours": link.time_offset_hours,
        "link_type": link.link_type,
        "auto_detected": link.auto_detected,
        "created_at": link.created_at.isoformat() if link.created_at else None,
        "updated_at": link.updated_at.isoformat() if link.updated_at else None,
    }


# ============================================================================
# API Routes - Channel Links CRUD
# ============================================================================


@channel_links_bp.route("/api/channel-links", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching channel links")
def get_channel_links():
    """
    Get all channel links with optional filtering.

    Query params:
        - account_id: Filter by account (either channel's or source's account)
        - channel_id: Filter by specific channel
        - link_type: Filter by link type (time_shifted, simulcast, etc.)
        - auto_detected: Filter by auto-detected status (true/false)
    """
    query = ChannelLink.query

    # Filter by account (channels belonging to this account)
    account_id = request.args.get("account_id", type=int)
    if account_id:
        query = query.join(Channel, ChannelLink.channel_id == Channel.id).filter(Channel.account_id == account_id)

    # Filter by specific channel
    channel_id = request.args.get("channel_id", type=int)
    if channel_id:
        query = query.filter(ChannelLink.channel_id == channel_id)

    # Filter by link type
    link_type = request.args.get("link_type")
    if link_type:
        query = query.filter(ChannelLink.link_type == link_type)

    # Filter by auto-detected status
    auto_detected = request.args.get("auto_detected")
    if auto_detected is not None:
        auto_detected_bool = auto_detected.lower() in ("true", "1", "yes")
        query = query.filter(ChannelLink.auto_detected == auto_detected_bool)

    links = query.all()
    return jsonify([channel_link_to_dict(link) for link in links])


@channel_links_bp.route("/api/channel-links/<int:link_id>", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching channel link")
def get_channel_link(link_id):
    """Get a specific channel link by ID."""
    link = db.session.get(ChannelLink, link_id)
    if not link:
        return jsonify({"error": "Channel link not found"}), 404
    return jsonify(channel_link_to_dict(link))


@channel_links_bp.route("/api/channel-links", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating channel link")
def create_channel_link():
    """
    Create a new channel link.

    Request body:
        - channel_id: ID of the channel that needs EPG from source
        - source_channel_id: ID of the channel to use as EPG source
        - time_offset_hours: Time offset in hours (default: 0)
        - link_type: Type of link (default: "time_shifted")
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body is required"}), 400

    channel_id = data.get("channel_id")
    source_channel_id = data.get("source_channel_id")

    if not channel_id or not source_channel_id:
        return jsonify({"error": "channel_id and source_channel_id are required"}), 400

    # Validate channels exist
    channel = db.session.get(Channel, channel_id)
    source_channel = db.session.get(Channel, source_channel_id)

    if not channel:
        return jsonify({"error": f"Channel {channel_id} not found"}), 404
    if not source_channel:
        return jsonify({"error": f"Source channel {source_channel_id} not found"}), 404

    # Prevent self-linking
    if channel_id == source_channel_id:
        return jsonify({"error": "Cannot link a channel to itself"}), 400

    # Check for existing link
    existing = ChannelLink.query.filter_by(
        channel_id=channel_id,
        source_channel_id=source_channel_id,
    ).first()
    if existing:
        return jsonify({"error": "This channel link already exists", "id": existing.id}), 409

    link = ChannelLink(
        channel_id=channel_id,
        source_channel_id=source_channel_id,
        time_offset_hours=data.get("time_offset_hours", 0),
        link_type=data.get("link_type", "time_shifted"),
        auto_detected=False,  # Manual creation
    )

    db.session.add(link)
    db.session.commit()

    logger.info(f"Created channel link: {channel.name} -> {source_channel.name}")
    return jsonify(channel_link_to_dict(link)), 201


@channel_links_bp.route("/api/channel-links/<int:link_id>", methods=["PUT"])
@handle_errors(return_json=True, default_message="Error updating channel link")
def update_channel_link(link_id):
    """
    Update a channel link.

    Request body (all optional):
        - time_offset_hours: New time offset
        - link_type: New link type
    """
    link = db.session.get(ChannelLink, link_id)
    if not link:
        return jsonify({"error": "Channel link not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    # Update allowed fields
    if "time_offset_hours" in data:
        link.time_offset_hours = data["time_offset_hours"]
    if "link_type" in data:
        link.link_type = data["link_type"]

    db.session.commit()

    logger.info(f"Updated channel link {link_id}")
    return jsonify(channel_link_to_dict(link))


@channel_links_bp.route("/api/channel-links/<int:link_id>", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error deleting channel link")
def delete_channel_link(link_id):
    """Delete a channel link."""
    link = db.session.get(ChannelLink, link_id)
    if not link:
        return jsonify({"error": "Channel link not found"}), 404

    db.session.delete(link)
    db.session.commit()

    logger.info(f"Deleted channel link {link_id}")
    return jsonify({"message": "Channel link deleted successfully"})


# ============================================================================
# Bulk Operations
# ============================================================================


@channel_links_bp.route("/api/channel-links/bulk", methods=["POST"])
@handle_errors(return_json=True, default_message="Error bulk creating channel links")
def bulk_create_channel_links():
    """
    Create multiple channel links at once.

    Request body:
        - links: Array of link objects, each with:
            - channel_id
            - source_channel_id
            - time_offset_hours (optional)
            - link_type (optional)
    """
    data = request.get_json()
    if not data or "links" not in data:
        return jsonify({"error": "links array is required"}), 400

    created = []
    errors = []

    for i, link_data in enumerate(data["links"]):
        channel_id = link_data.get("channel_id")
        source_channel_id = link_data.get("source_channel_id")

        if not channel_id or not source_channel_id:
            errors.append({"index": i, "error": "channel_id and source_channel_id required"})
            continue

        if channel_id == source_channel_id:
            errors.append({"index": i, "error": "Cannot link channel to itself"})
            continue

        # Check channels exist
        channel = db.session.get(Channel, channel_id)
        source = db.session.get(Channel, source_channel_id)
        if not channel or not source:
            errors.append({"index": i, "error": "Channel or source not found"})
            continue

        # Check for existing
        existing = ChannelLink.query.filter_by(
            channel_id=channel_id,
            source_channel_id=source_channel_id,
        ).first()
        if existing:
            errors.append({"index": i, "error": "Link already exists", "id": existing.id})
            continue

        link = ChannelLink(
            channel_id=channel_id,
            source_channel_id=source_channel_id,
            time_offset_hours=link_data.get("time_offset_hours", 0),
            link_type=link_data.get("link_type", "time_shifted"),
            auto_detected=False,
        )
        db.session.add(link)
        created.append(link)

    if created:
        db.session.commit()

    return jsonify(
        {
            "created": len(created),
            "errors": errors,
            "links": [channel_link_to_dict(link) for link in created],
        }
    )


@channel_links_bp.route("/api/channel-links/auto-detected", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error deleting auto-detected links")
def delete_auto_detected_links():
    """Delete all auto-detected channel links (to re-run detection)."""
    count = ChannelLink.query.filter_by(auto_detected=True).delete()
    db.session.commit()

    logger.info(f"Deleted {count} auto-detected channel links")
    return jsonify({"deleted": count})


@channel_links_bp.route("/api/channel-links/detect", methods=["POST"])
@handle_errors(return_json=True, default_message="Error detecting channel links")
def detect_channel_links():
    """
    Auto-detect channel links based on tags and cleaned names.

    Detects east/west channel pairs using tags (EAST, WEST, E, W, etc.)
    and channels with the same cleaned_name. West channels are linked
    to their east counterpart with a -3 hour time offset.

    Query params:
        - account_id: Optional account ID to limit detection to
        - clear_existing: If true, delete existing auto-detected links first

    Returns:
        Detection statistics including links created and skipped
    """
    from services.sync_service import ChannelSyncService

    account_id = request.args.get("account_id", type=int)
    clear_existing = request.args.get("clear_existing", "").lower() in ("true", "1", "yes")

    if clear_existing:
        # Delete existing auto-detected links
        query = ChannelLink.query.filter_by(auto_detected=True)
        if account_id:
            query = query.join(Channel, ChannelLink.channel_id == Channel.id).filter(Channel.account_id == account_id)
        deleted = query.delete(synchronize_session="fetch")
        db.session.commit()
        logger.info(f"Cleared {deleted} existing auto-detected links before detection")

    stats = ChannelSyncService.detect_channel_links(account_id)
    return jsonify(stats)


# ============================================================================
# Query Helpers
# ============================================================================


@channel_links_bp.route("/api/channels/<int:channel_id>/links", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching links for channel")
def get_links_for_channel(channel_id):
    """
    Get all links where this channel is either the target or source.

    Returns:
        - as_target: Links where this channel receives EPG from another
        - as_source: Links where this channel provides EPG to others
    """
    channel = db.session.get(Channel, channel_id)
    if not channel:
        return jsonify({"error": "Channel not found"}), 404

    as_target = ChannelLink.query.filter_by(channel_id=channel_id).all()
    as_source = ChannelLink.query.filter_by(source_channel_id=channel_id).all()

    return jsonify(
        {
            "channel": {"id": channel.id, "name": channel.name},
            "as_target": [channel_link_to_dict(link) for link in as_target],
            "as_source": [channel_link_to_dict(link) for link in as_source],
        }
    )
