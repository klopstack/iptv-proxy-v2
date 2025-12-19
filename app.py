#!/usr/bin/env python3
"""
IPTV M3U Proxy v2 - Web UI for managing multiple IPTV services with filtering
"""

import os
import json
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
import logging

from models import db, Account, Filter, TagRule, Tag, ChannelTag, PlaylistConfig, RuleSet, AccountRuleSet
from services.iptv_service import IPTVService
from services.cache_service import CacheService
from services.tag_service import TagService

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:////app/data/iptv_proxy.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize extensions
CORS(app)
db.init_app(app)

# Initialize services
cache_service = CacheService()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Web UI Routes
# ============================================================================

@app.route('/')
def index():
    """Main dashboard"""
    return render_template('index.html')


@app.route('/accounts')
def accounts_page():
    """Accounts management page"""
    return render_template('accounts.html')


@app.route('/filters')
def filters_page():
    """Filters management page"""
    return render_template('filters.html')


@app.route('/test')
def test_page():
    """Test and preview page"""
    return render_template('test.html')


@app.route('/rulesets')
def rulesets_page():
    """Rulesets and tags management page"""
    return render_template('rulesets.html')


# ============================================================================
# API Routes - Accounts
# ============================================================================

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get all accounts"""
    accounts = Account.query.all()
    return jsonify([{
        'id': a.id,
        'name': a.name,
        'server': a.server,
        'username': a.username,
        'enabled': a.enabled
    } for a in accounts])


@app.route('/api/accounts', methods=['POST'])
def create_account():
    """Create new account"""
    data = request.json
    
    account = Account(
        name=data['name'],
        server=data['server'],
        username=data['username'],
        password=data['password'],
        enabled=data.get('enabled', True)
    )
    
    db.session.add(account)
    db.session.commit()
    
    return jsonify({
        'id': account.id,
        'name': account.name,
        'server': account.server,
        'username': account.username,
        'enabled': account.enabled
    }), 201


@app.route('/api/accounts/<int:account_id>', methods=['PUT'])
def update_account(account_id):
    """Update account"""
    account = Account.query.get_or_404(account_id)
    data = request.json
    
    account.name = data.get('name', account.name)
    account.server = data.get('server', account.server)
    account.username = data.get('username', account.username)
    if 'password' in data:
        account.password = data['password']
    account.enabled = data.get('enabled', account.enabled)
    
    db.session.commit()
    
    # Clear cache for this account
    cache_service.clear_account_cache(account_id)
    
    return jsonify({
        'id': account.id,
        'name': account.name,
        'server': account.server,
        'username': account.username,
        'enabled': account.enabled
    })


@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
def delete_account(account_id):
    """Delete account"""
    account = Account.query.get_or_404(account_id)
    
    # Delete associated filters
    Filter.query.filter_by(account_id=account_id).delete()
    
    db.session.delete(account)
    db.session.commit()
    
    # Clear cache
    cache_service.clear_account_cache(account_id)
    
    return '', 204


@app.route('/api/accounts/<int:account_id>/test', methods=['POST'])
def test_account(account_id):
    """Test account connection"""
    account = Account.query.get_or_404(account_id)
    
    try:
        service = IPTVService(account.server, account.username, account.password)
        auth_info = service.authenticate()
        
        return jsonify({
            'success': True,
            'server_info': {
                'url': auth_info.get('server_info', {}).get('url', ''),
                'time': auth_info.get('server_info', {}).get('time_now', ''),
            },
            'user_info': {
                'username': auth_info.get('user_info', {}).get('username', ''),
                'status': auth_info.get('user_info', {}).get('status', ''),
                'exp_date': auth_info.get('user_info', {}).get('exp_date', ''),
                'max_connections': auth_info.get('user_info', {}).get('max_connections', ''),
            }
        })
    except Exception as e:
        logger.error(f"Error testing account {account_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


@app.route('/api/accounts/<int:account_id>/categories', methods=['GET'])
def get_account_categories(account_id):
    """Get categories for account"""
    account = Account.query.get_or_404(account_id)
    
    try:
        service = IPTVService(account.server, account.username, account.password)
        categories = service.get_live_categories()
        
        # Cache it
        cache_service.cache_categories(account_id, categories)
        
        return jsonify(categories)
    except Exception as e:
        logger.error(f"Error fetching categories for account {account_id}: {e}")
        return jsonify({'error': str(e)}), 400


@app.route('/api/accounts/<int:account_id>/stats', methods=['GET'])
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
        
        # Count by category
        category_counts = {}
        for stream in streams:
            cat_id = str(stream.get('category_id', 'Unknown'))
            category_counts[cat_id] = category_counts.get(cat_id, 0) + 1
        
        return jsonify({
            'total_channels': len(streams),
            'total_categories': len(categories),
            'category_counts': category_counts
        })
    except Exception as e:
        logger.error(f"Error fetching stats for account {account_id}: {e}")
        return jsonify({'error': str(e)}), 400


# ============================================================================
# API Routes - Filters
# ============================================================================

@app.route('/api/filters', methods=['GET'])
def get_filters():
    """Get all filters"""
    filters = Filter.query.all()
    return jsonify([{
        'id': f.id,
        'account_id': f.account_id,
        'name': f.name,
        'filter_type': f.filter_type,
        'filter_action': f.filter_action,
        'filter_value': f.filter_value,
        'enabled': f.enabled
    } for f in filters])


@app.route('/api/filters', methods=['POST'])
def create_filter():
    """Create new filter"""
    data = request.json
    
    filter_obj = Filter(
        account_id=data['account_id'],
        name=data['name'],
        filter_type=data['filter_type'],
        filter_action=data['filter_action'],
        filter_value=data['filter_value'],
        enabled=data.get('enabled', True)
    )
    
    db.session.add(filter_obj)
    db.session.commit()
    
    # Clear cache for this account
    cache_service.clear_account_cache(data['account_id'])
    
    return jsonify({
        'id': filter_obj.id,
        'account_id': filter_obj.account_id,
        'name': filter_obj.name,
        'filter_type': filter_obj.filter_type,
        'filter_action': filter_obj.filter_action,
        'filter_value': filter_obj.filter_value,
        'enabled': filter_obj.enabled
    }), 201


@app.route('/api/filters/<int:filter_id>', methods=['PUT'])
def update_filter(filter_id):
    """Update filter"""
    filter_obj = Filter.query.get_or_404(filter_id)
    data = request.json
    
    filter_obj.name = data.get('name', filter_obj.name)
    filter_obj.filter_type = data.get('filter_type', filter_obj.filter_type)
    filter_obj.filter_action = data.get('filter_action', filter_obj.filter_action)
    filter_obj.filter_value = data.get('filter_value', filter_obj.filter_value)
    filter_obj.enabled = data.get('enabled', filter_obj.enabled)
    
    db.session.commit()
    
    # Clear cache
    cache_service.clear_account_cache(filter_obj.account_id)
    
    return jsonify({
        'id': filter_obj.id,
        'account_id': filter_obj.account_id,
        'name': filter_obj.name,
        'filter_type': filter_obj.filter_type,
        'filter_action': filter_obj.filter_action,
        'filter_value': filter_obj.filter_value,
        'enabled': filter_obj.enabled
    })


@app.route('/api/filters/<int:filter_id>', methods=['DELETE'])
def delete_filter(filter_id):
    """Delete filter"""
    filter_obj = Filter.query.get_or_404(filter_id)
    account_id = filter_obj.account_id
    
    db.session.delete(filter_obj)
    db.session.commit()
    
    # Clear cache
    cache_service.clear_account_cache(account_id)
    
    return '', 204


@app.route('/api/accounts/<int:account_id>/filters', methods=['GET'])
def get_account_filters(account_id):
    """Get filters for specific account"""
    filters = Filter.query.filter_by(account_id=account_id).all()
    return jsonify([{
        'id': f.id,
        'name': f.name,
        'filter_type': f.filter_type,
        'filter_action': f.filter_action,
        'filter_value': f.filter_value,
        'enabled': f.enabled
    } for f in filters])


# ============================================================================
# API Routes - Rule Sets
# ============================================================================

@app.route('/api/rulesets', methods=['GET'])
def get_rulesets():
    """Get all rulesets"""
    rulesets = RuleSet.query.order_by(RuleSet.priority, RuleSet.name).all()
    return jsonify([{
        'id': rs.id,
        'name': rs.name,
        'description': rs.description,
        'is_default': rs.is_default,
        'enabled': rs.enabled,
        'priority': rs.priority,
        'rule_count': len(rs.rules)
    } for rs in rulesets])


@app.route('/api/rulesets', methods=['POST'])
def create_ruleset():
    """Create new ruleset"""
    data = request.json
    
    ruleset = RuleSet(
        name=data['name'],
        description=data.get('description', ''),
        is_default=data.get('is_default', False),
        enabled=data.get('enabled', True),
        priority=data.get('priority', 100)
    )
    
    db.session.add(ruleset)
    db.session.commit()
    
    return jsonify({
        'id': ruleset.id,
        'name': ruleset.name,
        'description': ruleset.description,
        'is_default': ruleset.is_default,
        'enabled': ruleset.enabled,
        'priority': ruleset.priority,
        'rule_count': 0
    }), 201


@app.route('/api/rulesets/<int:ruleset_id>', methods=['PUT'])
def update_ruleset(ruleset_id):
    """Update ruleset"""
    ruleset = RuleSet.query.get_or_404(ruleset_id)
    data = request.json
    
    ruleset.name = data.get('name', ruleset.name)
    ruleset.description = data.get('description', ruleset.description)
    ruleset.is_default = data.get('is_default', ruleset.is_default)
    ruleset.enabled = data.get('enabled', ruleset.enabled)
    ruleset.priority = data.get('priority', ruleset.priority)
    
    db.session.commit()
    cache_service.clear_all()
    
    return jsonify({
        'id': ruleset.id,
        'name': ruleset.name,
        'description': ruleset.description,
        'is_default': ruleset.is_default,
        'enabled': ruleset.enabled,
        'priority': ruleset.priority,
        'rule_count': len(ruleset.rules)
    })


@app.route('/api/rulesets/<int:ruleset_id>', methods=['DELETE'])
def delete_ruleset(ruleset_id):
    """Delete ruleset"""
    ruleset = RuleSet.query.get_or_404(ruleset_id)
    
    # Remove associations with accounts
    AccountRuleSet.query.filter_by(ruleset_id=ruleset_id).delete()
    
    db.session.delete(ruleset)
    db.session.commit()
    cache_service.clear_all()
    
    return '', 204


@app.route('/api/rulesets/create-default', methods=['POST'])
def create_default_ruleset():
    """Create default ruleset with common IPTV tag extraction rules"""
    try:
        ruleset = TagService.create_default_ruleset(db.session)
        cache_service.clear_all()
        
        return jsonify({
            'success': True,
            'id': ruleset.id,
            'name': ruleset.name,
            'rule_count': len(ruleset.rules),
            'message': f'Created default ruleset with {len(ruleset.rules)} rules'
        })
    except Exception as e:
        logger.error(f"Error creating default ruleset: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


@app.route('/api/rulesets/<int:ruleset_id>/rules', methods=['GET'])
def get_ruleset_rules(ruleset_id):
    """Get all rules for a specific ruleset"""
    ruleset = RuleSet.query.get_or_404(ruleset_id)
    rules = TagRule.query.filter_by(ruleset_id=ruleset_id).order_by(TagRule.priority, TagRule.id).all()
    
    return jsonify([{
        'id': r.id,
        'name': r.name,
        'pattern': r.pattern,
        'pattern_type': r.pattern_type,
        'tag_name': r.tag_name,
        'source': r.source,
        'remove_from_name': r.remove_from_name,
        'priority': r.priority,
        'enabled': r.enabled
    } for r in rules])


# ============================================================================
# API Routes - Account Rulesets
# ============================================================================

@app.route('/api/accounts/<int:account_id>/rulesets', methods=['GET'])
def get_account_rulesets(account_id):
    """Get rulesets assigned to an account"""
    account = Account.query.get_or_404(account_id)
    
    assignments = db.session.query(RuleSet, AccountRuleSet.priority).join(
        AccountRuleSet, RuleSet.id == AccountRuleSet.ruleset_id
    ).filter(
        AccountRuleSet.account_id == account_id
    ).order_by(AccountRuleSet.priority).all()
    
    return jsonify([{
        'id': rs.id,
        'name': rs.name,
        'description': rs.description,
        'is_default': rs.is_default,
        'enabled': rs.enabled,
        'priority': priority,
        'rule_count': len(rs.rules)
    } for rs, priority in assignments])


@app.route('/api/accounts/<int:account_id>/rulesets', methods=['POST'])
def assign_ruleset_to_account(account_id):
    """Assign a ruleset to an account"""
    account = Account.query.get_or_404(account_id)
    data = request.json
    
    ruleset_id = data['ruleset_id']
    priority = data.get('priority', 100)
    
    # Check if already assigned
    existing = AccountRuleSet.query.filter_by(
        account_id=account_id,
        ruleset_id=ruleset_id
    ).first()
    
    if existing:
        # Update priority
        existing.priority = priority
    else:
        # Create new assignment
        assignment = AccountRuleSet(
            account_id=account_id,
            ruleset_id=ruleset_id,
            priority=priority
        )
        db.session.add(assignment)
    
    db.session.commit()
    cache_service.clear_account_cache(account_id)
    
    return jsonify({'success': True}), 201


@app.route('/api/accounts/<int:account_id>/rulesets/<int:ruleset_id>', methods=['DELETE'])
def remove_ruleset_from_account(account_id, ruleset_id):
    """Remove a ruleset assignment from an account"""
    account = Account.query.get_or_404(account_id)
    
    AccountRuleSet.query.filter_by(
        account_id=account_id,
        ruleset_id=ruleset_id
    ).delete()
    
    db.session.commit()
    cache_service.clear_account_cache(account_id)
    
    return '', 204


# ============================================================================
# API Routes - Tag Rules
# ============================================================================

@app.route('/api/tag-rules', methods=['GET'])
def get_tag_rules():
    """Get all tag extraction rules (optionally filtered by ruleset)"""
    ruleset_id = request.args.get('ruleset_id', type=int)
    
    query = TagRule.query
    if ruleset_id:
        query = query.filter_by(ruleset_id=ruleset_id)
    
    rules = query.order_by(TagRule.priority, TagRule.id).all()
    return jsonify([{
        'id': r.id,
        'ruleset_id': r.ruleset_id,
        'name': r.name,
        'pattern': r.pattern,
        'pattern_type': r.pattern_type,
        'tag_name': r.tag_name,
        'source': r.source,
        'remove_from_name': r.remove_from_name,
        'priority': r.priority,
        'enabled': r.enabled
    } for r in rules])


@app.route('/api/tag-rules', methods=['POST'])
def create_tag_rule():
    """Create new tag extraction rule"""
    data = request.json
    
    # Verify ruleset exists
    ruleset_id = data.get('ruleset_id')
    if not ruleset_id:
        return jsonify({'error': 'ruleset_id is required'}), 400
    
    ruleset = RuleSet.query.get(ruleset_id)
    if not ruleset:
        return jsonify({'error': f'RuleSet {ruleset_id} not found'}), 404
    
    rule = TagRule(
        name=data['name'],
        pattern=data['pattern'],
        pattern_type=data['pattern_type'],
        tag_name=data['tag_name'],
        source=data['source'],
        ruleset_id=ruleset_id,
        remove_from_name=data.get('remove_from_name', True),
        priority=data.get('priority', 100),
        enabled=data.get('enabled', True)
    )
    
    db.session.add(rule)
    db.session.commit()
    
    # Clear all account caches since tags affect all channels
    cache_service.clear_all()
    
    return jsonify({
        'id': rule.id,
        'name': rule.name,
        'pattern': rule.pattern,
        'pattern_type': rule.pattern_type,
        'tag_name': rule.tag_name,
        'source': rule.source,
        'remove_from_name': rule.remove_from_name,
        'priority': rule.priority,
        'enabled': rule.enabled
    }), 201


@app.route('/api/tag-rules/<int:rule_id>', methods=['PUT'])
def update_tag_rule(rule_id):
    """Update tag extraction rule"""
    rule = TagRule.query.get_or_404(rule_id)
    data = request.json
    
    rule.name = data.get('name', rule.name)
    rule.pattern = data.get('pattern', rule.pattern)
    rule.pattern_type = data.get('pattern_type', rule.pattern_type)
    rule.tag_name = data.get('tag_name', rule.tag_name)
    rule.source = data.get('source', rule.source)
    rule.remove_from_name = data.get('remove_from_name', rule.remove_from_name)
    rule.priority = data.get('priority', rule.priority)
    rule.enabled = data.get('enabled', rule.enabled)
    
    db.session.commit()
    cache_service.clear_all()
    
    return jsonify({
        'id': rule.id,
        'name': rule.name,
        'pattern': rule.pattern,
        'pattern_type': rule.pattern_type,
        'tag_name': rule.tag_name,
        'source': rule.source,
        'remove_from_name': rule.remove_from_name,
        'priority': rule.priority,
        'enabled': rule.enabled
    })


@app.route('/api/tag-rules/<int:rule_id>', methods=['DELETE'])
def delete_tag_rule(rule_id):
    """Delete tag extraction rule"""
    rule = TagRule.query.get_or_404(rule_id)
    
    db.session.delete(rule)
    db.session.commit()
    cache_service.clear_all()
    
    return '', 204


@app.route('/api/tag-rules/create-defaults', methods=['POST'])
def create_default_tag_rules():
    """Create default tag extraction ruleset"""
    try:
        ruleset = TagService.create_default_ruleset(db.session)
        cache_service.clear_all()
        
        return jsonify({
            'success': True,
            'ruleset_id': ruleset.id,
            'ruleset_name': ruleset.name,
            'count': len(ruleset.rules),
            'message': f'Created default ruleset with {len(ruleset.rules)} rules'
        })
    except Exception as e:
        logger.error(f"Error creating default ruleset: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


@app.route('/api/tags', methods=['GET'])
def get_tags():
    """Get all tags"""
    tags = Tag.query.order_by(Tag.name).all()
    return jsonify([{
        'id': t.id,
        'name': t.name,
        'created_at': t.created_at.isoformat()
    } for t in tags])


@app.route('/api/accounts/<int:account_id>/process-tags', methods=['POST'])
def process_account_tags(account_id):
    """Process and extract tags for all channels in an account"""
    account = Account.query.get_or_404(account_id)
    
    try:
        # Get streams
        service = IPTVService(account.server, account.username, account.password)
        streams = cache_service.get_cached_streams(account_id)
        if not streams:
            streams = service.get_live_streams()
            cache_service.cache_streams(account_id, streams)
        
        categories = cache_service.get_cached_categories(account_id)
        if not categories:
            categories = service.get_live_categories()
            cache_service.cache_categories(account_id, categories)
        
        # Build category map
        category_map = {str(c['category_id']): c['category_name'] for c in categories}
        
        # Get tag rules for this account (account-specific rulesets or defaults)
        tag_rules = TagService.get_rules_for_account(db.session, account)
        
        # Clear existing channel tags for this account
        ChannelTag.query.filter_by(account_id=account_id).delete()
        
        # Process each stream
        processed_count = 0
        tag_counts = {}
        
        for stream in streams:
            stream_id = str(stream.get('stream_id'))
            channel_name = stream.get('name', '')
            category_id = str(stream.get('category_id', ''))
            category_name = category_map.get(category_id, '')
            
            # Extract tags
            tags, cleaned_name = TagService.extract_tags(channel_name, category_name, tag_rules)
            
            # Store tags
            for tag_name in tags:
                # Normalize tag name
                normalized_tag = TagService.normalize_tag_name(tag_name)
                
                # Get or create tag
                tag = Tag.query.filter_by(name=normalized_tag).first()
                if not tag:
                    tag = Tag(name=normalized_tag)
                    db.session.add(tag)
                    db.session.flush()  # Get the ID
                
                # Create channel tag association
                channel_tag = ChannelTag(
                    account_id=account_id,
                    stream_id=stream_id,
                    tag_id=tag.id
                )
                db.session.add(channel_tag)
                
                # Count tags
                tag_counts[normalized_tag] = tag_counts.get(normalized_tag, 0) + 1
            
            processed_count += 1
        
        db.session.commit()
        
        logger.info(f"Processed tags for {processed_count} channels in account {account_id}")
        
        return jsonify({
            'success': True,
            'processed': processed_count,
            'unique_tags': len(tag_counts),
            'tag_counts': tag_counts
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error processing tags for account {account_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


@app.route('/api/accounts/<int:account_id>/tags', methods=['GET'])
def get_account_tags(account_id):
    """Get all tags used in an account with channel counts"""
    account = Account.query.get_or_404(account_id)
    
    # Query tags for this account with counts
    from sqlalchemy import func
    
    results = db.session.query(
        Tag.id,
        Tag.name,
        func.count(ChannelTag.id).label('channel_count')
    ).join(
        ChannelTag, Tag.id == ChannelTag.tag_id
    ).filter(
        ChannelTag.account_id == account_id
    ).group_by(
        Tag.id, Tag.name
    ).order_by(
        Tag.name
    ).all()
    
    return jsonify([{
        'id': r.id,
        'name': r.name,
        'channel_count': r.channel_count
    } for r in results])


# ============================================================================
# API Routes - Playlist Configurations
# ============================================================================

@app.route('/api/playlist-configs', methods=['GET'])
def get_playlist_configs():
    """Get all playlist configurations"""
    configs = PlaylistConfig.query.all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'description': c.description,
        'include_accounts': json.loads(c.include_accounts) if c.include_accounts else [],
        'exclude_accounts': json.loads(c.exclude_accounts) if c.exclude_accounts else [],
        'include_tags': json.loads(c.include_tags) if c.include_tags else [],
        'exclude_tags': json.loads(c.exclude_tags) if c.exclude_tags else [],
        'tag_match_mode': c.tag_match_mode,
        'enabled': c.enabled
    } for c in configs])


@app.route('/api/playlist-configs', methods=['POST'])
def create_playlist_config():
    """Create new playlist configuration"""
    data = request.json
    
    config = PlaylistConfig(
        name=data['name'],
        description=data.get('description', ''),
        include_accounts=json.dumps(data.get('include_accounts', [])),
        exclude_accounts=json.dumps(data.get('exclude_accounts', [])),
        include_tags=json.dumps(data.get('include_tags', [])),
        exclude_tags=json.dumps(data.get('exclude_tags', [])),
        tag_match_mode=data.get('tag_match_mode', 'any'),
        enabled=data.get('enabled', True)
    )
    
    db.session.add(config)
    db.session.commit()
    
    return jsonify({
        'id': config.id,
        'name': config.name,
        'description': config.description,
        'include_accounts': json.loads(config.include_accounts),
        'exclude_accounts': json.loads(config.exclude_accounts),
        'include_tags': json.loads(config.include_tags),
        'exclude_tags': json.loads(config.exclude_tags),
        'tag_match_mode': config.tag_match_mode,
        'enabled': config.enabled
    }), 201


@app.route('/api/playlist-configs/<int:config_id>', methods=['PUT'])
def update_playlist_config(config_id):
    """Update playlist configuration"""
    config = PlaylistConfig.query.get_or_404(config_id)
    data = request.json
    
    config.name = data.get('name', config.name)
    config.description = data.get('description', config.description)
    
    if 'include_accounts' in data:
        config.include_accounts = json.dumps(data['include_accounts'])
    if 'exclude_accounts' in data:
        config.exclude_accounts = json.dumps(data['exclude_accounts'])
    if 'include_tags' in data:
        config.include_tags = json.dumps(data['include_tags'])
    if 'exclude_tags' in data:
        config.exclude_tags = json.dumps(data['exclude_tags'])
    
    config.tag_match_mode = data.get('tag_match_mode', config.tag_match_mode)
    config.enabled = data.get('enabled', config.enabled)
    
    db.session.commit()
    
    return jsonify({
        'id': config.id,
        'name': config.name,
        'description': config.description,
        'include_accounts': json.loads(config.include_accounts),
        'exclude_accounts': json.loads(config.exclude_accounts),
        'include_tags': json.loads(config.include_tags),
        'exclude_tags': json.loads(config.exclude_tags),
        'tag_match_mode': config.tag_match_mode,
        'enabled': config.enabled
    })


@app.route('/api/playlist-configs/<int:config_id>', methods=['DELETE'])
def delete_playlist_config(config_id):
    """Delete playlist configuration"""
    config = PlaylistConfig.query.get_or_404(config_id)
    
    db.session.delete(config)
    db.session.commit()
    
    return '', 204


@app.route('/api/playlist-configs/<int:config_id>/preview', methods=['GET'])
def preview_playlist_config(config_id):
    """Preview channels that would be included in this playlist configuration"""
    config = PlaylistConfig.query.get_or_404(config_id)
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    try:
        # Parse config
        include_accounts = json.loads(config.include_accounts) if config.include_accounts else []
        exclude_accounts = json.loads(config.exclude_accounts) if config.exclude_accounts else []
        include_tags = json.loads(config.include_tags) if config.include_tags else []
        exclude_tags = json.loads(config.exclude_tags) if config.exclude_tags else []
        
        # Get all enabled accounts or filter by include/exclude
        if include_accounts:
            accounts = Account.query.filter(Account.id.in_(include_accounts), Account.enabled == True).all()
        else:
            accounts = Account.query.filter(Account.enabled == True).all()
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
            
            category_map = {str(c['category_id']): c['category_name'] for c in categories}
            
            # Get tag rules
            tag_rules = TagRule.query.filter_by(enabled=True).order_by(TagRule.priority).all()
            
            # Process each stream
            for stream in streams:
                stream_id = str(stream.get('stream_id'))
                channel_name = stream.get('name', '')
                category_id = str(stream.get('category_id', ''))
                category_name = category_map.get(category_id, '')
                
                # Extract tags for this channel
                tags, cleaned_name = TagService.extract_tags(channel_name, category_name, tag_rules)
                
                # Check if channel matches filter criteria
                if matches_tag_filter(tags, include_tags, exclude_tags, config.tag_match_mode):
                    matching_channels.append({
                        'account_id': account.id,
                        'account_name': account.name,
                        'stream_id': stream_id,
                        'original_name': channel_name,
                        'cleaned_name': cleaned_name,
                        'category': category_name,
                        'tags': list(tags),
                        'icon': stream.get('stream_icon', '')
                    })
        
        # Apply pagination
        total = len(matching_channels)
        paginated = matching_channels[offset:offset+limit]
        
        return jsonify({
            'total': total,
            'offset': offset,
            'limit': limit,
            'showing': len(paginated),
            'channels': paginated,
            'has_more': offset + limit < total
        })
        
    except Exception as e:
        logger.error(f"Error previewing playlist config {config_id}: {e}")
        return jsonify({'error': str(e)}), 400


# ============================================================================
# Playlist Generation Routes
# ============================================================================

@app.route('/playlist/<int:account_id>.m3u')
def generate_playlist(account_id):
    """Generate M3U playlist for account with filters applied"""
    account = Account.query.get_or_404(account_id)
    
    if not account.enabled:
        return Response("Account is disabled", status=403)
    
    try:
        # Get streams
        service = IPTVService(account.server, account.username, account.password)
        streams = cache_service.get_cached_streams(account_id)
        if not streams:
            streams = service.get_live_streams()
            cache_service.cache_streams(account_id, streams)
        
        categories = cache_service.get_cached_categories(account_id)
        if not categories:
            categories = service.get_live_categories()
            cache_service.cache_categories(account_id, categories)
        
        # Build category map
        category_map = {str(c['category_id']): c['category_name'] for c in categories}
        
        # Get filters
        filters = Filter.query.filter_by(account_id=account_id, enabled=True).all()
        
        # Get tag rules for name cleaning
        tag_rules = TagRule.query.filter_by(enabled=True).order_by(TagRule.priority).all()
        
        # Apply filters
        filtered_streams = []
        for stream in streams:
            if apply_filters(stream, category_map, filters):
                filtered_streams.append(stream)
        
        # Generate M3U
        m3u_lines = ["#EXTM3U"]
        for stream in filtered_streams:
            stream_id = stream.get('stream_id')
            name = stream.get('name', '')
            category_id = str(stream.get('category_id', ''))
            category_name = category_map.get(category_id, 'Unknown')
            
            # Extract tags and clean name
            tags, cleaned_name = TagService.extract_tags(name, category_name, tag_rules)
            
            # Use cleaned name if available, otherwise original
            display_name = cleaned_name if cleaned_name else name
            
            tvg_id = stream.get('epg_channel_id', '')
            tvg_logo = stream.get('stream_icon', '')
            
            extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{display_name}" tvg-logo="{tvg_logo}" group-title="{category_name}",{display_name}'
            stream_url = f"http://{account.server}/live/{account.username}/{account.password}/{stream_id}.ts"
            
            m3u_lines.append(extinf)
            m3u_lines.append(stream_url)
        
        logger.info(f"Generated playlist for account {account_id}: {len(filtered_streams)} channels")
        return Response('\n'.join(m3u_lines), mimetype='application/x-mpegurl')
        
    except Exception as e:
        logger.error(f"Error generating playlist for account {account_id}: {e}")
        return Response(f"Error: {str(e)}", status=500)


@app.route('/playlist/config/<int:config_id>.m3u')
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
            accounts = Account.query.filter(Account.id.in_(include_accounts), Account.enabled == True).all()
        else:
            accounts = Account.query.filter(Account.enabled == True).all()
            if exclude_accounts:
                accounts = [a for a in accounts if a.id not in exclude_accounts]
        
        # Get tag rules
        tag_rules = TagRule.query.filter_by(enabled=True).order_by(TagRule.priority).all()
        
        # Generate M3U
        m3u_lines = [f"#EXTM3U"]
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
            
            category_map = {str(c['category_id']): c['category_name'] for c in categories}
            
            # Get existing filters for this account
            filters = Filter.query.filter_by(account_id=account.id, enabled=True).all()
            
            # Process each stream
            for stream in streams:
                # First apply account-level filters
                if not apply_filters(stream, category_map, filters):
                    continue
                
                stream_id = stream.get('stream_id')
                name = stream.get('name', '')
                category_id = str(stream.get('category_id', ''))
                category_name = category_map.get(category_id, 'Unknown')
                
                # Extract tags and clean name
                tags, cleaned_name = TagService.extract_tags(name, category_name, tag_rules)
                
                # Check if channel matches tag filter
                if not matches_tag_filter(tags, include_tags, exclude_tags, config.tag_match_mode):
                    continue
                
                # Use cleaned name
                display_name = cleaned_name if cleaned_name else name
                
                tvg_id = stream.get('epg_channel_id', '')
                tvg_logo = stream.get('stream_icon', '')
                
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
        
        logger.info(f"Generated playlist from config {config_id} ({config.name}): {total_channels} channels from {len(accounts)} accounts")
        return Response('\n'.join(m3u_lines), mimetype='application/x-mpegurl')
        
    except Exception as e:
        logger.error(f"Error generating playlist from config {config_id}: {e}")
        return Response(f"Error: {str(e)}", status=500)


@app.route('/epg/<int:account_id>.xml')
def proxy_epg(account_id):
    """Proxy EPG/XMLTV for account"""
    account = Account.query.get_or_404(account_id)
    
    if not account.enabled:
        return Response("Account is disabled", status=403)
    
    try:
        service = IPTVService(account.server, account.username, account.password)
        epg_data = service.get_xmltv()
        
        return Response(epg_data, mimetype='application/xml')
    except Exception as e:
        logger.error(f"Error proxying EPG for account {account_id}: {e}")
        return Response(f"Error: {str(e)}", status=500)


@app.route('/api/accounts/<int:account_id>/preview', methods=['GET'])
def preview_playlist(account_id):
    """Preview filtered channels (for testing) with pagination support"""
    account = Account.query.get_or_404(account_id)
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    try:
        service = IPTVService(account.server, account.username, account.password)
        streams = cache_service.get_cached_streams(account_id)
        if not streams:
            streams = service.get_live_streams()
            cache_service.cache_streams(account_id, streams)
        
        categories = cache_service.get_cached_categories(account_id)
        if not categories:
            categories = service.get_live_categories()
            cache_service.cache_categories(account_id, categories)
        
        category_map = {str(c['category_id']): c['category_name'] for c in categories}
        
        # Get filters
        filters = Filter.query.filter_by(account_id=account_id, enabled=True).all()
        
        # Apply filters and collect results with offset/limit
        filtered_streams = []
        skipped = 0
        
        for stream in streams:
            if apply_filters(stream, category_map, filters):
                # Skip items before offset
                if skipped < offset:
                    skipped += 1
                    continue
                
                filtered_streams.append({
                    'id': stream.get('stream_id'),
                    'name': stream.get('name'),
                    'category': category_map.get(str(stream.get('category_id', '')), 'Unknown'),
                    'icon': stream.get('stream_icon', '')
                })
                
                # Stop when we have enough items
                if len(filtered_streams) >= limit:
                    break
        
        # Calculate total (only when offset is 0 to avoid recalculating every time)
        if offset == 0:
            total = sum(1 for s in streams if apply_filters(s, category_map, filters))
        else:
            # For subsequent pages, return -1 to indicate total is unknown (client should use cached value)
            total = -1
        
        return jsonify({
            'total': total,
            'offset': offset,
            'limit': limit,
            'showing': len(filtered_streams),
            'channels': filtered_streams,
            'has_more': len(filtered_streams) == limit
        })
    except Exception as e:
        logger.error(f"Error previewing for account {account_id}: {e}")
        return jsonify({'error': str(e)}), 400


# ============================================================================
# Helper Functions
# ============================================================================

def matches_tag_filter(channel_tags, include_tags, exclude_tags, match_mode='any'):
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
    
    if match_mode == 'all':
        # Must have ALL include tags
        return all(tag in normalized_channel_tags for tag in normalized_include_tags)
    else:  # 'any'
        # Must have AT LEAST ONE include tag
        return any(tag in normalized_channel_tags for tag in normalized_include_tags)


def apply_filters(stream, category_map, filters):
    """Apply all filters to a stream"""
    name = stream.get('name', '').upper()
    category_id = str(stream.get('category_id', ''))
    category_name = category_map.get(category_id, '').upper()
    
    for f in filters:
        filter_value = f.filter_value.upper()
        
        if f.filter_type == 'category':
            # Check if category matches
            if f.filter_action == 'whitelist':
                if filter_value not in category_name:
                    return False
            elif f.filter_action == 'blacklist':
                if filter_value in category_name:
                    return False
                    
        elif f.filter_type == 'channel_name':
            # Check if channel name matches
            if f.filter_action == 'whitelist':
                if filter_value not in name:
                    return False
            elif f.filter_action == 'blacklist':
                if filter_value in name:
                    return False
                    
        elif f.filter_type == 'regex':
            import re
            try:
                pattern = re.compile(f.filter_value, re.IGNORECASE)
                if f.filter_action == 'whitelist':
                    if not pattern.search(name):
                        return False
                elif f.filter_action == 'blacklist':
                    if pattern.search(name):
                        return False
            except re.error:
                logger.warning(f"Invalid regex pattern in filter {f.id}: {f.filter_value}")
    
    return True


@app.route('/api/cache/clear', methods=['POST'])
def clear_all_cache():
    """Clear all caches"""
    cache_service.clear_all()
    return jsonify({'success': True})


@app.route('/api/cache/clear/<int:account_id>', methods=['POST'])
def clear_account_cache_route(account_id):
    """Clear cache for specific account"""
    cache_service.clear_account_cache(account_id)
    return jsonify({'success': True})


# ============================================================================
# Initialization
# ============================================================================

@app.cli.command()
def init_db():
    """Initialize the database"""
    db.create_all()
    print("Database initialized!")


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    port = int(os.getenv('PORT', 8000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting IPTV Proxy v2 on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
