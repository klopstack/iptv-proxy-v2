"""
Test input validation using Marshmallow schemas

Tests that:
1. Valid data is accepted
2. Invalid data is rejected with 400 Bad Request
3. Validation errors provide clear messages
4. Required fields are enforced
5. Type and format constraints work
"""
import pytest
from models import Account, RuleSet, db


# ============================================================================
# Account Validation Tests
# ============================================================================


def test_create_account_with_valid_data(client):
    """Test account creation with valid data"""
    response = client.post(
        "/api/accounts",
        json={"name": "Test Account", "server": "test.example.com", "username": "testuser", "password": "testpass"},
    )

    assert response.status_code == 201
    data = response.json
    assert data["name"] == "Test Account"
    assert data["server"] == "test.example.com"


def test_create_account_missing_required_fields(client):
    """Test account creation fails with missing required fields"""
    response = client.post(
        "/api/accounts",
        json={
            "name": "Test Account"
            # Missing server, username, password
        },
    )

    assert response.status_code == 400
    data = response.json
    assert "validation_errors" in data
    assert "server" in data["validation_errors"]
    assert "username" in data["validation_errors"]
    assert "password" in data["validation_errors"]


def test_create_account_empty_name(client):
    """Test account creation fails with empty name"""
    response = client.post(
        "/api/accounts", json={"name": "", "server": "test.example.com", "username": "testuser", "password": "testpass"}
    )

    assert response.status_code == 400
    data = response.json
    assert "validation_errors" in data
    assert "name" in data["validation_errors"]


def test_create_account_invalid_server(client):
    """Test account creation fails with invalid server format"""
    response = client.post(
        "/api/accounts",
        json={"name": "Test Account", "server": "invalid server!@#", "username": "testuser", "password": "testpass"},
    )

    assert response.status_code == 400
    data = response.json
    assert "validation_errors" in data
    assert "server" in data["validation_errors"]


def test_update_account_with_valid_data(app, client):
    """Test account update with valid data"""
    with app.app_context():
        account = Account(name="Original", server="original.com", username="user", password="pass", enabled=True)
        db.session.add(account)
        db.session.commit()
        account_id = account.id

    response = client.put(f"/api/accounts/{account_id}", json={"name": "Updated Name", "enabled": False})

    assert response.status_code == 200
    data = response.json
    assert data["name"] == "Updated Name"
    assert data["enabled"] is False


def test_update_account_invalid_field(app, client):
    """Test account update fails with invalid field type"""
    with app.app_context():
        account = Account(name="Original", server="original.com", username="user", password="pass")
        db.session.add(account)
        db.session.commit()
        account_id = account.id

    response = client.put(f"/api/accounts/{account_id}", json={"enabled": "not-a-boolean"})

    assert response.status_code == 400


# ============================================================================
# Filter Validation Tests
# ============================================================================


def test_create_filter_with_valid_data(app, client):
    """Test filter creation with valid data"""
    with app.app_context():
        account = Account(name="Test", server="test.com", username="user", password="pass")
        db.session.add(account)
        db.session.commit()
        account_id = account.id

    response = client.post(
        "/api/filters",
        json={
            "account_id": account_id,
            "name": "Test Filter",
            "filter_type": "category",
            "filter_action": "whitelist",
            "filter_value": "Sports",
        },
    )

    assert response.status_code == 201
    data = response.json
    assert data["name"] == "Test Filter"
    assert data["filter_type"] == "category"


def test_create_filter_invalid_type(app, client):
    """Test filter creation fails with invalid filter_type"""
    with app.app_context():
        account = Account(name="Test", server="test.com", username="user", password="pass")
        db.session.add(account)
        db.session.commit()
        account_id = account.id

    response = client.post(
        "/api/filters",
        json={
            "account_id": account_id,
            "name": "Test Filter",
            "filter_type": "invalid_type",
            "filter_action": "include",
            "filter_value": "Sports",
        },
    )

    assert response.status_code == 400
    data = response.json
    assert "validation_errors" in data
    assert "filter_type" in data["validation_errors"]


def test_create_filter_empty_value(app, client):
    """Test filter creation fails with empty filter_value"""
    with app.app_context():
        account = Account(name="Test", server="test.com", username="user", password="pass")
        db.session.add(account)
        db.session.commit()
        account_id = account.id

    response = client.post(
        "/api/filters",
        json={
            "account_id": account_id,
            "name": "Test Filter",
            "filter_type": "category_whitelist",
            "filter_action": "include",
            "filter_value": "   ",  # Whitespace only
        },
    )

    assert response.status_code == 400
    data = response.json
    assert "validation_errors" in data
    assert "filter_value" in data["validation_errors"]


# ============================================================================
# TagRule Validation Tests
# ============================================================================


def test_create_tag_rule_with_valid_data(app, client):
    """Test tag rule creation with valid data"""
    with app.app_context():
        ruleset = RuleSet(name="Test RuleSet", description="Test")
        db.session.add(ruleset)
        db.session.commit()
        ruleset_id = ruleset.id

    response = client.post(
        "/api/tag-rules",
        json={
            "ruleset_id": ruleset_id,
            "name": "Test Rule",
            "pattern": "4K",
            "pattern_type": "contains",
            "tag_name": "4K",
            "source": "channel_name",
            "priority": 50,
        },
    )

    assert response.status_code == 201
    data = response.json
    assert data["name"] == "Test Rule"
    assert data["pattern"] == "4K"


def test_create_tag_rule_invalid_pattern_type(app, client):
    """Test tag rule creation fails with invalid pattern_type"""
    with app.app_context():
        ruleset = RuleSet(name="Test RuleSet")
        db.session.add(ruleset)
        db.session.commit()
        ruleset_id = ruleset.id

    response = client.post(
        "/api/tag-rules",
        json={
            "ruleset_id": ruleset_id,
            "name": "Test Rule",
            "pattern": "4K",
            "pattern_type": "invalid",
            "tag_name": "4K",
            "source": "channel_name",
        },
    )

    assert response.status_code == 400
    data = response.json
    assert "validation_errors" in data
    assert "pattern_type" in data["validation_errors"]


def test_create_tag_rule_invalid_priority(app, client):
    """Test tag rule creation fails with out-of-range priority"""
    with app.app_context():
        ruleset = RuleSet(name="Test RuleSet")
        db.session.add(ruleset)
        db.session.commit()
        ruleset_id = ruleset.id

    response = client.post(
        "/api/tag-rules",
        json={
            "ruleset_id": ruleset_id,
            "name": "Test Rule",
            "pattern": "4K",
            "pattern_type": "contains",
            "tag_name": "4K",
            "source": "channel_name",
            "priority": 5000,  # Out of valid range (1-1000)
        },
    )

    assert response.status_code == 400
    data = response.json
    assert "validation_errors" in data
    assert "priority" in data["validation_errors"]


def test_create_tag_rule_special_tag_validation(app, client):
    """Test special tag naming rules"""
    with app.app_context():
        ruleset = RuleSet(name="Test RuleSet")
        db.session.add(ruleset)
        db.session.commit()
        ruleset_id = ruleset.id

    # Invalid: starts with __ but doesn't end with __
    response = client.post(
        "/api/tag-rules",
        json={
            "ruleset_id": ruleset_id,
            "name": "Test Rule",
            "pattern": "test",
            "pattern_type": "contains",
            "tag_name": "__INVALID",
            "source": "channel_name",
        },
    )

    assert response.status_code == 400
    data = response.json
    assert "validation_errors" in data
    assert "tag_name" in data["validation_errors"]

    # Valid: proper special tag
    response = client.post(
        "/api/tag-rules",
        json={
            "ruleset_id": ruleset_id,
            "name": "Test Rule",
            "pattern": "test",
            "pattern_type": "contains",
            "tag_name": "__CLEANUP__",
            "source": "channel_name",
        },
    )

    assert response.status_code == 201


# ============================================================================
# PlaylistConfig Validation Tests
# ============================================================================


def test_create_playlist_config_with_valid_data(client):
    """Test playlist config creation with valid data"""
    response = client.post(
        "/api/playlist-configs",
        json={"name": "Test Playlist", "include_accounts": [1, 2], "include_tags": ["Sports", "News"]},
    )

    assert response.status_code == 201
    data = response.json
    assert data["name"] == "Test Playlist"


def test_create_playlist_config_account_overlap(client):
    """Test playlist config fails when account is in both include and exclude"""
    response = client.post(
        "/api/playlist-configs",
        json={"name": "Test Playlist", "include_accounts": [1, 2, 3], "exclude_accounts": [2, 4]},  # 2 overlaps
    )

    assert response.status_code == 400
    data = response.json
    assert "validation_errors" in data
    assert "include_accounts" in data["validation_errors"]


def test_create_playlist_config_tag_overlap(client):
    """Test playlist config fails when tag is in both include and exclude"""
    response = client.post(
        "/api/playlist-configs",
        json={
            "name": "Test Playlist",
            "include_tags": ["Sports", "News"],
            "exclude_tags": ["News", "Adult"],  # News overlaps
        },
    )

    assert response.status_code == 400
    data = response.json
    assert "validation_errors" in data
    assert "include_tags" in data["validation_errors"]


def test_create_playlist_config_empty_name(client):
    """Test playlist config fails with empty name"""
    response = client.post("/api/playlist-configs", json={"name": ""})

    assert response.status_code == 400
    data = response.json
    assert "validation_errors" in data
    assert "name" in data["validation_errors"]


# ============================================================================
# General Validation Tests
# ============================================================================


def test_validation_with_null_json(client):
    """Test endpoints handle null/missing JSON body"""
    response = client.post("/api/accounts")

    # Flask returns 415 (Unsupported Media Type) when no Content-Type header is sent
    assert response.status_code == 415


def test_validation_with_wrong_types(app, client):
    """Test validation catches type mismatches"""
    with app.app_context():
        account = Account(name="Test", server="test.com", username="user", password="pass")
        db.session.add(account)
        db.session.commit()
        account_id = account.id

    # Sending string for account_id integer
    response = client.post(
        "/api/filters",
        json={
            "account_id": "not-an-integer",
            "name": "Test Filter",
            "filter_type": "category_whitelist",
            "filter_action": "include",
            "filter_value": "Sports",
        },
    )

    assert response.status_code == 400
