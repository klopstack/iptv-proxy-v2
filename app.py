#!/usr/bin/env python3
"""
IPTV M3U Proxy v2 - Web UI for managing multiple IPTV services with filtering

TODO: REFACTORING NEEDED
- This file is ~1500 lines and growing. Consider splitting into:
  - routes/accounts.py - Account management routes
  - routes/filters.py - Filter management routes  
  - routes/rulesets.py - Ruleset and tag rule routes
  - routes/playlists.py - Playlist generation routes
  - routes/tags.py - Tag processing routes
  - routes/cache.py - Cache management routes
- Use Flask Blueprints for better organization
- Extract business logic into service layer (some already in services/)
"""

import json
import logging
import os

from flask import Flask, Response, jsonify, render_template, request
from flask_cors import CORS

from models import Account, AccountRuleSet, Category, Channel, ChannelTag, Filter, PlaylistConfig, RuleSet, Tag, TagRule, db
from services.cache_service import CacheService
from services.iptv_service import IPTVService
from services.scheduler import SyncScheduler
from services.tag_service import TagService

# Initialize Flask app
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:////app/data/iptv_proxy.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

# Initialize extensions
CORS(app)
db.init_app(app)

# Initialize services
cache_service = CacheService()

# Initialize sync scheduler (6 hours by default, configurable via SYNC_INTERVAL_HOURS env var)
sync_interval = int(os.getenv("SYNC_INTERVAL_HOURS", "6"))
sync_scheduler = SyncScheduler(app, interval_hours=sync_interval)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Web UI Routes
# ============================================================================


@app.route("/")
def index():
    """Main dashboard"""
    return render_template("index.html")


@app.route("/accounts")
def accounts_page():
    """Accounts management page"""
    return render_template("accounts.html")


@app.route("/filters")
def filters_page():
    """Filters management page"""
    return render_template("filters.html")


@app.route("/test")
def test_page():
    """Test and preview page"""
    return render_template("test.html")


@app.route("/rulesets")
def rulesets_page():
    """Rulesets and tags management page"""
    return render_template("rulesets.html")


# ============================================================================
# API Routes - Accounts
# ============================================================================


@app.route("/api/accounts", methods=["GET"])
def get_accounts():
    """Get all accounts"""
    accounts = Account.query.all()
    return jsonify(
        [
            {"id": a.id, "name": a.name, "server": a.server, "username": a.username, "enabled": a.enabled}
            for a in accounts
        ]
    )


@app.route("/api/accounts", methods=["POST"])
def create_account():
    """Create new account"""
    data = request.json

    account = Account(
        name=data["name"],
        server=data["server"],
        username=data["username"],
        password=data["password"],
        enabled=data.get("enabled", True),
    )

    db.session.add(account)
    db.session.commit()

    return (
        jsonify(
            {
                "id": account.id,
                "name": account.name,
                "server": account.server,
                "username": account.username,
                "enabled": account.enabled,
            }
        ),
        201,
    )


@app.route("/api/accounts/<int:account_id>", methods=["PUT"])
def update_account(account_id):
    """Update account"""
    account = Account.query.get_or_404(account_id)
    data = request.json

    account.name = data.get("name", account.name)
    account.server = data.get("server", account.server)
    account.username = data.get("username", account.username)
    if "password" in data:
        account.password = data["password"]
    account.enabled = data.get("enabled", account.enabled)

    db.session.commit()

    # Clear cache for this account
    cache_service.clear_account_cache(account_id)

    return jsonify(
        {
            "id": account.id,
            "name": account.name,
            "server": account.server,
            "username": account.username,
            "enabled": account.enabled,
        }
    )


@app.route("/api/accounts/<int:account_id>", methods=["DELETE"])
def delete_account(account_id):
    """Delete account"""
    account = Account.query.get_or_404(account_id)

    # Delete associated filters
    Filter.query.filter_by(account_id=account_id).delete()

    db.session.delete(account)
    db.session.commit()

    # Clear cache
    cache_service.clear_account_cache(account_id)

    return "", 204


# TODO: Add test coverage for account testing endpoint
@app.route("/api/accounts/<int:account_id>/test", methods=["POST"])
def test_account(account_id):
    """Test account connection"""
    account = Account.query.get_or_404(account_id)

    try:
        service = IPTVService(account.server, account.username, account.password)
        auth_info = service.authenticate()

        return jsonify(
            {
                "success": True,
                "server_info": {
                    "url": auth_info.get("server_info", {}).get("url", ""),
                    "time": auth_info.get("server_info", {}).get("time_now", ""),
                },
                "user_info": {
                    "username": auth_info.get("user_info", {}).get("username", ""),
                    "status": auth_info.get("user_info", {}).get("status", ""),
                    "exp_date": auth_info.get("user_info", {}).get("exp_date", ""),
                    "max_connections": auth_info.get("user_info", {}).get("max_connections", ""),
                },
            }
        )
    except Exception as e:
        logger.error(f"Error testing account {account_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


# TODO: Add test coverage for categories endpoint (requires mocking IPTVService)
@app.route("/api/accounts/<int:account_id>/categories", methods=["GET"])
def get_account_categories(account_id):
    """Get categories for account"""
    account = Account.query.get_or_404(account_id)

    try:
        service = IPTVService(account.server, account.username, account.password)
        categories = service.get_live_categories()

        # Cache it
        cache_service.cache_categories(account_id, categories)

        # Trigger tag processing in background if streams are cached
        streams = cache_service.get_cached_streams(account_id)
        if streams:
            try:
                _process_tags_for_account(account_id, streams, categories)
            except Exception as tag_error:
                logger.warning(f"Error auto-processing tags for account {account_id}: {tag_error}")

        return jsonify(categories)
    except Exception as e:
        logger.error(f"Error fetching categories for account {account_id}: {e}")
        return jsonify({"error": str(e)}), 400


def _process_tags_for_account(account_id, streams, categories):
    """Helper function to process tags for an account (internal use)"""
    from models import Account

    account = Account.query.get(account_id)
    if not account:
        return

    # Build category map
    category_map = {str(c["category_id"]): c["category_name"] for c in categories}

    # Get tag rules for this account
    tag_rules = TagService.get_rules_for_account(account)

    # Clear existing channel tags for this account
    ChannelTag.query.filter_by(account_id=account_id).delete()

    # Process each stream
    for stream in streams:
        stream_id = str(stream.get("stream_id"))
        channel_name = stream.get("name", "")
        category_id = str(stream.get("category_id", ""))
        category_name = category_map.get(category_id, "")

        # Extract tags
        tags, cleaned_name = TagService.extract_tags(channel_name, category_name, tag_rules)

        # Store tags
        for tag_name in tags:
            normalized_tag = TagService.normalize_tag_name(tag_name)
            
            # Skip empty or too-short tags
            if not normalized_tag or len(normalized_tag) < 2:
                continue

            # Get or create tag
            tag = Tag.query.filter_by(name=normalized_tag).first()
            if not tag:
                tag = Tag(name=normalized_tag)
                db.session.add(tag)
                db.session.flush()

            # Create channel tag association
            channel_tag = ChannelTag(account_id=account_id, stream_id=stream_id, tag_id=tag.id)
            db.session.add(channel_tag)

    db.session.commit()
    logger.info(f"Auto-processed tags for account {account_id}")


# TODO: Add test coverage for stats endpoint (requires mocking IPTVService)
@app.route("/api/accounts/<int:account_id>/stats", methods=["GET"])
def get_account_stats(account_id):
    """Get statistics for account"""
    account = Account.query.get_or_404(account_id)

    try:
        service = IPTVService(account.server, account.username, account.password)

        # Get cached or fetch new
        streams = cache_service.get_cached_streams(account_id)
        if not streams:
            streams = service.get_live_streams()
            cache_service.cache_streams(account_id, streams)

        categories = cache_service.get_cached_categories(account_id)
        if not categories:
            categories = service.get_live_categories()
            cache_service.cache_categories(account_id, categories)

        # Auto-process tags when stats are fetched
        try:
            _process_tags_for_account(account_id, streams, categories)
        except Exception as tag_error:
            logger.warning(f"Error auto-processing tags for account {account_id}: {tag_error}")

        # Count by category
        category_counts = {}
        for stream in streams:
            cat_id = str(stream.get("category_id", "Unknown"))
            category_counts[cat_id] = category_counts.get(cat_id, 0) + 1

        return jsonify(
            {"total_channels": len(streams), "total_categories": len(categories), "category_counts": category_counts}
        )
    except Exception as e:
        logger.error(f"Error fetching stats for account {account_id}: {e}")
        return jsonify({"error": str(e)}), 400


# ============================================================================
# API Routes - Filters
# ============================================================================


@app.route("/api/filters", methods=["GET"])
def get_filters():
    """Get all filters"""
    filters = Filter.query.all()
    return jsonify(
        [
            {
                "id": f.id,
                "account_id": f.account_id,
                "name": f.name,
                "filter_type": f.filter_type,
                "filter_action": f.filter_action,
                "filter_value": f.filter_value,
                "enabled": f.enabled,
            }
            for f in filters
        ]
    )


@app.route("/api/filters", methods=["POST"])
def create_filter():
    """Create new filter"""
    data = request.json

    filter_obj = Filter(
        account_id=data["account_id"],
        name=data["name"],
        filter_type=data["filter_type"],
        filter_action=data["filter_action"],
        filter_value=data["filter_value"],
        enabled=data.get("enabled", True),
    )

    db.session.add(filter_obj)
    db.session.commit()

    # Clear cache for this account
    cache_service.clear_account_cache(data["account_id"])

    return (
        jsonify(
            {
                "id": filter_obj.id,
                "account_id": filter_obj.account_id,
                "name": filter_obj.name,
                "filter_type": filter_obj.filter_type,
                "filter_action": filter_obj.filter_action,
                "filter_value": filter_obj.filter_value,
                "enabled": filter_obj.enabled,
            }
        ),
        201,
    )


@app.route("/api/filters/<int:filter_id>", methods=["PUT"])
def update_filter(filter_id):
    """Update filter"""
    filter_obj = Filter.query.get_or_404(filter_id)
    data = request.json

    filter_obj.name = data.get("name", filter_obj.name)
    filter_obj.filter_type = data.get("filter_type", filter_obj.filter_type)
    filter_obj.filter_action = data.get("filter_action", filter_obj.filter_action)
    filter_obj.filter_value = data.get("filter_value", filter_obj.filter_value)
    filter_obj.enabled = data.get("enabled", filter_obj.enabled)

    db.session.commit()

    # Clear cache
    cache_service.clear_account_cache(filter_obj.account_id)

    return jsonify(
        {
            "id": filter_obj.id,
            "account_id": filter_obj.account_id,
            "name": filter_obj.name,
            "filter_type": filter_obj.filter_type,
            "filter_action": filter_obj.filter_action,
            "filter_value": filter_obj.filter_value,
            "enabled": filter_obj.enabled,
        }
    )


@app.route("/api/filters/<int:filter_id>", methods=["DELETE"])
def delete_filter(filter_id):
    """Delete filter"""
    filter_obj = Filter.query.get_or_404(filter_id)
    account_id = filter_obj.account_id

    db.session.delete(filter_obj)
    db.session.commit()

    # Clear cache
    cache_service.clear_account_cache(account_id)

    return "", 204


@app.route("/api/accounts/<int:account_id>/filters", methods=["GET"])
def get_account_filters(account_id):
    """Get filters for specific account"""
    filters = Filter.query.filter_by(account_id=account_id).all()
    return jsonify(
        [
            {
                "id": f.id,
                "name": f.name,
                "filter_type": f.filter_type,
                "filter_action": f.filter_action,
                "filter_value": f.filter_value,
                "enabled": f.enabled,
            }
            for f in filters
        ]
    )


# ============================================================================
# API Routes - Rule Sets
# ============================================================================


@app.route("/api/rulesets", methods=["GET"])
def get_rulesets():
    """Get all rulesets"""
    rulesets = RuleSet.query.order_by(RuleSet.priority, RuleSet.name).all()
    return jsonify(
        [
            {
                "id": rs.id,
                "name": rs.name,
                "description": rs.description,
                "is_default": rs.is_default,
                "enabled": rs.enabled,
                "priority": rs.priority,
                "rule_count": len(rs.rules),
            }
            for rs in rulesets
        ]
    )


@app.route("/api/rulesets", methods=["POST"])
def create_ruleset():
    """Create new ruleset"""
    data = request.json

    ruleset = RuleSet(
        name=data["name"],
        description=data.get("description", ""),
        is_default=data.get("is_default", False),
        enabled=data.get("enabled", True),
        priority=data.get("priority", 100),
    )

    db.session.add(ruleset)
    db.session.commit()

    return (
        jsonify(
            {
                "id": ruleset.id,
                "name": ruleset.name,
                "description": ruleset.description,
                "is_default": ruleset.is_default,
                "enabled": ruleset.enabled,
                "priority": ruleset.priority,
                "rule_count": 0,
            }
        ),
        201,
    )


@app.route("/api/rulesets/<int:ruleset_id>", methods=["GET"])
def get_ruleset(ruleset_id):
    """Get a single ruleset"""
    ruleset = RuleSet.query.get_or_404(ruleset_id)
    return jsonify(
        {
            "id": ruleset.id,
            "name": ruleset.name,
            "description": ruleset.description,
            "is_default": ruleset.is_default,
            "enabled": ruleset.enabled,
            "priority": ruleset.priority,
            "rule_count": len(ruleset.rules),
        }
    )


@app.route("/api/rulesets/<int:ruleset_id>", methods=["PUT"])
def update_ruleset(ruleset_id):
    """Update ruleset"""
    ruleset = RuleSet.query.get_or_404(ruleset_id)
    data = request.json

    ruleset.name = data.get("name", ruleset.name)
    ruleset.description = data.get("description", ruleset.description)
    ruleset.is_default = data.get("is_default", ruleset.is_default)
    ruleset.enabled = data.get("enabled", ruleset.enabled)
    ruleset.priority = data.get("priority", ruleset.priority)

    db.session.commit()
    cache_service.clear_all()

    return jsonify(
        {
            "id": ruleset.id,
            "name": ruleset.name,
            "description": ruleset.description,
            "is_default": ruleset.is_default,
            "enabled": ruleset.enabled,
            "priority": ruleset.priority,
            "rule_count": len(ruleset.rules),
        }
    )


@app.route("/api/rulesets/<int:ruleset_id>", methods=["DELETE"])
def delete_ruleset(ruleset_id):
    """Delete ruleset"""
    ruleset = RuleSet.query.get_or_404(ruleset_id)

    # Remove associations with accounts
    AccountRuleSet.query.filter_by(ruleset_id=ruleset_id).delete()

    db.session.delete(ruleset)
    db.session.commit()
    cache_service.clear_all()

    return "", 204


@app.route("/api/rulesets/create-default", methods=["POST"])
def create_default_ruleset():
    """Create default ruleset with common IPTV tag extraction rules"""
    try:
        ruleset = TagService.create_default_ruleset(db.session)
        cache_service.clear_all()

        return jsonify(
            {
                "success": True,
                "id": ruleset.id,
                "name": ruleset.name,
                "rule_count": len(ruleset.rules),
                "message": f"Created default ruleset with {len(ruleset.rules)} rules",
            }
        )
    except Exception as e:
        logger.error(f"Error creating default ruleset: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/rulesets/<int:ruleset_id>/rules", methods=["GET"])
def get_ruleset_rules(ruleset_id):
    """Get all rules for a specific ruleset"""
    RuleSet.query.get_or_404(ruleset_id)  # Validate ruleset exists
    rules = TagRule.query.filter_by(ruleset_id=ruleset_id).order_by(TagRule.priority, TagRule.id).all()

    return jsonify(
        [
            {
                "id": r.id,
                "name": r.name,
                "pattern": r.pattern,
                "pattern_type": r.pattern_type,
                "tag_name": r.tag_name,
                "source": r.source,
                "remove_from_name": r.remove_from_name,
                "priority": r.priority,
                "enabled": r.enabled,
            }
            for r in rules
        ]
    )


# ============================================================================
# API Routes - Account Rulesets
# ============================================================================


@app.route("/api/accounts/<int:account_id>/rulesets", methods=["GET"])
def get_account_rulesets(account_id):
    """Get rulesets assigned to an account"""
    Account.query.get_or_404(account_id)  # Validate account exists

    assignments = (
        db.session.query(RuleSet, AccountRuleSet.priority)
        .join(AccountRuleSet, RuleSet.id == AccountRuleSet.ruleset_id)
        .filter(AccountRuleSet.account_id == account_id)
        .order_by(AccountRuleSet.priority)
        .all()
    )

    return jsonify(
        [
            {
                "id": rs.id,
                "name": rs.name,
                "description": rs.description,
                "is_default": rs.is_default,
                "enabled": rs.enabled,
                "priority": priority,
                "rule_count": len(rs.rules),
            }
            for rs, priority in assignments
        ]
    )


@app.route("/api/accounts/<int:account_id>/rulesets", methods=["POST"])
def assign_ruleset_to_account(account_id):
    """Assign a ruleset to an account"""
    Account.query.get_or_404(account_id)  # Validate account exists
    data = request.json

    ruleset_id = data["ruleset_id"]
    priority = data.get("priority", 100)

    # Check if already assigned
    existing = AccountRuleSet.query.filter_by(account_id=account_id, ruleset_id=ruleset_id).first()

    if existing:
        # Update priority
        existing.priority = priority
    else:
        # Create new assignment
        assignment = AccountRuleSet(account_id=account_id, ruleset_id=ruleset_id, priority=priority)
        db.session.add(assignment)

    db.session.commit()
    cache_service.clear_account_cache(account_id)

    return jsonify({"success": True}), 201


@app.route("/api/accounts/<int:account_id>/rulesets/<int:ruleset_id>", methods=["DELETE"])
def remove_ruleset_from_account(account_id, ruleset_id):
    """Remove a ruleset assignment from an account"""
    Account.query.get_or_404(account_id)  # Validate account exists

    AccountRuleSet.query.filter_by(account_id=account_id, ruleset_id=ruleset_id).delete()

    db.session.commit()
    cache_service.clear_account_cache(account_id)

    return "", 204


# ============================================================================
# API Routes - Tag Rules
# ============================================================================


@app.route("/api/tag-rules", methods=["GET"])
def get_tag_rules():
    """Get all tag extraction rules (optionally filtered by ruleset)"""
    ruleset_id = request.args.get("ruleset_id", type=int)

    query = TagRule.query
    if ruleset_id:
        query = query.filter_by(ruleset_id=ruleset_id)

    rules = query.order_by(TagRule.priority, TagRule.id).all()
    return jsonify(
        [
            {
                "id": r.id,
                "ruleset_id": r.ruleset_id,
                "name": r.name,
                "pattern": r.pattern,
                "pattern_type": r.pattern_type,
                "tag_name": r.tag_name,
                "source": r.source,
                "remove_from_name": r.remove_from_name,
                "priority": r.priority,
                "enabled": r.enabled,
            }
            for r in rules
        ]
    )


@app.route("/api/tag-rules", methods=["POST"])
def create_tag_rule():
    """Create new tag extraction rule"""
    data = request.json

    # Verify ruleset exists
    ruleset_id = data.get("ruleset_id")
    if not ruleset_id:
        return jsonify({"error": "ruleset_id is required"}), 400

    ruleset = RuleSet.query.get(ruleset_id)
    if not ruleset:
        return jsonify({"error": f"RuleSet {ruleset_id} not found"}), 404

    rule = TagRule(
        name=data["name"],
        pattern=data["pattern"],
        pattern_type=data["pattern_type"],
        tag_name=data["tag_name"],
        source=data["source"],
        ruleset_id=ruleset_id,
        remove_from_name=data.get("remove_from_name", True),
        priority=data.get("priority", 100),
        enabled=data.get("enabled", True),
    )

    db.session.add(rule)
    db.session.commit()

    # Clear all account caches since tags affect all channels
    cache_service.clear_all()

    return (
        jsonify(
            {
                "id": rule.id,
                "name": rule.name,
                "pattern": rule.pattern,
                "pattern_type": rule.pattern_type,
                "tag_name": rule.tag_name,
                "source": rule.source,
                "remove_from_name": rule.remove_from_name,
                "priority": rule.priority,
                "enabled": rule.enabled,
            }
        ),
        201,
    )


@app.route("/api/tag-rules/<int:rule_id>", methods=["PUT"])
def update_tag_rule(rule_id):
    """Update tag extraction rule"""
    rule = TagRule.query.get_or_404(rule_id)
    data = request.json

    rule.name = data.get("name", rule.name)
    rule.pattern = data.get("pattern", rule.pattern)
    rule.pattern_type = data.get("pattern_type", rule.pattern_type)
    rule.tag_name = data.get("tag_name", rule.tag_name)
    rule.source = data.get("source", rule.source)
    rule.remove_from_name = data.get("remove_from_name", rule.remove_from_name)
    rule.priority = data.get("priority", rule.priority)
    rule.enabled = data.get("enabled", rule.enabled)

    db.session.commit()
    cache_service.clear_all()

    return jsonify(
        {
            "id": rule.id,
            "name": rule.name,
            "pattern": rule.pattern,
            "pattern_type": rule.pattern_type,
            "tag_name": rule.tag_name,
            "source": rule.source,
            "remove_from_name": rule.remove_from_name,
            "priority": rule.priority,
            "enabled": rule.enabled,
        }
    )


@app.route("/api/tag-rules/<int:rule_id>", methods=["DELETE"])
def delete_tag_rule(rule_id):
    """Delete tag extraction rule"""
    rule = TagRule.query.get_or_404(rule_id)

    db.session.delete(rule)
    db.session.commit()
    cache_service.clear_all()

    return "", 204


@app.route("/api/tag-rules/create-defaults", methods=["POST"])
def create_default_tag_rules():
    """Create default tag extraction ruleset"""
    try:
        ruleset = TagService.create_default_ruleset(db.session)
        cache_service.clear_all()

        return jsonify(
            {
                "success": True,
                "ruleset_id": ruleset.id,
                "ruleset_name": ruleset.name,
                "count": len(ruleset.rules),
                "message": f"Created default ruleset with {len(ruleset.rules)} rules",
            }
        )
    except Exception as e:
        logger.error(f"Error creating default ruleset: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


# TODO: Add test coverage for tags listing endpoint
@app.route("/api/tags", methods=["GET"])
def get_tags():
    """Get all tags with optional account filtering and usage counts
    
    Query parameters:
    - account_id (optional): Filter tags to specific account
    - with_counts (optional): Include channel counts per tag
    """
    account_id = request.args.get("account_id", type=int)
    with_counts = request.args.get("with_counts", "false").lower() == "true"
    
    if account_id:
        # Filter tags for specific account
        tags_query = (
            db.session.query(Tag)
            .join(ChannelTag)
            .filter(ChannelTag.account_id == account_id)
            .distinct()
            .order_by(Tag.name)
        )
    else:
        # All tags across all accounts
        tags_query = Tag.query.order_by(Tag.name)
    
    tags = tags_query.all()
    
    if with_counts:
        # Build counts for each tag
        result = []
        for tag in tags:
            if account_id:
                count = ChannelTag.query.filter_by(tag_id=tag.id, account_id=account_id).count()
            else:
                count = ChannelTag.query.filter_by(tag_id=tag.id).count()
            
            result.append({
                "id": tag.id,
                "name": tag.name,
                "created_at": tag.created_at.isoformat(),
                "channel_count": count
            })
        return jsonify(result)
    else:
        return jsonify([{"id": t.id, "name": t.name, "created_at": t.created_at.isoformat()} for t in tags])


# TODO: Add test coverage for tag processing endpoint (requires mocking IPTVService)
@app.route("/api/accounts/<int:account_id>/process-tags", methods=["POST"])
def process_account_tags(account_id):
    """Process and extract tags for all channels in an account"""
    account = Account.query.get_or_404(account_id)

    try:
        # Mark start time for this processing run
        from datetime import datetime
        processing_start = datetime.utcnow()
        
        # Check if channels are synced to database
        db_channels = Channel.query.filter_by(account_id=account_id, is_active=True).all()
        
        if db_channels:
            # Use database channels (fast path)
            logger.info(f"Processing tags from database for account {account_id}")
            return _process_tags_from_channels(account, db_channels, processing_start)
        else:
            # Fall back to API
            logger.info(f"Processing tags from API for account {account_id} (no synced channels)")
            return _process_tags_from_api(account, processing_start)

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error processing tags for account {account_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


def _process_tags_from_channels(account, channels, processing_start):
    """Process tags using Channel database records and update cleaned names"""
    # Get tag rules for this account
    tag_rules = TagService.get_rules_for_account(account)
    
    # Build lookup of existing channel tags for efficient updates
    existing_tags = {}
    for ct in ChannelTag.query.filter_by(account_id=account.id).all():
        key = (ct.stream_id, ct.tag_id)
        existing_tags[key] = ct
    
    # Process each channel
    processed_count = 0
    tag_counts = {}
    tags_created = 0
    tags_updated = 0
    channels_updated = 0
    
    for channel in channels:
        category_name = channel.category.category_name if channel.category else ""
        
        # Extract tags and cleaned name
        tags, cleaned_name = TagService.extract_tags(channel.name, category_name, tag_rules)
        
        # Update cleaned name in database if changed
        if channel.cleaned_name != cleaned_name:
            channel.cleaned_name = cleaned_name
            channel.updated_at = processing_start
            channels_updated += 1
        
        # Store tags
        for tag_name in tags:
            # Normalize tag name
            normalized_tag = TagService.normalize_tag_name(tag_name)
            
            # Skip empty or too-short tags
            if not normalized_tag or len(normalized_tag) < 2:
                continue
            
            # Get or create tag
            tag = Tag.query.filter_by(name=normalized_tag).first()
            if not tag:
                tag = Tag(name=normalized_tag)
                db.session.add(tag)
                db.session.flush()  # Get the ID
            
            # Check if channel tag association exists
            key = (channel.stream_id, tag.id)
            if key in existing_tags:
                # Update existing - mark as fresh
                existing_tags[key].updated_at = processing_start
                tags_updated += 1
            else:
                # Create new channel tag association
                channel_tag = ChannelTag(
                    account_id=account.id,
                    stream_id=channel.stream_id,
                    tag_id=tag.id,
                    created_at=processing_start,
                    updated_at=processing_start
                )
                db.session.add(channel_tag)
                tags_created += 1
            
            # Count tags
            tag_counts[normalized_tag] = tag_counts.get(normalized_tag, 0) + 1
        
        processed_count += 1
    
    # Remove channel tags that weren't updated in this processing run
    stale_tags = ChannelTag.query.filter(
        ChannelTag.account_id == account.id,
        ChannelTag.updated_at < processing_start
    )
    tags_removed = stale_tags.delete()
    
    db.session.commit()
    
    logger.info(
        f"Processed tags for {processed_count} channels in account {account.id}: "
        f"{tags_created} created, {tags_updated} updated, {tags_removed} removed, "
        f"{channels_updated} channel names cleaned"
    )
    
    return jsonify({
        "success": True,
        "processed": processed_count,
        "unique_tags": len(tag_counts),
        "tag_counts": tag_counts,
        "tags_created": tags_created,
        "tags_updated": tags_updated,
        "tags_removed": tags_removed,
        "channels_updated": channels_updated,
        "using_database": True
    })


def _process_tags_from_api(account, processing_start):
    """Process tags using IPTV API (fallback)"""
    # Get streams
    service = IPTVService(account.server, account.username, account.password)
    streams = cache_service.get_cached_streams(account.id)
    if not streams:
        streams = service.get_live_streams()
        cache_service.cache_streams(account.id, streams)

    categories = cache_service.get_cached_categories(account.id)
    if not categories:
        categories = service.get_live_categories()
        cache_service.cache_categories(account.id, categories)

    # Build category map
    category_map = {str(c["category_id"]): c["category_name"] for c in categories}

    # Get tag rules for this account (account-specific rulesets or defaults)
    tag_rules = TagService.get_rules_for_account(account)
    
    # Build lookup of existing channel tags for efficient updates
    existing_tags = {}
    for ct in ChannelTag.query.filter_by(account_id=account.id).all():
        key = (ct.stream_id, ct.tag_id)
        existing_tags[key] = ct

    # Process each stream
    processed_count = 0
    tag_counts = {}
    tags_created = 0
    tags_updated = 0

    for stream in streams:
        stream_id = str(stream.get("stream_id"))
        channel_name = stream.get("name", "")
        category_id = str(stream.get("category_id", ""))
        category_name = category_map.get(category_id, "")

        # Extract tags
        tags, cleaned_name = TagService.extract_tags(channel_name, category_name, tag_rules)

        # Store tags
        for tag_name in tags:
            # Normalize tag name
            normalized_tag = TagService.normalize_tag_name(tag_name)
            
            # Skip empty or too-short tags
            if not normalized_tag or len(normalized_tag) < 2:
                continue

            # Get or create tag
            tag = Tag.query.filter_by(name=normalized_tag).first()
            if not tag:
                tag = Tag(name=normalized_tag)
                db.session.add(tag)
                db.session.flush()  # Get the ID

            # Check if channel tag association exists
            key = (stream_id, tag.id)
            if key in existing_tags:
                # Update existing - mark as fresh
                existing_tags[key].updated_at = processing_start
                tags_updated += 1
            else:
                # Create new channel tag association
                channel_tag = ChannelTag(
                    account_id=account.id, 
                    stream_id=stream_id, 
                    tag_id=tag.id,
                    created_at=processing_start,
                    updated_at=processing_start
                )
                db.session.add(channel_tag)
                tags_created += 1

            # Count tags
            tag_counts[normalized_tag] = tag_counts.get(normalized_tag, 0) + 1

        processed_count += 1

    # Remove channel tags that weren't updated in this processing run
    # These are tags that are no longer generated by the current rulesets
    stale_tags = ChannelTag.query.filter(
        ChannelTag.account_id == account.id,
        ChannelTag.updated_at < processing_start
    )
    tags_removed = stale_tags.delete()

    db.session.commit()

    logger.info(
        f"Processed tags for {processed_count} channels in account {account.id}: "
        f"{tags_created} created, {tags_updated} updated, {tags_removed} removed"
    )

    return jsonify({
        "success": True, 
        "processed": processed_count, 
        "unique_tags": len(tag_counts), 
        "tag_counts": tag_counts,
        "tags_created": tags_created,
        "tags_updated": tags_updated,
        "tags_removed": tags_removed,
        "using_database": False
    })


# TODO: Add test coverage for account tags listing endpoint
@app.route("/api/accounts/<int:account_id>/tags", methods=["GET"])
def get_account_tags(account_id):
    """Get all tags used in an account with channel counts"""
    Account.query.get_or_404(account_id)  # Validate account exists

    # Query tags for this account with counts
    from sqlalchemy import func

    results = (
        db.session.query(Tag.id, Tag.name, func.count(ChannelTag.id).label("channel_count"))
        .join(ChannelTag, Tag.id == ChannelTag.tag_id)
        .filter(ChannelTag.account_id == account_id)
        .group_by(Tag.id, Tag.name)
        .order_by(Tag.name)
        .all()
    )

    return jsonify([{"id": r.id, "name": r.name, "channel_count": r.channel_count} for r in results])


@app.route("/api/accounts/<int:account_id>/tags/search", methods=["GET"])
def search_account_tags(account_id):
    """Search tags for an account by name (autocomplete endpoint)"""
    Account.query.get_or_404(account_id)  # Validate account exists
    
    query = request.args.get("q", "").strip()
    limit = request.args.get("limit", 20, type=int)
    
    # Query tags matching the search term
    from sqlalchemy import func
    
    search_pattern = f"%{query}%" if query else "%"
    
    results = (
        db.session.query(Tag.id, Tag.name, func.count(ChannelTag.id).label("channel_count"))
        .join(ChannelTag, Tag.id == ChannelTag.tag_id)
        .filter(
            ChannelTag.account_id == account_id,
            Tag.name.ilike(search_pattern)
        )
        .group_by(Tag.id, Tag.name)
        .order_by(Tag.name)
        .limit(limit)
        .all()
    )
    
    return jsonify([{"id": r.id, "name": r.name, "channel_count": r.channel_count} for r in results])


# ============================================================================
# API Routes - Channel Sync
# ============================================================================


@app.route("/api/accounts/<int:account_id>/sync", methods=["POST"])
def sync_account_channels(account_id):
    """Sync channels for a specific account"""
    from services.sync_service import ChannelSyncService
    
    Account.query.get_or_404(account_id)  # Validate account exists
    
    try:
        stats = ChannelSyncService.sync_account(account_id)
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error syncing account {account_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/sync/all", methods=["POST"])
def sync_all_accounts():
    """Sync channels for all enabled accounts"""
    from services.sync_service import ChannelSyncService
    
    try:
        results = ChannelSyncService.sync_all_accounts()
        return jsonify({
            "success": True,
            "accounts_synced": len(results),
            "results": results
        })
    except Exception as e:
        logger.error(f"Error syncing all accounts: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/accounts/<int:account_id>/sync/status", methods=["GET"])
def get_sync_status(account_id):
    """Get sync status for an account"""
    from services.sync_service import ChannelSyncService
    
    Account.query.get_or_404(account_id)  # Validate account exists
    
    try:
        status = ChannelSyncService.get_sync_status(account_id)
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error getting sync status for account {account_id}: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# API Routes - Playlist Configurations
# ============================================================================


@app.route("/api/playlist-configs", methods=["GET"])
def get_playlist_configs():
    """Get all playlist configurations"""
    configs = PlaylistConfig.query.all()
    return jsonify(
        [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "include_accounts": json.loads(c.include_accounts) if c.include_accounts else [],
                "exclude_accounts": json.loads(c.exclude_accounts) if c.exclude_accounts else [],
                "include_tags": json.loads(c.include_tags) if c.include_tags else [],
                "exclude_tags": json.loads(c.exclude_tags) if c.exclude_tags else [],
                "tag_match_mode": c.tag_match_mode,
                "enabled": c.enabled,
            }
            for c in configs
        ]
    )


# TODO: Add test coverage for playlist config CRUD endpoints
@app.route("/api/playlist-configs", methods=["POST"])
def create_playlist_config():
    """Create new playlist configuration"""
    data = request.json

    config = PlaylistConfig(
        name=data["name"],
        description=data.get("description", ""),
        include_accounts=json.dumps(data.get("include_accounts", [])),
        exclude_accounts=json.dumps(data.get("exclude_accounts", [])),
        include_tags=json.dumps(data.get("include_tags", [])),
        exclude_tags=json.dumps(data.get("exclude_tags", [])),
        tag_match_mode=data.get("tag_match_mode", "any"),
        enabled=data.get("enabled", True),
    )

    db.session.add(config)
    db.session.commit()

    return (
        jsonify(
            {
                "id": config.id,
                "name": config.name,
                "description": config.description,
                "include_accounts": json.loads(config.include_accounts),
                "exclude_accounts": json.loads(config.exclude_accounts),
                "include_tags": json.loads(config.include_tags),
                "exclude_tags": json.loads(config.exclude_tags),
                "tag_match_mode": config.tag_match_mode,
                "enabled": config.enabled,
            }
        ),
        201,
    )


@app.route("/api/playlist-configs/<int:config_id>", methods=["PUT"])
def update_playlist_config(config_id):
    """Update playlist configuration"""
    config = PlaylistConfig.query.get_or_404(config_id)
    data = request.json

    config.name = data.get("name", config.name)
    config.description = data.get("description", config.description)

    if "include_accounts" in data:
        config.include_accounts = json.dumps(data["include_accounts"])
    if "exclude_accounts" in data:
        config.exclude_accounts = json.dumps(data["exclude_accounts"])
    if "include_tags" in data:
        config.include_tags = json.dumps(data["include_tags"])
    if "exclude_tags" in data:
        config.exclude_tags = json.dumps(data["exclude_tags"])

    config.tag_match_mode = data.get("tag_match_mode", config.tag_match_mode)
    config.enabled = data.get("enabled", config.enabled)

    db.session.commit()

    return jsonify(
        {
            "id": config.id,
            "name": config.name,
            "description": config.description,
            "include_accounts": json.loads(config.include_accounts),
            "exclude_accounts": json.loads(config.exclude_accounts),
            "include_tags": json.loads(config.include_tags),
            "exclude_tags": json.loads(config.exclude_tags),
            "tag_match_mode": config.tag_match_mode,
            "enabled": config.enabled,
        }
    )


@app.route("/api/playlist-configs/<int:config_id>", methods=["DELETE"])
def delete_playlist_config(config_id):
    """Delete playlist configuration"""
    config = PlaylistConfig.query.get_or_404(config_id)

    db.session.delete(config)
    db.session.commit()

    return "", 204


@app.route("/api/playlist-configs/<int:config_id>/preview", methods=["GET"])
def preview_playlist_config(config_id):
    """Preview channels that would be included in this playlist configuration"""
    config = PlaylistConfig.query.get_or_404(config_id)
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    try:
        # Parse config
        include_accounts = json.loads(config.include_accounts) if config.include_accounts else []
        exclude_accounts = json.loads(config.exclude_accounts) if config.exclude_accounts else []
        include_tags = json.loads(config.include_tags) if config.include_tags else []
        exclude_tags = json.loads(config.exclude_tags) if config.exclude_tags else []

        # Get all enabled accounts or filter by include/exclude
        if include_accounts:
            accounts = Account.query.filter(Account.id.in_(include_accounts), Account.enabled.is_(True)).all()
        else:
            accounts = Account.query.filter(Account.enabled.is_(True)).all()
            if exclude_accounts:
                accounts = [a for a in accounts if a.id not in exclude_accounts]

        # Collect matching channels
        matching_channels = []

        for account in accounts:
            # Get streams for this account
            service = IPTVService(account.server, account.username, account.password)
            streams = cache_service.get_cached_streams(account.id)
            if not streams:
                streams = service.get_live_streams()
                cache_service.cache_streams(account.id, streams)

            categories = cache_service.get_cached_categories(account.id)
            if not categories:
                categories = service.get_live_categories()
                cache_service.cache_categories(account.id, categories)

            category_map = {str(c["category_id"]): c["category_name"] for c in categories}

            # Get tag rules
            tag_rules = TagRule.query.filter_by(enabled=True).order_by(TagRule.priority).all()

            # Process each stream
            for stream in streams:
                stream_id = str(stream.get("stream_id"))
                channel_name = stream.get("name", "")
                category_id = str(stream.get("category_id", ""))
                category_name = category_map.get(category_id, "")

                # Extract tags for this channel
                tags, cleaned_name = TagService.extract_tags(channel_name, category_name, tag_rules)

                # Check if channel matches filter criteria
                if matches_tag_filter(tags, include_tags, exclude_tags, config.tag_match_mode):
                    matching_channels.append(
                        {
                            "account_id": account.id,
                            "account_name": account.name,
                            "stream_id": stream_id,
                            "original_name": channel_name,
                            "cleaned_name": cleaned_name,
                            "category": category_name,
                            "tags": list(tags),
                            "icon": stream.get("stream_icon", ""),
                        }
                    )

        # Apply pagination
        total = len(matching_channels)
        paginated = matching_channels[offset : offset + limit]

        return jsonify(
            {
                "total": total,
                "offset": offset,
                "limit": limit,
                "showing": len(paginated),
                "channels": paginated,
                "has_more": offset + limit < total,
            }
        )

    except Exception as e:
        logger.error(f"Error previewing playlist config {config_id}: {e}")
        return jsonify({"error": str(e)}), 400


# ============================================================================
# Playlist Generation Routes
# ============================================================================


# TODO: Add test coverage for playlist generation (requires mocking IPTVService)
@app.route("/playlist/<int:account_id>.m3u")
def generate_playlist(account_id):
    """Generate M3U playlist for account with filters applied (using database)"""
    account = Account.query.get_or_404(account_id)

    if not account.enabled:
        return Response("Account is disabled", status=403)

    try:
        # Check if channels are synced to database
        channel_count = Channel.query.filter_by(account_id=account_id, is_active=True).count()
        if channel_count == 0:
            return Response("Account not synced. Please sync channels first.", status=503)
        
        # Get filters
        filters = Filter.query.filter_by(account_id=account_id, enabled=True).all()
        
        # Build base query
        query = db.session.query(Channel).filter(
            Channel.account_id == account_id,
            Channel.is_active == True
        ).join(Category, Channel.category_id == Category.id, isouter=True)
        
        # Apply category filters
        category_whitelist = [f.filter_value for f in filters if f.filter_type == "category" and f.filter_action == "whitelist"]
        category_blacklist = [f.filter_value for f in filters if f.filter_type == "category" and f.filter_action == "blacklist"]
        
        if category_whitelist:
            query = query.filter(Category.category_name.in_(category_whitelist))
        if category_blacklist:
            query = query.filter(~Category.category_name.in_(category_blacklist))
        
        # Apply channel name filters
        for f in filters:
            if f.filter_type == "channel_name":
                if f.filter_action == "whitelist":
                    query = query.filter(Channel.name.ilike(f"%{f.filter_value}%"))
                elif f.filter_action == "blacklist":
                    query = query.filter(~Channel.name.ilike(f"%{f.filter_value}%"))
        
        # Check if we have tag filters
        tag_filters = [f for f in filters if f.filter_type == "tag"]
        if tag_filters:
            # Get tag IDs for filtering
            tag_names = []
            for f in tag_filters:
                if f.filter_action == "whitelist":
                    tag_names.append(f.filter_value)
            
            if tag_names:
                tag_ids = db.session.query(Tag.id).filter(Tag.name.in_(tag_names)).all()
                tag_ids = [t[0] for t in tag_ids]
                
                if tag_ids:
                    # Only include channels that have at least one of the requested tags
                    query = query.join(ChannelTag, Channel.stream_id == ChannelTag.stream_id).filter(
                        ChannelTag.tag_id.in_(tag_ids),
                        ChannelTag.account_id == account_id
                    ).distinct()
        
        # Get all matching channels
        channels = query.order_by(Channel.name).all()

        # Generate M3U
        m3u_lines = ["#EXTM3U"]
        for channel in channels:
            # Use cleaned name (pre-computed during sync)
            display_name = channel.cleaned_name or channel.name
            category_name = channel.category.category_name if channel.category else "Unknown"
            
            tvg_id = channel.epg_channel_id or ""
            tvg_logo = channel.stream_icon or ""

            extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{display_name}" tvg-logo="{tvg_logo}" group-title="{category_name}",{display_name}'
            stream_url = f"http://{account.server}/live/{account.username}/{account.password}/{channel.stream_id}.ts"

            m3u_lines.append(extinf)
            m3u_lines.append(stream_url)

        logger.info(f"Generated playlist for account {account_id}: {len(channels)} channels")
        return Response("\n".join(m3u_lines), mimetype="application/x-mpegurl")

    except Exception as e:
        logger.error(f"Error generating playlist for account {account_id}: {e}")
        return Response(f"Error: {str(e)}", status=500)


# TODO: Add test coverage for config-based playlist generation (requires mocking IPTVService)
@app.route("/playlist/config/<int:config_id>.m3u")
def generate_playlist_from_config(config_id):
    """Generate M3U playlist based on a playlist configuration (tag-based filtering)"""
    config = PlaylistConfig.query.get_or_404(config_id)

    if not config.enabled:
        return Response("Playlist configuration is disabled", status=403)

    try:
        # Parse config
        include_accounts = json.loads(config.include_accounts) if config.include_accounts else []
        exclude_accounts = json.loads(config.exclude_accounts) if config.exclude_accounts else []
        include_tags = json.loads(config.include_tags) if config.include_tags else []
        exclude_tags = json.loads(config.exclude_tags) if config.exclude_tags else []

        # Get accounts to process
        if include_accounts:
            accounts = Account.query.filter(Account.id.in_(include_accounts), Account.enabled.is_(True)).all()
        else:
            accounts = Account.query.filter(Account.enabled.is_(True)).all()
            if exclude_accounts:
                accounts = [a for a in accounts if a.id not in exclude_accounts]

        # Get tag rules
        tag_rules = TagRule.query.filter_by(enabled=True).order_by(TagRule.priority).all()

        # Generate M3U
        m3u_lines = ["#EXTM3U"]
        m3u_lines.append(f"# Playlist: {config.name}")
        if config.description:
            m3u_lines.append(f"# {config.description}")

        total_channels = 0

        for account in accounts:
            # Get streams
            service = IPTVService(account.server, account.username, account.password)
            streams = cache_service.get_cached_streams(account.id)
            if not streams:
                streams = service.get_live_streams()
                cache_service.cache_streams(account.id, streams)

            categories = cache_service.get_cached_categories(account.id)
            if not categories:
                categories = service.get_live_categories()
                cache_service.cache_categories(account.id, categories)

            category_map = {str(c["category_id"]): c["category_name"] for c in categories}

            # Get existing filters for this account
            filters = Filter.query.filter_by(account_id=account.id, enabled=True).all()
            
            # Check if we have any tag filters
            has_tag_filters = any(f.filter_type == "tag" for f in filters)
            stream_tag_map = {}
            
            if has_tag_filters:
                # Load channel tags for this account
                channel_tags_query = db.session.query(
                    ChannelTag.stream_id, Tag.name
                ).join(Tag, ChannelTag.tag_id == Tag.id).filter(
                    ChannelTag.account_id == account.id
                ).all()
                
                for sid, tag_name in channel_tags_query:
                    if sid not in stream_tag_map:
                        stream_tag_map[sid] = []
                    stream_tag_map[sid].append(tag_name)

            # Process each stream
            for stream in streams:
                stream_id = str(stream.get("stream_id"))
                stream_tags = stream_tag_map.get(stream_id, []) if has_tag_filters else None
                
                # First apply account-level filters
                if not apply_filters(stream, category_map, filters, stream_tags):
                    continue

                stream_id = stream.get("stream_id")
                name = stream.get("name", "")
                category_id = str(stream.get("category_id", ""))
                category_name = category_map.get(category_id, "Unknown")

                # Extract tags and clean name
                tags, cleaned_name = TagService.extract_tags(name, category_name, tag_rules)

                # Check if channel matches tag filter
                if not matches_tag_filter(tags, include_tags, exclude_tags, config.tag_match_mode):
                    continue

                # Use cleaned name
                display_name = cleaned_name if cleaned_name else name

                tvg_id = stream.get("epg_channel_id", "")
                tvg_logo = stream.get("stream_icon", "")

                # Add account name to group title for multi-account playlists
                if len(accounts) > 1:
                    group_title = f"{category_name} ({account.name})"
                else:
                    group_title = category_name

                extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{display_name}" tvg-logo="{tvg_logo}" group-title="{group_title}",{display_name}'
                stream_url = f"http://{account.server}/live/{account.username}/{account.password}/{stream_id}.ts"

                m3u_lines.append(extinf)
                m3u_lines.append(stream_url)
                total_channels += 1

        logger.info(
            f"Generated playlist from config {config_id} ({config.name}): {total_channels} channels from {len(accounts)} accounts"
        )
        return Response("\n".join(m3u_lines), mimetype="application/x-mpegurl")

    except Exception as e:
        logger.error(f"Error generating playlist from config {config_id}: {e}")
        return Response(f"Error: {str(e)}", status=500)


# TODO: Add test coverage for EPG XML generation (requires mocking IPTVService)
@app.route("/epg/<int:account_id>.xml")
def proxy_epg(account_id):
    """Proxy EPG/XMLTV for account"""
    account = Account.query.get_or_404(account_id)

    if not account.enabled:
        return Response("Account is disabled", status=403)

    try:
        service = IPTVService(account.server, account.username, account.password)
        epg_data = service.get_xmltv()

        return Response(epg_data, mimetype="application/xml")
    except Exception as e:
        logger.error(f"Error proxying EPG for account {account_id}: {e}")
        return Response(f"Error: {str(e)}", status=500)


# TODO: Add test coverage for channel preview endpoint (requires mocking IPTVService)
@app.route("/api/accounts/<int:account_id>/preview", methods=["GET"])
def preview_playlist(account_id):
    """
    Preview filtered channels (for testing) with pagination support.
    
    Uses local database for fast query performance. Falls back to API if not synced.
    """
    account = Account.query.get_or_404(account_id)
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    tag_filter = request.args.get("tags", "", type=str)  # Comma-separated tag names

    try:
        # Check if channels are synced to database
        channel_count = Channel.query.filter_by(account_id=account_id, is_active=True).count()
        
        if channel_count == 0:
            # No synced channels - fall back to API
            return preview_playlist_from_api(account_id, limit, offset, tag_filter)
        
        # Use database for fast queries
        return preview_playlist_from_db(account_id, limit, offset, tag_filter)

    except Exception as e:
        logger.error(f"Error previewing playlist for account {account_id}: {e}")
        return jsonify({"error": str(e)}), 500


def preview_playlist_from_db(account_id, limit, offset, tag_filter):
    """Preview channels using database (fast path)"""
    account = Account.query.get_or_404(account_id)
    
    # Parse tag filter
    filter_tags = []
    if tag_filter:
        filter_tags = [t.strip().upper() for t in tag_filter.split(",") if t.strip()]
    
    # Get filters
    filters = Filter.query.filter_by(account_id=account_id, enabled=True).all()
    
    # Build base query
    query = db.session.query(Channel).filter(
        Channel.account_id == account_id,
        Channel.is_active == True
    ).join(Category, Channel.category_id == Category.id, isouter=True)
    
    # Apply category filters
    category_whitelist = [f.filter_value for f in filters if f.filter_type == "category" and f.filter_action == "whitelist"]
    category_blacklist = [f.filter_value for f in filters if f.filter_type == "category" and f.filter_action == "blacklist"]
    
    if category_whitelist:
        query = query.filter(Category.category_name.in_(category_whitelist))
    if category_blacklist:
        query = query.filter(~Category.category_name.in_(category_blacklist))
    
    # Apply channel name filters
    for f in filters:
        if f.filter_type == "channel_name":
            if f.filter_action == "whitelist":
                query = query.filter(Channel.name.ilike(f"%{f.filter_value}%"))
            elif f.filter_action == "blacklist":
                query = query.filter(~Channel.name.ilike(f"%{f.filter_value}%"))
        elif f.filter_type == "regex":
            # Note: SQLite doesn't have good regex support, may need to filter in Python
            pass
    
    # Apply tag filters
    if filter_tags:
        # Get tag IDs
        tag_ids = db.session.query(Tag.id).filter(
            Tag.name.in_([t for t in filter_tags])
        ).all()
        tag_ids = [t[0] for t in tag_ids]
        
        if tag_ids:
            # Only include channels that have at least one of the requested tags
            query = query.join(ChannelTag, Channel.stream_id == ChannelTag.stream_id).filter(
                ChannelTag.tag_id.in_(tag_ids),
                ChannelTag.account_id == account_id
            ).distinct()
    
    # Get total count (before pagination)
    total = query.count()
    
    # Apply pagination
    channels = query.order_by(Channel.name).offset(offset).limit(limit).all()
    
    # Load tags for these channels
    stream_ids = [ch.stream_id for ch in channels]
    channel_tags_query = db.session.query(
        ChannelTag.stream_id, Tag.name
    ).join(Tag, ChannelTag.tag_id == Tag.id).filter(
        ChannelTag.account_id == account_id,
        ChannelTag.stream_id.in_(stream_ids)
    ).all()
    
    stream_tag_map = {}
    for stream_id, tag_name in channel_tags_query:
        if stream_id not in stream_tag_map:
            stream_tag_map[stream_id] = []
        stream_tag_map[stream_id].append(tag_name)
    
    # Build results
    results = []
    for channel in channels:
        category_name = channel.category.category_name if channel.category else "Unknown"
        
        # Use stored cleaned name (computed during sync or tag processing)
        cleaned_name = channel.cleaned_name or channel.name
        
        results.append({
            "id": channel.stream_id,
            "name": channel.name,
            "cleaned_name": cleaned_name,
            "category": category_name,
            "icon": channel.stream_icon or "",
            "tags": stream_tag_map.get(channel.stream_id, []),
        })
    
    return jsonify({
        "total": total,
        "channels": results,
        "using_database": True
    })


def preview_playlist_from_api(account_id, limit, offset, tag_filter):
    """Preview channels using IPTV API (fallback when database not synced)"""
    try:
        account = Account.query.get_or_404(account_id)
        
        # Parse tag filter
        filter_tags = []
        if tag_filter:
            filter_tags = [t.strip().upper() for t in tag_filter.split(",") if t.strip()]
        
        service = IPTVService(account.server, account.username, account.password)
        streams = cache_service.get_cached_streams(account_id)
        if not streams:
            streams = service.get_live_streams()
            cache_service.cache_streams(account_id, streams)

        categories = cache_service.get_cached_categories(account_id)
        if not categories:
            categories = service.get_live_categories()
            cache_service.cache_categories(account_id, categories)

        category_map = {str(c["category_id"]): c["category_name"] for c in categories}

        # Get filters
        filters = Filter.query.filter_by(account_id=account_id, enabled=True).all()

        # Get tag rules for name cleaning
        tag_rules = TagService.get_rules_for_account(account)

        # First pass: collect stream IDs that pass filters
        candidate_stream_ids = []
        
        for stream in streams:
            if apply_filters(stream, category_map, filters):
                stream_id = str(stream.get("stream_id"))
                
                # If we have enough candidates for this page, stop collecting
                if len(candidate_stream_ids) >= offset + limit:
                    candidate_stream_ids.append(stream_id)
                    break
                    
                candidate_stream_ids.append(stream_id)

        # Only load tags for candidate streams
        stream_tag_map = {}
        if candidate_stream_ids:
            # Load tags in batches
            batch_size = 500
            for i in range(0, len(candidate_stream_ids), batch_size):
                batch = candidate_stream_ids[i:i + batch_size]
                channel_tags_query = db.session.query(
                    ChannelTag.stream_id, Tag.name
                ).join(Tag, ChannelTag.tag_id == Tag.id).filter(
                    ChannelTag.account_id == account_id,
                    ChannelTag.stream_id.in_(batch)
                ).all()
                
                for stream_id, tag_name in channel_tags_query:
                    if stream_id not in stream_tag_map:
                        stream_tag_map[stream_id] = []
                    stream_tag_map[stream_id].append(tag_name)

        # Second pass: apply tag filters and build final results
        filtered_streams = []
        skipped = 0

        for stream in streams:
            if apply_filters(stream, category_map, filters):
                stream_id = str(stream.get("stream_id"))
                channel_tags = stream_tag_map.get(stream_id, [])
                
                # Apply tag filter if specified
                if filter_tags:
                    channel_tags_upper = [t.upper() for t in channel_tags]
                    if not any(ft in channel_tags_upper for ft in filter_tags):
                        continue
                
                # Skip items before offset
                if skipped < offset:
                    skipped += 1
                    continue

                # Extract cleaned name
                channel_name = stream.get("name", "")
                category_id = str(stream.get("category_id", ""))
                category_name = category_map.get(category_id, "Unknown")
                _, cleaned_name = TagService.extract_tags(channel_name, category_name, tag_rules)

                filtered_streams.append({
                    "id": stream.get("stream_id"),
                    "name": stream.get("name"),
                    "cleaned_name": cleaned_name,
                    "category": category_name,
                    "icon": stream.get("stream_icon", ""),
                    "tags": channel_tags,
                })

                # Stop when we have enough items
                if len(filtered_streams) >= limit:
                    break

        # Calculate total (only when offset is 0)
        if offset == 0:
            total = 0
            for s in streams:
                if apply_filters(s, category_map, filters):
                    # If tag filter specified, need to check tags
                    if filter_tags:
                        stream_id = str(s.get("stream_id"))
                        channel_tags = stream_tag_map.get(stream_id, [])
                        channel_tags_upper = [t.upper() for t in channel_tags]
                        if not any(ft in channel_tags_upper for ft in filter_tags):
                            continue
                    total += 1
        else:
            total = -1

        return jsonify({
            "total": total,
            "offset": offset,
            "limit": limit,
            "showing": len(filtered_streams),
            "channels": filtered_streams,
            "has_more": len(filtered_streams) == limit,
            "using_database": False
        })
    except Exception as e:
        logger.error(f"Error previewing for account {account_id}: {e}")
        return jsonify({"error": str(e)}), 400


@app.route("/api/channels/preview", methods=["GET"])
def preview_channels_cross_account():
    """Preview channels across all accounts with tag filtering
    
    Query parameters:
    - tags: Comma-separated list of tags to filter by
    - account_ids: Optional comma-separated list of account IDs to limit search
    - offset: Pagination offset (default 0)
    - limit: Results per page (default 100)
    - search: Optional search term for channel name
    """
    # Parse query parameters
    tags_param = request.args.get("tags", "")
    account_ids_param = request.args.get("account_ids", "")
    offset = request.args.get("offset", 0, type=int)
    limit = min(request.args.get("limit", 100, type=int), 500)  # Max 500
    search_term = request.args.get("search", "").strip()
    
    tags = [t.strip() for t in tags_param.split(",") if t.strip()]
    account_ids = [int(a.strip()) for a in account_ids_param.split(",") if a.strip()] if account_ids_param else None
    
    try:
        # Build base query for channels
        query = db.session.query(Channel).filter(Channel.is_active == True)
        
        # Filter by account IDs if specified
        if account_ids:
            query = query.filter(Channel.account_id.in_(account_ids))
        
        # Filter by tags if specified
        if tags:
            # Join with ChannelTag and Tag for each tag
            for tag in tags:
                tag_obj = Tag.query.filter(Tag.name.ilike(tag)).first()
                if tag_obj:
                    query = query.join(
                        ChannelTag, 
                        db.and_(
                            ChannelTag.account_id == Channel.account_id,
                            ChannelTag.stream_id == Channel.stream_id,
                            ChannelTag.tag_id == tag_obj.id
                        )
                    )
        
        # Filter by search term if specified
        if search_term:
            query = query.filter(Channel.name.ilike(f"%{search_term}%"))
        
        # Get total count
        total = query.distinct().count()
        
        # Apply pagination
        channels = query.distinct().order_by(Channel.name).offset(offset).limit(limit).all()
        
        # Load tags for these channels
        channel_keys = [(c.account_id, c.stream_id) for c in channels]
        channel_tags_query = (
            db.session.query(ChannelTag.account_id, ChannelTag.stream_id, Tag.name)
            .join(Tag, ChannelTag.tag_id == Tag.id)
        )
        
        # Build OR conditions for each (account_id, stream_id) pair
        if channel_keys:
            conditions = []
            for account_id, stream_id in channel_keys:
                conditions.append(
                    db.and_(
                        ChannelTag.account_id == account_id,
                        ChannelTag.stream_id == stream_id
                    )
                )
            channel_tags_query = channel_tags_query.filter(db.or_(*conditions))
        
        channel_tags_data = channel_tags_query.all()
        
        # Build tag map
        tag_map = {}
        for account_id, stream_id, tag_name in channel_tags_data:
            key = (account_id, stream_id)
            if key not in tag_map:
                tag_map[key] = []
            tag_map[key].append(tag_name)
        
        # Load account names
        account_map = {}
        if channels:
            account_ids_used = list(set(c.account_id for c in channels))
            accounts = Account.query.filter(Account.id.in_(account_ids_used)).all()
            account_map = {a.id: a.name for a in accounts}
        
        # Format results
        results = []
        for channel in channels:
            key = (channel.account_id, channel.stream_id)
            results.append({
                "stream_id": channel.stream_id,
                "name": channel.name,
                "cleaned_name": channel.cleaned_name or channel.name,
                "category_name": channel.category.name if channel.category else "",
                "account_id": channel.account_id,
                "account_name": account_map.get(channel.account_id, "Unknown"),
                "tags": sorted(tag_map.get(key, []))
            })
        
        return jsonify({
            "success": True,
            "total": total,
            "offset": offset,
            "limit": limit,
            "showing": len(results),
            "channels": results,
            "has_more": offset + limit < total,
            "using_database": True
        })
        
    except Exception as e:
        logger.error(f"Error previewing cross-account channels: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


# ============================================================================
# Helper Functions
# ============================================================================


def matches_tag_filter(channel_tags, include_tags, exclude_tags, match_mode="any"):
    """
    Check if channel tags match the filter criteria.

    Args:
        channel_tags: Set of tag names for the channel
        include_tags: List of tags to include (empty = all)
        exclude_tags: List of tags to exclude
        match_mode: 'any' (at least one include tag) or 'all' (all include tags)

    Returns:
        True if channel matches filter, False otherwise
    """
    # First check exclude tags - if any match, exclude the channel
    if exclude_tags:
        for exclude_tag in exclude_tags:
            if exclude_tag.upper() in [t.upper() for t in channel_tags]:
                return False

    # If no include tags specified, include everything (that wasn't excluded)
    if not include_tags:
        return True

    # Check include tags based on match mode
    normalized_channel_tags = {t.upper() for t in channel_tags}
    normalized_include_tags = [t.upper() for t in include_tags]

    if match_mode == "all":
        # Must have ALL include tags
        return all(tag in normalized_channel_tags for tag in normalized_include_tags)
    else:  # 'any'
        # Must have AT LEAST ONE include tag
        return any(tag in normalized_channel_tags for tag in normalized_include_tags)


def apply_filters(stream, category_map, filters, stream_tags=None):
    """
    Apply all filters to a stream
    
    Args:
        stream: The stream dict to check
        category_map: Map of category_id to category_name
        filters: List of Filter objects to apply
        stream_tags: Optional list of tag names for this stream (for tag filtering)
    
    Returns:
        True if stream passes all filters, False otherwise
    """
    name = stream.get("name", "").upper()
    category_id = str(stream.get("category_id", ""))
    category_name = category_map.get(category_id, "").upper()

    for f in filters:
        filter_value = f.filter_value.upper()

        if f.filter_type == "category":
            # Check if category matches
            if f.filter_action == "whitelist":
                if filter_value not in category_name:
                    return False
            elif f.filter_action == "blacklist":
                if filter_value in category_name:
                    return False

        elif f.filter_type == "channel_name":
            # Check if channel name matches
            if f.filter_action == "whitelist":
                if filter_value not in name:
                    return False
            elif f.filter_action == "blacklist":
                if filter_value in name:
                    return False

        elif f.filter_type == "regex":
            import re

            try:
                pattern = re.compile(f.filter_value, re.IGNORECASE)
                if f.filter_action == "whitelist":
                    if not pattern.search(name):
                        return False
                elif f.filter_action == "blacklist":
                    if pattern.search(name):
                        return False
            except re.error:
                logger.warning(f"Invalid regex pattern in filter {f.id}: {f.filter_value}")
        
        elif f.filter_type == "tag":
            # Tag-based filtering
            # filter_value contains comma-separated tag names
            filter_tags = [t.strip().upper() for t in f.filter_value.split(",") if t.strip()]
            
            if stream_tags is None:
                # If no tags provided, can't apply tag filter - skip it
                logger.warning(f"Tag filter {f.id} cannot be applied - no tag data provided")
                continue
            
            stream_tags_upper = [t.upper() for t in stream_tags]
            
            if f.filter_action == "whitelist":
                # Must have at least one of the specified tags
                if not any(tag in stream_tags_upper for tag in filter_tags):
                    return False
            elif f.filter_action == "blacklist":
                # Must not have any of the specified tags
                if any(tag in stream_tags_upper for tag in filter_tags):
                    return False

    return True


# TODO: Add test coverage for cache management endpoints
@app.route("/api/cache/clear", methods=["POST"])
def clear_all_cache():
    """Clear all caches"""
    cache_service.clear_all()
    return jsonify({"success": True})


@app.route("/api/cache/clear/<int:account_id>", methods=["POST"])
def clear_account_cache_route(account_id):
    """Clear cache for specific account"""
    cache_service.clear_account_cache(account_id)
    return jsonify({"success": True})


# ============================================================================
# Initialization
# ============================================================================


@app.cli.command()
def init_db():
    """Initialize the database"""
    db.create_all()
    print("Database initialized!")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    # Start the sync scheduler
    sync_scheduler.start()

    port = int(os.getenv("PORT", 8000))
    debug = os.getenv("DEBUG", "False").lower() == "true"

    logger.info(f"Starting IPTV Proxy v2 on port {port}")
    logger.info(f"Sync scheduler running (interval: {sync_interval} hours)")
    
    try:
        app.run(host="0.0.0.0", port=port, debug=debug)
    finally:
        # Stop scheduler on shutdown
        sync_scheduler.stop()
