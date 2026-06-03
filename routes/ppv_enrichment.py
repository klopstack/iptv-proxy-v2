"""
API endpoints for PPV event enrichment management

Uses the calendar-based enrichment service which:
1. Scrapes TheSportsDB calendar (no rate limits) for event matching
2. Fetches detailed event info via API (rate limited) in background thread
"""

import logging

from flask import Blueprint, current_app, jsonify, request
from flask_cors import cross_origin

from error_handling import handle_errors
from services.ppv.enrichment import get_calendar_enrichment_service

logger = logging.getLogger(__name__)

ppv_enrichment_bp = Blueprint("ppv_enrichment", __name__, url_prefix="/api/ppv-enrichment")


@ppv_enrichment_bp.route("/status", methods=["GET"])
@cross_origin()
@handle_errors(return_json=True, default_message="Error getting enrichment status")
def get_enrichment_status():
    """
    Get PPV enrichment service status and statistics.

    Returns enrichment progress, calendar cache stats, and detail thread status.

    Response:
    {
        "detail_queue_size": 12,
        "detail_thread_running": true,
        "calendar_cache_stats": {
            "size": 7,
            "hit_rate": 0.85
        },
        "cumulative_stats": {
            "calendar_processed": "1268",
            "calendar_matched": "1203",
            "details_fetched": "456"
        },
        "session_stats": {
            "channels_processed": 100,
            "events_matched": 85,
            "details_fetched": 20
        }
    }
    """
    from models import db
    from services.ppv.orchestrator import get_ppv_orchestrator

    try:
        service = get_calendar_enrichment_service(current_app._get_current_object())
        status = service.get_status()

        try:
            orchestrator = get_ppv_orchestrator(current_app._get_current_object())
            queue_stats = orchestrator.get_queue_stats()
            queued_count = queue_stats["queued_count"]
            batch_size = status.get("batch_size", 100)
            status["queued_count"] = queued_count
            status["hot_queued_count"] = queue_stats["hot_queued_count"]
            status["estimated_hours_at_current_rate"] = max(0, queued_count // batch_size) if batch_size > 0 else 0
        except Exception as exc:
            logger.warning("Could not load PPV enrichment queue stats: %s", exc, exc_info=True)
            status["queue_stats_error"] = True

        return jsonify(status), 200
    finally:
        db.session.remove()


@ppv_enrichment_bp.route("/process", methods=["POST"])
@cross_origin()
@handle_errors(return_json=True, default_message="Error processing enrichment")
def process_enrichment():
    """
    Manually trigger PPV enrichment processing.

    Empty POST is accepted (no JSON body required).

    Optional JSON body:
    {
        "account_id": 1,              # Optional: only process channels from this account
        "fetch_details": true,        # Whether to queue detail fetches (default: true)
        "include_no_match": false     # If true, re-queue no_match channels then run batch drain
    }

    By default runs the queued-channel drain loop (same as the scheduler job).
    Returns processing statistics.
    """
    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")
    fetch_details = data.get("fetch_details", True)
    include_no_match = data.get("include_no_match", False)

    from services.ppv.orchestrator import get_ppv_orchestrator

    app_obj = current_app._get_current_object()
    orchestrator = get_ppv_orchestrator(app_obj)

    if include_no_match:
        requeued = orchestrator.requeue_no_match_channels(account_id=account_id)
        if requeued == 0:
            return jsonify({"message": "No PPV channels need enrichment", "processed": 0}), 200
        logger.info(
            "Re-queued %s no_match PPV channels for enrichment%s",
            requeued,
            f" (account {account_id})" if account_id else "",
        )

    if account_id:
        total_stats: dict = {
            "accounts_processed": 0,
            "channels_processed": 0,
            "channels_matched": 0,
            "channels_no_match": 0,
            "errors": 0,
            "batches_run": 0,
        }
        from services.jobs.ppv_enrichment import _merge_enrichment_stats

        while True:
            stats = orchestrator.enrich_pending_channels(account_id=account_id)
            if stats.get("skipped"):
                if total_stats["batches_run"] == 0:
                    return jsonify(stats), 200
                return jsonify(total_stats), 200
            total_stats["batches_run"] += 1
            _merge_enrichment_stats(total_stats, stats)
            if stats.get("channels_processed", 0) == 0:
                break
            if orchestrator.get_queue_stats().get("queued_count", 0) == 0:
                break
        if fetch_details and total_stats["channels_matched"] > 0:
            get_calendar_enrichment_service(app_obj).start_detail_fetcher()
        if total_stats["channels_no_match"] > 0:
            orchestrator.run_enhanced_fallback()
        if include_no_match:
            total_stats["no_match_requeued"] = requeued
        return jsonify(total_stats), 200

    from services.jobs.ppv_enrichment import run_ppv_enrichment

    results = run_ppv_enrichment(app_obj)
    if not fetch_details:
        results["detail_fetch_skipped"] = True
    if include_no_match:
        results["no_match_requeued"] = requeued
    return jsonify(results), 200


@ppv_enrichment_bp.route("/queue/channels", methods=["POST"])
@cross_origin()
@handle_errors(return_json=True, default_message="Error queuing channels for enrichment")
def queue_channels_for_enrichment():
    """
    Queue specific PPV channels for enrichment.

    JSON body:
    {
        "channel_ids": [1, 2, 3],  # IDs of channels to queue
        "account_id": 1           # Optional: only queue channels from this account
    }

    Returns queuing statistics.
    """
    from models import Channel, db
    from services.ppv.persistence import clear_event_links_for_channels

    data = request.get_json(silent=True) or {}
    channel_ids = data.get("channel_ids", [])
    account_id = data.get("account_id")

    if not channel_ids:
        return jsonify({"error": "channel_ids required"}), 400

    query = Channel.query.filter(Channel.id.in_(channel_ids))
    if account_id:
        query = query.filter_by(account_id=account_id)

    channels = query.all()

    if not channels:
        return (
            jsonify({"error": "No channels found with provided IDs"}),
            404,
        )

    ppv_channel_ids = [ch.id for ch in channels if ch.is_ppv]
    links_cleared = clear_event_links_for_channels(ppv_channel_ids)

    queued = 0
    for channel in channels:
        if channel.is_ppv:
            channel.ppv_enrichment_status = "queued"
            channel.ppv_enrichment_attempts = 0
            channel.ppv_enrichment_error = None
            queued += 1

    db.session.commit()

    logger.info(f"Queued {queued} channels for enrichment" f"{f' from account {account_id}' if account_id else ''}")

    return jsonify({"queued": queued, "total_requested": len(channel_ids), "links_cleared": links_cleared}), 200


@ppv_enrichment_bp.route("/queue/all-ppv", methods=["POST"])
@cross_origin()
@handle_errors(return_json=True, default_message="Error queuing PPV channels")
def queue_all_ppv_channels():
    """
    Queue all PPV channels for enrichment (reset their status to 'queued').

    Optional JSON body:
    {
        "account_id": 1  # Optional: only queue channels from this account
    }

    Returns queuing statistics.
    """
    from models import Channel, db
    from services.ppv.persistence import clear_event_links_for_channels

    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")

    query = Channel.query.filter_by(is_ppv=True)
    if account_id:
        query = query.filter_by(account_id=account_id)

    channels = query.all()

    if not channels:
        return (
            jsonify({"error": "No PPV channels found"}),
            404,
        )

    ppv_channel_ids = [ch.id for ch in channels]
    links_cleared = clear_event_links_for_channels(ppv_channel_ids)

    queued = 0
    skipped_already_matched = 0

    for channel in channels:
        if channel.ppv_enrichment_status == "matched":
            skipped_already_matched += 1
        channel.ppv_enrichment_status = "queued"
        channel.ppv_enrichment_attempts = 0
        channel.ppv_enrichment_error = None
        queued += 1

    db.session.commit()

    logger.info(f"Queued {queued} PPV channels for enrichment" f"{f' from account {account_id}' if account_id else ''}")

    return (
        jsonify(
            {
                "queued": queued,
                "skipped_already_matched": skipped_already_matched,
                "links_cleared": links_cleared,
            }
        ),
        200,
    )


@ppv_enrichment_bp.route("/channels", methods=["GET"])
@cross_origin()
@handle_errors(return_json=True, default_message="Error listing PPV enrichment channels")
def get_enrichment_channels():
    """
    List PPV channels with enrichment status and linked event summaries.

    Query Parameters:
        account_id (optional): Filter to specific account
        status (optional): Comma-separated enrichment statuses
        search (optional): Search channel names
        page (optional): Page number (default: 1)
        per_page (optional): Results per page (default: 50)
    """
    from services.ppv.preview import list_ppv_enrichment_channels

    account_id = request.args.get("account_id", type=int)
    status = request.args.get("status")
    search = request.args.get("search")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    result = list_ppv_enrichment_channels(
        account_id=account_id,
        status=status,
        search=search,
        page=page,
        per_page=per_page,
    )
    return jsonify(result), 200


@ppv_enrichment_bp.route("/settings", methods=["GET"])
@cross_origin()
@handle_errors(return_json=True, default_message="Error getting enrichment settings")
def get_enrichment_settings():
    """
    Get current PPV enrichment service settings.

    Returns configuration details including rate limits for detail fetching.
    """
    from services.ppv.enrichment import DETAIL_FETCH_BATCH_SIZE
    from services.thesportsdb_service import get_thesportsdb_api_requests_per_minute

    rpm = get_thesportsdb_api_requests_per_minute()
    return (
        jsonify(
            {
                "detail_fetch_batch_size": DETAIL_FETCH_BATCH_SIZE,
                "api_requests_per_minute": rpm,
                "calendar_scraping": {
                    "rate_limited": False,
                    "cache_ttl_seconds": 3600,
                },
                "detail_fetching": {
                    "rate_limited": True,
                    "requests_per_minute": rpm,
                },
            }
        ),
        200,
    )


@ppv_enrichment_bp.route("/detail-thread/start", methods=["POST"])
@cross_origin()
@handle_errors(return_json=True, default_message="Error starting detail fetcher thread")
def start_detail_thread():
    """
    Start the background detail fetching thread.

    The detail thread fetches full event information (descriptions, logos, etc.)
    from the API for events that were matched via calendar scraping.
    """
    service = get_calendar_enrichment_service(current_app._get_current_object())
    service.start_detail_fetcher()

    return jsonify({"message": "Detail fetcher thread started", "running": True}), 200


@ppv_enrichment_bp.route("/detail-thread/stop", methods=["POST"])
@cross_origin()
@handle_errors(return_json=True, default_message="Error stopping detail fetcher thread")
def stop_detail_thread():
    """
    Stop the background detail fetching thread.
    """
    service = get_calendar_enrichment_service(current_app._get_current_object())
    service.stop_detail_fetcher()

    return jsonify({"message": "Detail fetcher thread stopped", "running": False}), 200


@ppv_enrichment_bp.route("/coverage", methods=["GET"])
@cross_origin()
@handle_errors(return_json=True, default_message="Failed to generate coverage report")
def get_coverage_report():
    """
    Return a matrix showing which sports/leagues have which context data types covered.

    Useful for identifying gaps in provider coverage and debugging enrichment.
    """
    from services.ppv.context.registry import get_registry

    report = get_registry().coverage_report()
    return jsonify(report), 200


@ppv_enrichment_bp.route("/provider-settings", methods=["GET"])
@cross_origin()
@handle_errors(return_json=True, default_message="Internal server error fetching provider settings")
def get_provider_settings():
    """
    Return settings fields and current values for all context data providers
    plus the LLM enrichment virtual provider.

    Response shape::

        {
            "providers": [
                {
                    "name": "football_data",
                    "fields": [
                        {
                            "key": "api_key",
                            "label": "API Key",
                            "type": "password",
                            "description": "...",
                            "required": true,
                            "current_value": "ab12****"
                        }
                    ]
                },
                ...
            ]
        }

    Password fields are masked in the response (first 4 chars + ``****``).
    """
    from models.provider_settings import ProviderSettings
    from services.ppv.context.llm_client import LLMEnrichmentSettings
    from services.ppv.context.registry import get_registry

    registry = get_registry()
    all_providers = list(registry.all_providers()) + [LLMEnrichmentSettings()]

    result = []
    for provider in all_providers:
        fields = provider.settings_fields()
        if not fields:
            continue

        stored = ProviderSettings.get_all_for(provider.name)
        enriched_fields = []
        for f in fields:
            key = f["key"]
            raw = stored.get(key, f.get("default", ""))
            display = _mask_value(f.get("type", "text"), raw)
            enriched_fields.append({**f, "current_value": display})

        result.append({"name": provider.name, "fields": enriched_fields})

    return jsonify({"providers": result}), 200


@ppv_enrichment_bp.route("/provider-settings/<provider_name>/<key>", methods=["PUT"])
@cross_origin()
@handle_errors(return_json=True, default_message="Internal server error saving provider setting")
def set_provider_setting(provider_name, key):
    """
    Store a single setting value for a context data provider.

    URL parameters:
        provider_name  - Provider name, e.g. ``football_data`` or ``llm_enrichment``.
        key            - Setting key as declared in the provider's ``settings_fields()``.

    JSON body::

        {"value": "my-api-key"}

    Returns the stored key/provider on success.
    """
    from models.provider_settings import ProviderSettings
    from services.ppv.context.llm_client import LLMEnrichmentSettings
    from services.ppv.context.registry import get_registry

    registry = get_registry()
    all_providers = {p.name: p for p in registry.all_providers()}
    all_providers[LLMEnrichmentSettings.name] = LLMEnrichmentSettings()

    provider = all_providers.get(provider_name)
    if provider is None:
        return jsonify({"error": f"Unknown provider: {provider_name!r}"}), 404

    valid_keys = {f["key"] for f in provider.settings_fields()}
    if key not in valid_keys:
        return jsonify({"error": f"Unknown setting key {key!r} for provider {provider_name!r}"}), 400

    data = request.get_json()
    if not data or "value" not in data:
        return jsonify({"error": "JSON body with 'value' key is required"}), 400

    value = str(data["value"])
    description = next(
        (f.get("description", "") for f in provider.settings_fields() if f["key"] == key),
        "",
    )
    ProviderSettings.set(provider_name, key, value, description=description)

    return jsonify({"provider": provider_name, "key": key, "message": "Setting saved"}), 200


@ppv_enrichment_bp.route("/queue/cleanup", methods=["POST"])
@cross_origin()
@handle_errors(return_json=True, default_message="Error cleaning up PPV enrichment queue")
def cleanup_enrichment_queue():
    """
    Mark non-enrichable queued PPV channels as skipped.

    Optional JSON body: {"dry_run": true, "account_id": 1}
    Empty POST is accepted.
    """
    from services.ppv.queue_cleanup import cleanup_ppv_queue

    data = request.get_json(silent=True) or {}
    dry_run = bool(data.get("dry_run", False))
    account_id = data.get("account_id")

    result = cleanup_ppv_queue(dry_run=dry_run, account_id=account_id)
    return jsonify(result), 200


@ppv_enrichment_bp.route("/sportsipy-refresh", methods=["POST"])
@cross_origin()
@handle_errors(return_json=True, default_message="Error refreshing sportsipy teams")
def refresh_sportsipy_teams():
    """
    Trigger a sportsipy team data refresh (same job as the weekly scheduler task).

    No UI exists for this; use this endpoint or wait for the scheduled run.
    """
    from services.sportsipy_service import refresh_teams_from_sportsipy, seed_initial_team_data

    seed_result = seed_initial_team_data()
    result = refresh_teams_from_sportsipy(
        sports=["mlb", "nba", "ncaab", "ncaaf", "nfl", "nhl"],
    )
    return jsonify({"seed": seed_result, "refresh": result}), 200 if result.get("success") else 500


def _mask_value(field_type: str, value: str) -> str:
    """Return a masked representation of *value* for password fields."""
    if field_type != "password" or not value:
        return value
    visible = min(4, len(value))
    return value[:visible] + "****"
