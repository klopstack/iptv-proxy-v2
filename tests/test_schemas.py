"""
Tests for Marshmallow schemas

Tests input validation for all API endpoints.
"""
import os

import pytest
from marshmallow import ValidationError

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from schemas import (
    AccountCreateSchema,
    AccountUpdateSchema,
    CredentialCreateSchema,
    CredentialUpdateSchema,
    EpgChannelNameMappingCreateSchema,
    EpgChannelNameMappingUpdateSchema,
    EpgExclusionPatternCreateSchema,
    EpgExclusionPatternUpdateSchema,
    EpgMatchRuleCreateSchema,
    EpgMatchRuleSetCreateSchema,
    EpgMatchRuleSetUpdateSchema,
    EpgMatchRuleUpdateSchema,
    FilterCreateSchema,
    FilterUpdateSchema,
    RuleSetCreateSchema,
    RuleSetUpdateSchema,
    TagRuleCreateSchema,
    TagRuleUpdateSchema,
)


class TestAccountSchemas:
    """Tests for Account schemas"""

    def test_account_create_valid(self):
        """Test valid account creation"""
        schema = AccountCreateSchema()
        data = {
            "name": "Test Account",
            "server": "test.server.com",
            "username": "user",
            "password": "pass",
        }
        result = schema.load(data)
        assert result["name"] == "Test Account"
        assert result["enabled"] is True  # default value

    def test_account_create_missing_name(self):
        """Test account creation with missing name"""
        schema = AccountCreateSchema()
        data = {"server": "test.server.com", "username": "user", "password": "pass"}
        with pytest.raises(ValidationError) as exc:
            schema.load(data)
        assert "name" in exc.value.messages

    def test_account_create_invalid_server(self):
        """Test account creation with invalid server format"""
        schema = AccountCreateSchema()
        data = {
            "name": "Test",
            "server": "invalid server with spaces",
            "username": "user",
            "password": "pass",
        }
        with pytest.raises(ValidationError) as exc:
            schema.load(data)
        assert "server" in exc.value.messages

    def test_account_update_valid(self):
        """Test valid account update"""
        schema = AccountUpdateSchema()
        data = {"name": "Updated Name", "enabled": False}
        result = schema.load(data)
        assert result["name"] == "Updated Name"
        assert result["enabled"] is False

    def test_account_update_invalid_server(self):
        """Test account update with invalid server"""
        schema = AccountUpdateSchema()
        data = {"server": "http://invalid-with-scheme.com"}
        with pytest.raises(ValidationError) as exc:
            schema.load(data)
        assert "server" in exc.value.messages


class TestCredentialSchemas:
    """Tests for Credential schemas"""

    def test_credential_create_valid(self):
        """Test valid credential creation"""
        schema = CredentialCreateSchema()
        data = {"username": "testuser", "password": "testpass"}
        result = schema.load(data)
        assert result["username"] == "testuser"
        assert result["max_connections"] == 1  # default

    def test_credential_create_missing_password(self):
        """Test credential creation with missing password"""
        schema = CredentialCreateSchema()
        data = {"username": "user"}
        with pytest.raises(ValidationError) as exc:
            schema.load(data)
        assert "password" in exc.value.messages

    def test_credential_update_valid(self):
        """Test valid credential update"""
        schema = CredentialUpdateSchema()
        data = {"max_connections": 5}
        result = schema.load(data)
        assert result["max_connections"] == 5


class TestFilterSchemas:
    """Tests for Filter schemas"""

    def test_filter_create_valid(self):
        """Test valid filter creation"""
        schema = FilterCreateSchema()
        data = {
            "account_id": 1,
            "name": "Test Filter",
            "filter_type": "category",
            "filter_action": "whitelist",
            "filter_value": "Sports",
        }
        result = schema.load(data)
        assert result["name"] == "Test Filter"
        assert result["enabled"] is True  # default

    def test_filter_create_invalid_type(self):
        """Test filter creation with invalid type"""
        schema = FilterCreateSchema()
        data = {
            "account_id": 1,
            "name": "Test Filter",
            "filter_type": "invalid_type",
            "filter_action": "whitelist",
            "filter_value": "Sports",
        }
        with pytest.raises(ValidationError) as exc:
            schema.load(data)
        assert "filter_type" in exc.value.messages

    def test_filter_create_invalid_action(self):
        """Test filter creation with invalid action"""
        schema = FilterCreateSchema()
        data = {
            "account_id": 1,
            "name": "Test Filter",
            "filter_type": "category",
            "filter_action": "invalid_action",
            "filter_value": "Sports",
        }
        with pytest.raises(ValidationError) as exc:
            schema.load(data)
        assert "filter_action" in exc.value.messages

    def test_filter_create_empty_value(self):
        """Test filter creation with empty value"""
        schema = FilterCreateSchema()
        data = {
            "account_id": 1,
            "name": "Test Filter",
            "filter_type": "category",
            "filter_action": "whitelist",
            "filter_value": "   ",  # whitespace only
        }
        with pytest.raises(ValidationError) as exc:
            schema.load(data)
        assert "filter_value" in exc.value.messages

    def test_filter_update_valid(self):
        """Test valid filter update"""
        schema = FilterUpdateSchema()
        data = {"filter_value": "News", "enabled": False}
        result = schema.load(data)
        assert result["filter_value"] == "News"
        assert result["enabled"] is False

    def test_filter_update_invalid_regex(self):
        """Test filter update with invalid regex"""
        schema = FilterUpdateSchema()
        data = {"filter_value": "[invalid("}
        result = schema.load(data)  # Regex validation is optional
        assert result["filter_value"] == "[invalid("


class TestRuleSetSchemas:
    """Tests for RuleSet schemas"""

    def test_ruleset_create_valid(self):
        """Test valid ruleset creation"""
        schema = RuleSetCreateSchema()
        data = {"name": "Test Ruleset", "description": "A test ruleset"}
        result = schema.load(data)
        assert result["name"] == "Test Ruleset"
        assert result["is_default"] is False  # default

    def test_ruleset_create_name_too_long(self):
        """Test ruleset creation with name too long"""
        schema = RuleSetCreateSchema()
        data = {"name": "A" * 201}  # > 200 chars
        with pytest.raises(ValidationError) as exc:
            schema.load(data)
        assert "name" in exc.value.messages

    def test_ruleset_update_valid(self):
        """Test valid ruleset update"""
        schema = RuleSetUpdateSchema()
        data = {"description": "Updated description", "is_default": True}
        result = schema.load(data)
        assert result["is_default"] is True


class TestTagRuleSchemas:
    """Tests for TagRule schemas"""

    def test_tag_rule_create_valid(self):
        """Test valid tag rule creation"""
        schema = TagRuleCreateSchema()
        data = {
            "ruleset_id": 1,
            "name": "Test Rule",
            "pattern_type": "prefix",
            "pattern": "US|",
            "tag_name": "US",
            "source": "channel_name",
        }
        result = schema.load(data)
        assert result["name"] == "Test Rule"
        assert result["remove_from_name"] is True  # default

    def test_tag_rule_create_invalid_pattern_type(self):
        """Test tag rule creation with invalid pattern type"""
        schema = TagRuleCreateSchema()
        data = {
            "ruleset_id": 1,
            "name": "Test Rule",
            "pattern_type": "invalid",
            "pattern": "US|",
            "tag_name": "US",
        }
        with pytest.raises(ValidationError) as exc:
            schema.load(data)
        assert "pattern_type" in exc.value.messages

    def test_tag_rule_create_invalid_search_in(self):
        """Test tag rule creation with invalid search_in"""
        schema = TagRuleCreateSchema()
        data = {
            "ruleset_id": 1,
            "name": "Test Rule",
            "pattern_type": "prefix",
            "pattern": "US|",
            "tag_name": "US",
            "search_in": "invalid",
        }
        with pytest.raises(ValidationError) as exc:
            schema.load(data)
        assert "search_in" in exc.value.messages

    def test_tag_rule_update_valid(self):
        """Test valid tag rule update"""
        schema = TagRuleUpdateSchema()
        data = {"priority": 50, "enabled": False}
        result = schema.load(data)
        assert result["priority"] == 50
        assert result["enabled"] is False


class TestEpgMatchRuleSchemas:
    """Tests for EPG Match Rule schemas"""

    def test_epg_ruleset_create_valid(self):
        """Test valid EPG ruleset creation"""
        schema = EpgMatchRuleSetCreateSchema()
        data = {"name": "EPG Test Ruleset"}
        result = schema.load(data)
        assert result["name"] == "EPG Test Ruleset"

    def test_epg_ruleset_update_valid(self):
        """Test valid EPG ruleset update"""
        schema = EpgMatchRuleSetUpdateSchema()
        data = {"enabled": False, "priority": 200}
        result = schema.load(data)
        assert result["enabled"] is False

    def test_epg_rule_create_valid(self):
        """Test valid EPG match rule creation"""
        schema = EpgMatchRuleCreateSchema()
        data = {
            "ruleset_id": 1,
            "name": "Test EPG Rule",
            "match_type": "exact_name",
        }
        result = schema.load(data)
        assert result["match_type"] == "exact_name"
        assert result["enabled"] is True  # default

    def test_epg_rule_create_invalid_match_type(self):
        """Test EPG rule creation with invalid match type"""
        schema = EpgMatchRuleCreateSchema()
        data = {
            "ruleset_id": 1,
            "name": "Test Rule",
            "match_type": "invalid_type",
        }
        with pytest.raises(ValidationError) as exc:
            schema.load(data)
        assert "match_type" in exc.value.messages

    def test_epg_rule_create_invalid_source(self):
        """Test EPG rule creation with invalid source"""
        schema = EpgMatchRuleCreateSchema()
        data = {
            "ruleset_id": 1,
            "name": "Test Rule",
            "match_type": "exact_name",
            "source": "invalid_source",
        }
        with pytest.raises(ValidationError) as exc:
            schema.load(data)
        assert "source" in exc.value.messages

    def test_epg_rule_update_valid(self):
        """Test valid EPG rule update"""
        schema = EpgMatchRuleUpdateSchema()
        data = {"min_confidence": 0.8, "stop_on_match": True}
        result = schema.load(data)
        assert result["min_confidence"] == 0.8


class TestEpgExclusionPatternSchemas:
    """Tests for EPG Exclusion Pattern schemas"""

    def test_exclusion_create_valid(self):
        """Test valid exclusion pattern creation"""
        schema = EpgExclusionPatternCreateSchema()
        data = {
            "name": "PPV Exclusion",
            "pattern_type": "category_name",
            "pattern": "PPV",
        }
        result = schema.load(data)
        assert result["name"] == "PPV Exclusion"
        assert result["enabled"] is True  # default

    def test_exclusion_create_invalid_pattern_type(self):
        """Test exclusion creation with invalid pattern type"""
        schema = EpgExclusionPatternCreateSchema()
        data = {
            "name": "Test",
            "pattern_type": "invalid",
            "pattern": "PPV",
        }
        with pytest.raises(ValidationError) as exc:
            schema.load(data)
        assert "pattern_type" in exc.value.messages

    def test_exclusion_update_valid(self):
        """Test valid exclusion pattern update"""
        schema = EpgExclusionPatternUpdateSchema()
        data = {"hide_channel": True, "priority": 50}
        result = schema.load(data)
        assert result["hide_channel"] is True


class TestEpgChannelNameMappingSchemas:
    """Tests for EPG Channel Name Mapping schemas"""

    def test_mapping_create_valid(self):
        """Test valid channel name mapping creation"""
        schema = EpgChannelNameMappingCreateSchema()
        data = {
            "name": "HD Removal",
            "old_name": "HD",
            "new_name": "removed",  # new_name requires at least 1 char
        }
        result = schema.load(data)
        assert result["name"] == "HD Removal"
        assert result["match_type"] == "contains"  # default

    def test_mapping_create_invalid_match_type(self):
        """Test mapping creation with invalid match type"""
        schema = EpgChannelNameMappingCreateSchema()
        data = {
            "name": "Test",
            "old_name": "old",
            "new_name": "new",
            "match_type": "invalid",
        }
        with pytest.raises(ValidationError) as exc:
            schema.load(data)
        assert "match_type" in exc.value.messages

    def test_mapping_update_valid(self):
        """Test valid channel name mapping update"""
        schema = EpgChannelNameMappingUpdateSchema()
        data = {"case_sensitive": True, "priority": 25}
        result = schema.load(data)
        assert result["case_sensitive"] is True
