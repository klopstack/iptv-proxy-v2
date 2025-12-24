"""
Tests for EPG Match Rules functionality

Tests the configurable EPG matching rules system including:
- EpgMatchRuleSet CRUD
- EpgMatchRule CRUD
- EpgExclusionPattern CRUD
- Rule-based channel matching

Uses shared fixtures from conftest.py for proper test isolation.
"""
import pytest

from models import (
    Account,
    AccountEpgMatchRuleSet,
    Category,
    Channel,
    EpgChannel,
    EpgExclusionPattern,
    EpgMatchRule,
    EpgMatchRuleSet,
    EpgSource,
    db,
)

# app and client fixtures are provided by conftest.py


@pytest.fixture
def sample_account(app):
    """Create a sample account for testing"""
    with app.app_context():
        account = Account(
            name="Test Account",
            server="http://test.server.com",
            username="testuser",
            password="testpass",
        )
        db.session.add(account)
        db.session.commit()
        # Refresh to get the id
        db.session.refresh(account)
        account_id = account.id
    # Return a simple object with the id
    return type("Account", (), {"id": account_id})()


@pytest.fixture
def sample_epg_source(app):
    """Create a sample EPG source for testing"""
    with app.app_context():
        source = EpgSource(
            name="Test EPG Source",
            source_type="xmltv_url",
            url="http://test.epg.com/guide.xml",
        )
        db.session.add(source)
        db.session.commit()
        db.session.refresh(source)
        source_id = source.id
    return type("EpgSource", (), {"id": source_id})()


@pytest.fixture
def sample_epg_channels(app, sample_epg_source):
    """Create sample EPG channels for testing"""
    with app.app_context():
        channels = []
        for name, channel_id in [
            ("ESPN", "ESPN.us"),
            ("CNN", "CNN.us"),
            ("HBO", "HBO.us"),
            ("NBC", "NBC.us"),
        ]:
            ec = EpgChannel(
                source_id=sample_epg_source.id,
                channel_id=channel_id,
                display_name=name,
            )
            db.session.add(ec)
            channels.append(ec)
        db.session.commit()
    return channels


@pytest.fixture
def sample_ruleset(app):
    """Create a sample EPG match ruleset"""
    with app.app_context():
        ruleset = EpgMatchRuleSet(
            name="Test Ruleset",
            description="A test ruleset for EPG matching",
            is_default=True,
            enabled=True,
            priority=100,
        )
        db.session.add(ruleset)
        db.session.commit()
        db.session.refresh(ruleset)
        ruleset_id = ruleset.id
    return type("Ruleset", (), {"id": ruleset_id})()


class TestEpgMatchRuleSetCRUD:
    """Tests for EPG Match Ruleset CRUD operations"""

    def test_create_ruleset(self, client, app):
        """Test creating an EPG match ruleset"""
        response = client.post(
            "/api/epg-match-rules/rulesets",
            json={
                "name": "New Ruleset",
                "description": "A new EPG match ruleset",
                "is_default": False,
                "enabled": True,
                "priority": 50,
            },
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["name"] == "New Ruleset"
        assert data["description"] == "A new EPG match ruleset"
        assert data["is_default"] is False
        assert data["enabled"] is True
        assert data["priority"] == 50

    def test_get_rulesets(self, client, app, sample_ruleset):
        """Test getting all EPG match rulesets"""
        response = client.get("/api/epg-match-rules/rulesets")

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(r["name"] == "Test Ruleset" for r in data)

    def test_get_ruleset_by_id(self, client, app, sample_ruleset):
        """Test getting a specific EPG match ruleset"""
        response = client.get(f"/api/epg-match-rules/rulesets/{sample_ruleset.id}")

        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "Test Ruleset"
        assert data["id"] == sample_ruleset.id

    def test_update_ruleset(self, client, app, sample_ruleset):
        """Test updating an EPG match ruleset"""
        response = client.put(
            f"/api/epg-match-rules/rulesets/{sample_ruleset.id}",
            json={
                "name": "Updated Ruleset",
                "description": "Updated description",
                "priority": 25,
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "Updated Ruleset"
        assert data["description"] == "Updated description"
        assert data["priority"] == 25

    def test_delete_ruleset(self, client, app, sample_ruleset):
        """Test deleting an EPG match ruleset"""
        ruleset_id = sample_ruleset.id
        response = client.delete(f"/api/epg-match-rules/rulesets/{ruleset_id}")

        assert response.status_code == 204

        # Verify deletion
        with app.app_context():
            deleted = EpgMatchRuleSet.query.get(ruleset_id)
            assert deleted is None

    def test_create_ruleset_duplicate_name(self, client, app, sample_ruleset):
        """Test that duplicate ruleset names are rejected"""
        response = client.post(
            "/api/epg-match-rules/rulesets",
            json={
                "name": "Test Ruleset",  # Same name as existing
                "description": "Duplicate",
            },
        )

        assert response.status_code in [400, 409]


class TestEpgMatchRuleCRUD:
    """Tests for EPG Match Rule CRUD operations"""

    def test_create_rule(self, client, app, sample_ruleset):
        """Test creating an EPG match rule"""
        response = client.post(
            "/api/epg-match-rules/rules",
            json={
                "ruleset_id": sample_ruleset.id,
                "name": "Exact Callsign Match",
                "description": "Match by exact callsign tag",
                "match_type": "callsign_tag",
                "source": "cleaned_name",
                "priority": 10,
                "enabled": True,
            },
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["name"] == "Exact Callsign Match"
        assert data["match_type"] == "callsign_tag"
        assert data["priority"] == 10

    def test_get_rules_for_ruleset(self, client, app, sample_ruleset):
        """Test getting all rules for a ruleset"""
        # First create a rule
        with app.app_context():
            rule = EpgMatchRule(
                ruleset_id=sample_ruleset.id,
                name="Test Rule",
                match_type="exact_name",
                source="cleaned_name",
                priority=100,
            )
            db.session.add(rule)
            db.session.commit()

        response = client.get(f"/api/epg-match-rules/rules?ruleset_id={sample_ruleset.id}")

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_update_rule(self, client, app, sample_ruleset):
        """Test updating an EPG match rule"""
        # Create a rule first
        with app.app_context():
            rule = EpgMatchRule(
                ruleset_id=sample_ruleset.id,
                name="Original Rule",
                match_type="exact_name",
                source="cleaned_name",
                priority=100,
            )
            db.session.add(rule)
            db.session.commit()
            rule_id = rule.id

        response = client.put(
            f"/api/epg-match-rules/rules/{rule_id}",
            json={
                "name": "Updated Rule",
                "priority": 50,
                "min_confidence": 0.85,
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "Updated Rule"
        assert data["priority"] == 50
        assert data["min_confidence"] == 0.85

    def test_delete_rule(self, client, app, sample_ruleset):
        """Test deleting an EPG match rule"""
        # Create a rule first
        with app.app_context():
            rule = EpgMatchRule(
                ruleset_id=sample_ruleset.id,
                name="Rule to Delete",
                match_type="exact_name",
                source="cleaned_name",
                priority=100,
            )
            db.session.add(rule)
            db.session.commit()
            rule_id = rule.id

        response = client.delete(f"/api/epg-match-rules/rules/{rule_id}")

        assert response.status_code == 204

        # Verify deletion
        with app.app_context():
            deleted = EpgMatchRule.query.get(rule_id)
            assert deleted is None


class TestEpgExclusionPatternCRUD:
    """Tests for EPG Exclusion Pattern CRUD operations"""

    def test_create_exclusion_pattern(self, client, app):
        """Test creating an EPG exclusion pattern"""
        response = client.post(
            "/api/epg-match-rules/exclusions",
            json={
                "name": "PPV Exclusion",
                "description": "Exclude PPV channels from EPG matching",
                "pattern_type": "category_name",
                "pattern": "PPV",
                "is_regex": False,
                "hide_channel": False,
                "enabled": True,
                "priority": 10,
            },
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["name"] == "PPV Exclusion"
        assert data["pattern_type"] == "category_name"
        assert data["pattern"] == "PPV"

    def test_get_exclusion_patterns(self, client, app):
        """Test getting all exclusion patterns"""
        # Create a pattern first
        with app.app_context():
            pattern = EpgExclusionPattern(
                name="Test Pattern",
                pattern_type="category_name",
                pattern="TEST",
                is_regex=False,
                priority=100,
            )
            db.session.add(pattern)
            db.session.commit()

        response = client.get("/api/epg-match-rules/exclusions")

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_update_exclusion_pattern(self, client, app):
        """Test updating an exclusion pattern"""
        # Create a pattern first
        with app.app_context():
            pattern = EpgExclusionPattern(
                name="Original Pattern",
                pattern_type="category_name",
                pattern="ORIGINAL",
                is_regex=False,
                priority=100,
            )
            db.session.add(pattern)
            db.session.commit()
            pattern_id = pattern.id

        response = client.put(
            f"/api/epg-match-rules/exclusions/{pattern_id}",
            json={
                "name": "Updated Pattern",
                "pattern": "UPDATED",
                "is_regex": True,
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "Updated Pattern"
        assert data["pattern"] == "UPDATED"
        assert data["is_regex"] is True

    def test_delete_exclusion_pattern(self, client, app):
        """Test deleting an exclusion pattern"""
        # Create a pattern first
        with app.app_context():
            pattern = EpgExclusionPattern(
                name="Pattern to Delete",
                pattern_type="channel_name",
                pattern="DELETE",
                is_regex=False,
                priority=100,
            )
            db.session.add(pattern)
            db.session.commit()
            pattern_id = pattern.id

        response = client.delete(f"/api/epg-match-rules/exclusions/{pattern_id}")

        assert response.status_code == 204

        # Verify deletion
        with app.app_context():
            deleted = EpgExclusionPattern.query.get(pattern_id)
            assert deleted is None


class TestAccountRulesetAssignment:
    """Tests for assigning rulesets to accounts"""

    def test_assign_ruleset_to_account(self, client, app, sample_account, sample_ruleset):
        """Test assigning an EPG match ruleset to an account"""
        response = client.post(
            f"/api/accounts/{sample_account.id}/epg-match-rulesets",
            json={
                "ruleset_id": sample_ruleset.id,
                "priority": 10,
            },
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["success"] is True

    def test_remove_ruleset_from_account(self, client, app, sample_account, sample_ruleset):
        """Test removing an EPG match ruleset from an account"""
        # First assign the ruleset
        with app.app_context():
            assignment = AccountEpgMatchRuleSet(
                account_id=sample_account.id,
                ruleset_id=sample_ruleset.id,
                priority=100,
            )
            db.session.add(assignment)
            db.session.commit()

        response = client.delete(f"/api/accounts/{sample_account.id}/epg-match-rulesets/{sample_ruleset.id}")

        assert response.status_code == 204

        # Verify deletion
        with app.app_context():
            remaining = AccountEpgMatchRuleSet.query.filter_by(
                account_id=sample_account.id, ruleset_id=sample_ruleset.id
            ).first()
            assert remaining is None


class TestEpgMatchRulesService:
    """Tests for the EPG match rules service"""

    def test_should_exclude_channel_by_category(self, app):
        """Test excluding a channel by category pattern"""
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            # Clear cache to ensure test isolation
            clear_fcc_pattern_cache()

            # Create account first
            account = Account(
                name="Test Account Service",
                server="http://test.server.com",
                username="testuser",
                password="testpass",
            )
            db.session.add(account)
            db.session.commit()

            # Create exclusion pattern
            pattern = EpgExclusionPattern(
                name="PPV Exclusion",
                pattern_type="category_name",
                pattern="PPV",
                is_regex=False,
                enabled=True,
                priority=10,
            )
            db.session.add(pattern)

            # Create category and channel
            category = Category(
                account_id=account.id,
                category_id=1,
                category_name="US| PPV Events",
            )
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="12345",
                name="PPV Channel 1",
                category_id=category.id,
            )
            db.session.add(channel)
            db.session.commit()

            # Test exclusion
            should_exclude, pattern_name, hide = EpgMatchRulesService.should_exclude_channel(channel)
            assert should_exclude is True
            assert pattern_name == "PPV Exclusion"

    def test_should_not_exclude_regular_channel(self, app):
        """Test that regular channels are not excluded"""
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            # Clear cache to ensure test isolation
            clear_fcc_pattern_cache()

            # Create account first
            account = Account(
                name="Test Account Service 2",
                server="http://test.server.com",
                username="testuser2",
                password="testpass",
            )
            db.session.add(account)
            db.session.commit()

            # Create exclusion pattern
            pattern = EpgExclusionPattern(
                name="PPV Exclusion",
                pattern_type="category_name",
                pattern="PPV",
                is_regex=False,
                enabled=True,
                priority=10,
            )
            db.session.add(pattern)

            # Create category and channel (not PPV)
            category = Category(
                account_id=account.id,
                category_id=2,
                category_name="US| Sports",
            )
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="12346",
                name="ESPN",
                category_id=category.id,
            )
            db.session.add(channel)
            db.session.commit()

            # Test exclusion
            should_exclude, pattern_name, hide = EpgMatchRulesService.should_exclude_channel(channel)
            assert should_exclude is False
            assert pattern_name is None

    def test_get_rulesets_for_account_with_assignment(self, app):
        """Test getting rulesets for an account with explicit assignment"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            # Create account
            account = Account(
                name="Test Account Service 3",
                server="http://test.server.com",
                username="testuser3",
                password="testpass",
            )
            db.session.add(account)

            # Create ruleset
            ruleset = EpgMatchRuleSet(
                name="Test Ruleset Service",
                description="A test ruleset for EPG matching",
                is_default=False,
                enabled=True,
                priority=100,
            )
            db.session.add(ruleset)
            db.session.commit()

            # Assign ruleset to account
            assignment = AccountEpgMatchRuleSet(
                account_id=account.id,
                ruleset_id=ruleset.id,
                priority=10,
            )
            db.session.add(assignment)
            db.session.commit()

            rulesets = EpgMatchRulesService.get_rulesets_for_account(account.id)
            assert len(rulesets) == 1
            assert rulesets[0].name == "Test Ruleset Service"

    def test_get_rulesets_for_account_fallback_to_default(self, app):
        """Test getting default rulesets when no assignment exists"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            # Create account
            account = Account(
                name="Test Account Service 4",
                server="http://test.server.com",
                username="testuser4",
                password="testpass",
            )
            db.session.add(account)

            # Create default ruleset
            ruleset = EpgMatchRuleSet(
                name="Default Test Ruleset",
                description="Default EPG matching ruleset",
                is_default=True,
                enabled=True,
                priority=100,
            )
            db.session.add(ruleset)
            db.session.commit()

            # No assignment - should get default rulesets
            rulesets = EpgMatchRulesService.get_rulesets_for_account(account.id)
            assert len(rulesets) >= 1
            assert any(r.is_default for r in rulesets)


class TestPreviewEndpoints:
    """Test the preview endpoints for exclusion patterns and rules"""

    def test_preview_exclusion_pattern_empty_pattern(self, client, app):
        """Test preview with empty pattern returns error"""
        response = client.post(
            "/api/epg-match-rules/exclusions/preview",
            json={
                "pattern_type": "channel_name",
                "pattern": "",
                "is_regex": True,
            },
        )
        assert response.status_code == 200
        data = response.json
        assert data["matches"] == []
        assert data["total_count"] == 0
        assert "error" in data

    def test_preview_exclusion_pattern_invalid_regex(self, client, app):
        """Test preview with invalid regex returns error"""
        response = client.post(
            "/api/epg-match-rules/exclusions/preview",
            json={
                "pattern_type": "channel_name",
                "pattern": "[invalid",
                "is_regex": True,
            },
        )
        assert response.status_code == 200
        data = response.json
        assert "error" in data
        assert "Invalid regex" in data["error"]

    def test_preview_exclusion_pattern_channel_name(self, client, app):
        """Test preview exclusion pattern for channel names"""
        from models import Account, Category, Channel

        with app.app_context():
            # Create test account
            account = Account(
                name="Preview Test Account",
                server="http://test.server.com",
                username="testuser_preview",
                password="testpass",
            )
            db.session.add(account)
            db.session.commit()

            # Create test category
            category = Category(account_id=account.id, category_id="1", category_name="Test Category")
            db.session.add(category)
            db.session.commit()

            # Create test channels
            channel1 = Channel(
                account_id=account.id,
                stream_id="1",
                name="ESPN Sports",
                category_id=category.id,
                is_active=True,
            )
            channel2 = Channel(
                account_id=account.id,
                stream_id="2",
                name="CNN News",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel1)
            db.session.add(channel2)
            db.session.commit()

        response = client.post(
            "/api/epg-match-rules/exclusions/preview",
            json={
                "pattern_type": "channel_name",
                "pattern": "ESPN",
                "is_regex": False,
            },
        )
        assert response.status_code == 200
        data = response.json
        assert data["total_count"] >= 1
        # Check that ESPN is in the matches
        names = [m["name"] for m in data["matches"]]
        assert any("ESPN" in name for name in names)

    def test_preview_rule_pattern_invalid_regex(self, client, app):
        """Test preview rule pattern with invalid regex returns error"""
        response = client.post(
            "/api/epg-match-rules/rules/preview",
            json={
                "match_type": "regex",
                "source": "channel_name",
                "pattern": "[invalid",
            },
        )
        assert response.status_code == 200
        data = response.json
        assert "error" in data
        assert "Invalid regex" in data["error"]

    def test_preview_rule_pattern_regex(self, client, app):
        """Test preview rule pattern with regex"""
        from models import Account, Category, Channel

        with app.app_context():
            # Create test account if it doesn't exist
            account = Account.query.filter_by(name="Preview Test Account 2").first()
            if not account:
                account = Account(
                    name="Preview Test Account 2",
                    server="http://test.server.com",
                    username="testuser_preview2",
                    password="testpass",
                )
                db.session.add(account)
                db.session.commit()

            # Create test category
            category = Category(account_id=account.id, category_id="2", category_name="News Category")
            db.session.add(category)
            db.session.commit()

            # Create test channels
            channel1 = Channel(
                account_id=account.id,
                stream_id="10",
                name="FOX News HD",
                category_id=category.id,
                is_active=True,
            )
            channel2 = Channel(
                account_id=account.id,
                stream_id="11",
                name="ABC News",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel1)
            db.session.add(channel2)
            db.session.commit()

        response = client.post(
            "/api/epg-match-rules/rules/preview",
            json={
                "match_type": "regex",
                "source": "channel_name",
                "pattern": "News",
            },
        )
        assert response.status_code == 200
        data = response.json
        assert data["total_count"] >= 1
        assert "matches" in data


class TestChannelNumberExtraction:
    """Test the channel number extraction from channel names"""

    def test_extract_network_followed_by_number(self, app):
        """Test extracting channel number when network is followed by number"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            assert EpgMatchRulesService._extract_channel_number("US: NBC 13 HD [MONTANA]") == "13"
            assert EpgMatchRulesService._extract_channel_number("ABC 7 News") == "7"
            assert EpgMatchRulesService._extract_channel_number("CBS 2 Los Angeles") == "2"
            assert EpgMatchRulesService._extract_channel_number("FOX 11 LA") == "11"
            assert EpgMatchRulesService._extract_channel_number("PBS 2 [NEW YORK]") == "2"

    def test_extract_number_followed_by_network(self, app):
        """Test extracting channel number when number is followed by network/quality"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            assert EpgMatchRulesService._extract_channel_number("Channel 9 HD") == "9"
            assert EpgMatchRulesService._extract_channel_number("US: 13 NBC HD") == "13"

    def test_extract_no_channel_number(self, app):
        """Test that None is returned when no channel number is found"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            assert EpgMatchRulesService._extract_channel_number("ESPN") is None
            assert EpgMatchRulesService._extract_channel_number("CNN International") is None
            assert EpgMatchRulesService._extract_channel_number("") is None
            assert EpgMatchRulesService._extract_channel_number(None) is None


class TestFccLookupEnhanced:
    """Test the enhanced FCC lookup functionality"""

    def test_state_name_mapping(self, app):
        """Test that US state names are correctly mapped to abbreviations"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            # Check the state mapping dictionary exists and has expected entries
            assert EpgMatchRulesService.US_STATE_NAMES["MONTANA"] == "MT"
            assert EpgMatchRulesService.US_STATE_NAMES["CALIFORNIA"] == "CA"
            assert EpgMatchRulesService.US_STATE_NAMES["NEW YORK"] == "NY"
            assert EpgMatchRulesService.US_STATE_NAMES["TEXAS"] == "TX"

    def test_fcc_lookup_with_state_and_channel(self, app):
        """Test FCC lookup using state name and channel number"""
        from models import FccFacility, FccMatchNetwork, FccMatchStrategy
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            # Clear the cache to ensure our test data is used
            clear_fcc_pattern_cache()

            # Create a test FCC facility
            facility = FccFacility(
                facility_id=12345,
                callsign="KTEST-TV",
                service_code="DTV",
                community_city="TESTVILLE",
                community_state="MT",
                tv_virtual_channel="13",
                channel="13",
                network_affiliation="NBC",
                nielsen_dma="Test DMA",
                active=True,
            )
            db.session.add(facility)

            # Create NBC network configuration
            network = FccMatchNetwork(
                name="NBC",
                display_name="NBC",
                fcc_affiliation_pattern="%NBC%",
                enabled=True,
                priority=10,
            )
            db.session.add(network)

            # Create a matching strategy for state + channel
            strategy = FccMatchStrategy(
                name="state_channel",
                strategy_type="state_channel",
                description="Match by state and channel",
                require_channel_number=True,
                require_state=True,
                require_city=False,
                enabled=True,
                priority=10,
            )
            db.session.add(strategy)
            db.session.commit()

            # Create a mock channel object
            class MockChannel:
                def __init__(self, name):
                    self.name = name

            channel = MockChannel("US: NBC 13 HD [MONTANA]")
            tags = {"US", "NBC", "HD", "MONTANA"}

            result = EpgMatchRulesService._lookup_fcc_callsign(channel, tags)
            assert result == "KTEST-TV"

            # Clear cache after test
            clear_fcc_pattern_cache()

    def test_fcc_lookup_without_network(self, app):
        """Test that FCC lookup returns None without network tag"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():

            class MockChannel:
                def __init__(self, name):
                    self.name = name

            channel = MockChannel("US: 13 HD [MONTANA]")
            tags = {"US", "HD", "MONTANA"}  # No network tag

            result = EpgMatchRulesService._lookup_fcc_callsign(channel, tags)
            assert result is None


class TestCallsignExtraction:
    """Tests for EPG channel ID callsign extraction"""

    def test_extract_callsign_us_locals_format(self, app):
        """Test extraction from us_locals format like KECI-DT.us_locals1"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            # Format used by US local stations EPG source
            assert EpgMatchRulesService._extract_callsign("KECI-DT.us_locals1") == "KECI-DT"
            assert EpgMatchRulesService._extract_callsign("WHAS.us_locals1") == "WHAS"
            # Non-callsign format (has colon) returns None
            assert EpgMatchRulesService._extract_callsign("MTV2:.Music.Television.HD.us2") is None

    def test_extract_callsign_simple_country_format(self, app):
        """Test extraction from simple CALLSIGN.country format"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            assert EpgMatchRulesService._extract_callsign("WHAS.us") == "WHAS"
            assert EpgMatchRulesService._extract_callsign("KMAX.us") == "KMAX"
            assert EpgMatchRulesService._extract_callsign("AMC.hu") == "AMC"

    def test_extract_callsign_schedules_direct_format(self, app):
        """Test extraction from Schedules Direct format"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            assert EpgMatchRulesService._extract_callsign("I12345.json.schedulesdirect.org") == "12345"
            assert EpgMatchRulesService._extract_callsign("I99999.json.schedulesdirect.org") == "99999"

    def test_extract_callsign_simple(self, app):
        """Test extraction from simple callsign without suffix"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            assert EpgMatchRulesService._extract_callsign("KABC") == "KABC"
            assert EpgMatchRulesService._extract_callsign("WXYZ-TV") == "WXYZ-TV"

    def test_extract_callsign_none(self, app):
        """Test extraction returns None for invalid inputs"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            assert EpgMatchRulesService._extract_callsign(None) is None
            assert EpgMatchRulesService._extract_callsign("") is None


class TestCallsignNormalization:
    """Tests for callsign normalization (removing suffixes like -TV, -DT)"""

    def test_normalize_callsign_tv_suffix(self, app):
        """Test normalization removes -TV suffix"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            assert EpgMatchRulesService._normalize_callsign("KECI-TV") == "KECI"
            assert EpgMatchRulesService._normalize_callsign("WHAS-TV") == "WHAS"

    def test_normalize_callsign_dt_suffix(self, app):
        """Test normalization removes -DT suffix"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            assert EpgMatchRulesService._normalize_callsign("KECI-DT") == "KECI"
            assert EpgMatchRulesService._normalize_callsign("WHAS-DT") == "WHAS"

    def test_normalize_callsign_hd_suffix(self, app):
        """Test normalization removes -HD suffix"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            assert EpgMatchRulesService._normalize_callsign("KECI-HD") == "KECI"

    def test_normalize_callsign_no_suffix(self, app):
        """Test normalization preserves callsigns without suffix"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            assert EpgMatchRulesService._normalize_callsign("KECI") == "KECI"
            assert EpgMatchRulesService._normalize_callsign("WHAS") == "WHAS"

    def test_normalize_callsign_empty(self, app):
        """Test normalization handles empty input"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            assert EpgMatchRulesService._normalize_callsign("") == ""
            assert EpgMatchRulesService._normalize_callsign(None) == ""


class TestFccToEpgCallsignMatching:
    """Tests for matching FCC callsigns (KECI-TV) to EPG callsigns (KECI-DT)"""

    def test_fcc_tv_matches_epg_dt(self, app):
        """Test that FCC's KECI-TV normalizes to match EPG's KECI-DT"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            fcc_callsign = "KECI-TV"
            epg_callsign = "KECI-DT"

            fcc_normalized = EpgMatchRulesService._normalize_callsign(fcc_callsign)
            epg_normalized = EpgMatchRulesService._normalize_callsign(epg_callsign)

            assert fcc_normalized == epg_normalized == "KECI"

    def test_callsign_index_includes_base_callsign(self, app):
        """Test that callsign index includes both full and base callsigns"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            # Create an EPG source and channel
            source = EpgSource(
                name="Test Source",
                source_type="xmltv_url",
                url="http://test.com/epg.xml",
            )
            db.session.add(source)
            db.session.flush()

            epg_channel = EpgChannel(
                channel_id="KECI-DT.us_locals1",
                display_name="KECI-DT",
                source_id=source.id,
            )
            db.session.add(epg_channel)
            db.session.commit()

            # Extract and normalize
            callsign = EpgMatchRulesService._extract_callsign("KECI-DT.us_locals1")
            assert callsign == "KECI-DT"

            base_callsign = EpgMatchRulesService._normalize_callsign(callsign.upper())
            assert base_callsign == "KECI"

            # Both should work for lookup
            # Full match
            assert callsign.upper() == "KECI-DT"
            # Base match for FCC lookup
            fcc_result = "KECI-TV"
            fcc_base = EpgMatchRulesService._normalize_callsign(fcc_result.upper())
            assert fcc_base == base_callsign


class TestParseLocationTag:
    """Tests for parsing location tags to extract city and state"""

    def test_parse_city_with_state_suffix(self, app):
        """Test parsing tags like WICHITA_KS into city and state"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            city, state = EpgMatchRulesService._parse_location_tag("WICHITA_KS")
            assert city == "WICHITA"
            assert state == "KS"

            city, state = EpgMatchRulesService._parse_location_tag("WATERTOWN_NY")
            assert city == "WATERTOWN"
            assert state == "NY"

    def test_parse_state_name_with_underscore(self, app):
        """Test parsing state names like NEW_YORK"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            city, state = EpgMatchRulesService._parse_location_tag("NEW_YORK")
            assert city is None
            assert state == "NY"

            city, state = EpgMatchRulesService._parse_location_tag("NORTH_CAROLINA")
            assert city is None
            assert state == "NC"

    def test_parse_single_word_state_name(self, app):
        """Test parsing single word state names like MONTANA"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            city, state = EpgMatchRulesService._parse_location_tag("MONTANA")
            assert city is None
            assert state == "MT"

            city, state = EpgMatchRulesService._parse_location_tag("CALIFORNIA")
            assert city is None
            assert state == "CA"

    def test_parse_state_abbreviation(self, app):
        """Test parsing 2-letter state abbreviations"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            city, state = EpgMatchRulesService._parse_location_tag("KS")
            assert city is None
            assert state == "KS"

            city, state = EpgMatchRulesService._parse_location_tag("VI")
            assert city is None
            assert state == "VI"  # Virgin Islands

    def test_parse_city_only(self, app):
        """Test parsing city names without state"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            city, state = EpgMatchRulesService._parse_location_tag("BINGHAMTON")
            assert city == "BINGHAMTON"
            assert state is None

            city, state = EpgMatchRulesService._parse_location_tag("WATERTOWN")
            assert city == "WATERTOWN"
            assert state is None

    def test_parse_multi_word_city(self, app):
        """Test parsing multi-word city names"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            city, state = EpgMatchRulesService._parse_location_tag("VIRGIN_ISLANDS")
            assert city == "VIRGIN ISLANDS"
            assert state is None

            city, state = EpgMatchRulesService._parse_location_tag("ST_JOSEPH")
            assert city == "ST JOSEPH"
            assert state is None

    def test_parse_hyphenated_location(self, app):
        """Test parsing hyphenated DMA names like CHICO-READING"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            # Hyphenated without state at end is treated as city
            city, state = EpgMatchRulesService._parse_location_tag("CHICO-READING")
            assert city == "CHICO-READING"
            assert state is None

    def test_parse_empty_input(self, app):
        """Test parsing empty or None input"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            city, state = EpgMatchRulesService._parse_location_tag("")
            assert city is None
            assert state is None

            city, state = EpgMatchRulesService._parse_location_tag(None)
            assert city is None
            assert state is None


class TestDefaultRulesets:
    """Tests for creating default rulesets and exclusion patterns"""

    def test_create_default_epg_match_ruleset(self, client, app):
        """Test creating the default EPG match ruleset"""
        response = client.post("/api/epg-match-rules/create-default")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["name"] == "Default EPG Matching"
        assert data["rule_count"] == 7  # 7 default rules

    def test_create_default_epg_match_ruleset_already_exists(self, client, app):
        """Test creating default ruleset when it already exists"""
        # Create it first
        client.post("/api/epg-match-rules/create-default")
        # Try to create again
        response = client.post("/api/epg-match-rules/create-default")
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "already exists" in data["error"]

    def test_create_default_exclusion_patterns(self, client, app):
        """Test creating default exclusion patterns"""
        response = client.post("/api/epg-match-rules/create-default-exclusions")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["patterns_created"] == 4  # 4 default patterns

    def test_create_default_exclusion_patterns_skip_existing(self, client, app):
        """Test that creating default exclusions skips existing patterns"""
        # Create them first
        client.post("/api/epg-match-rules/create-default-exclusions")
        # Try to create again
        response = client.post("/api/epg-match-rules/create-default-exclusions")
        assert response.status_code == 200
        data = response.get_json()
        assert data["patterns_created"] == 0
        assert data["patterns_skipped"] == 4


class TestMatchTypes:
    """Tests for match type info endpoint"""

    def test_get_match_types(self, client, app):
        """Test getting available match types"""
        response = client.get("/api/epg-match-rules/match-types")
        assert response.status_code == 200
        data = response.get_json()
        assert "match_types" in data
        # Check for some expected match types
        match_type_values = [mt["value"] for mt in data["match_types"]]
        assert "provider_id" in match_type_values
        assert "exact_name" in match_type_values
        assert "fuzzy_name" in match_type_values
        assert "fcc_lookup" in match_type_values


class TestDuplicateRuleset:
    """Tests for duplicating rulesets"""

    def test_duplicate_ruleset(self, client, app, sample_ruleset):
        """Test duplicating a ruleset"""
        with app.app_context():
            # First add a rule to the ruleset
            from models import EpgMatchRule, db

            rule = EpgMatchRule(
                ruleset_id=sample_ruleset.id,
                name="Test Rule",
                description="A test rule",
                match_type="exact_name",
                pattern="ESPN",
                priority=10,
                enabled=True,
            )
            db.session.add(rule)
            db.session.commit()

        response = client.post(f"/api/epg-match-rules/rulesets/{sample_ruleset.id}/duplicate")
        assert response.status_code == 201
        data = response.get_json()
        assert "(Copy)" in data["name"]
        assert data["rule_count"] == 1

    def test_duplicate_ruleset_not_found(self, client, app):
        """Test duplicating a non-existent ruleset"""
        response = client.post("/api/epg-match-rules/rulesets/99999/duplicate")
        assert response.status_code == 404

    def test_duplicate_ruleset_unique_name(self, client, app, sample_ruleset):
        """Test that duplicating creates unique names"""
        # Duplicate twice
        response1 = client.post(f"/api/epg-match-rules/rulesets/{sample_ruleset.id}/duplicate")
        assert response1.status_code == 201
        name1 = response1.get_json()["name"]

        response2 = client.post(f"/api/epg-match-rules/rulesets/{sample_ruleset.id}/duplicate")
        assert response2.status_code == 201
        name2 = response2.get_json()["name"]

        # Names should be different
        assert name1 != name2


class TestNameMappings:
    """Tests for channel name mapping functionality"""

    def test_create_name_mapping(self, client, app):
        """Test creating a channel name mapping"""
        response = client.post(
            "/api/epg-match-rules/name-mappings",
            json={
                "name": "Test Mapping",
                "description": "Maps old name to new name",
                "old_name": "ESPN HD",
                "new_name": "ESPN",
            },
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["name"] == "Test Mapping"
        assert data["old_name"] == "ESPN HD"
        assert data["new_name"] == "ESPN"

    def test_get_name_mappings(self, client, app):
        """Test getting all name mappings"""
        # Create a mapping first
        client.post(
            "/api/epg-match-rules/name-mappings",
            json={"name": "Test", "old_name": "Old", "new_name": "New"},
        )

        response = client.get("/api/epg-match-rules/name-mappings")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_name_mapping_by_id(self, client, app):
        """Test getting a specific name mapping"""
        # Create a mapping first
        create_response = client.post(
            "/api/epg-match-rules/name-mappings",
            json={"name": "Test", "old_name": "Old", "new_name": "New"},
        )
        mapping_id = create_response.get_json()["id"]

        response = client.get(f"/api/epg-match-rules/name-mappings/{mapping_id}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == mapping_id

    def test_update_name_mapping(self, client, app):
        """Test updating a name mapping"""
        # Create a mapping first
        create_response = client.post(
            "/api/epg-match-rules/name-mappings",
            json={"name": "Test", "old_name": "Old", "new_name": "New"},
        )
        mapping_id = create_response.get_json()["id"]

        response = client.put(
            f"/api/epg-match-rules/name-mappings/{mapping_id}",
            json={"new_name": "Updated New", "priority": 50},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["new_name"] == "Updated New"
        assert data["priority"] == 50

    def test_delete_name_mapping(self, client, app):
        """Test deleting a name mapping"""
        # Create a mapping first
        create_response = client.post(
            "/api/epg-match-rules/name-mappings",
            json={"name": "Test", "old_name": "Old", "new_name": "New"},
        )
        mapping_id = create_response.get_json()["id"]

        response = client.delete(f"/api/epg-match-rules/name-mappings/{mapping_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/api/epg-match-rules/name-mappings/{mapping_id}")
        assert get_response.status_code == 404


class TestNameMappingPreview:
    """Tests for channel name mapping preview"""

    def test_preview_name_mapping_empty_pattern(self, client, app):
        """Test preview with empty pattern returns error"""
        response = client.post("/api/epg-match-rules/name-mappings/preview", json={})
        assert response.status_code == 200
        data = response.get_json()
        assert data["total_count"] == 0
        assert "old_name is required" in data.get("error", "")

    def test_preview_name_mapping_invalid_regex(self, client, app):
        """Test preview with invalid regex"""
        response = client.post(
            "/api/epg-match-rules/name-mappings/preview",
            json={"old_name": "[invalid", "new_name": "test", "match_type": "regex"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "Invalid regex" in data.get("error", "")

    def test_preview_name_mapping_contains(self, client, app, sample_account):
        """Test preview with contains match type"""
        with app.app_context():
            from models import Channel, db

            # Create a test channel
            channel = Channel(
                account_id=sample_account.id,
                stream_id=123,
                name="ESPN HD Sports",
                cleaned_name="ESPN HD Sports",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.post(
            "/api/epg-match-rules/name-mappings/preview",
            json={
                "old_name": "HD",
                "new_name": "",
                "match_type": "contains",
                "case_sensitive": False,
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        # Should match the channel
        assert data["total_count"] >= 1

    def test_preview_name_mapping_exact(self, client, app, sample_account):
        """Test preview with exact match type"""
        with app.app_context():
            from models import Channel, db

            channel = Channel(
                account_id=sample_account.id,
                stream_id=124,
                name="CNN",
                cleaned_name="CNN",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.post(
            "/api/epg-match-rules/name-mappings/preview",
            json={
                "old_name": "CNN",
                "new_name": "CNN News",
                "match_type": "exact",
                "case_sensitive": False,
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["total_count"] >= 1
        # Check the transformation
        if data["matches"]:
            assert data["matches"][0]["transformed_name"] == "CNN News"

    def test_preview_name_mapping_prefix(self, client, app, sample_account):
        """Test preview with prefix match type"""
        with app.app_context():
            from models import Channel, db

            channel = Channel(
                account_id=sample_account.id,
                stream_id=125,
                name="HBO Max",
                cleaned_name="HBO Max",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.post(
            "/api/epg-match-rules/name-mappings/preview",
            json={
                "old_name": "HBO",
                "new_name": "HBO+",
                "match_type": "prefix",
                "case_sensitive": False,
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["total_count"] >= 1

    def test_preview_name_mapping_suffix(self, client, app, sample_account):
        """Test preview with suffix match type"""
        with app.app_context():
            from models import Channel, db

            channel = Channel(
                account_id=sample_account.id,
                stream_id=126,
                name="Sports HD",
                cleaned_name="Sports HD",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.post(
            "/api/epg-match-rules/name-mappings/preview",
            json={
                "old_name": "HD",
                "new_name": "",
                "match_type": "suffix",
                "case_sensitive": False,
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["total_count"] >= 1

    def test_preview_name_mapping_regex(self, client, app, sample_account):
        """Test preview with regex match type"""
        with app.app_context():
            from models import Channel, db

            channel = Channel(
                account_id=sample_account.id,
                stream_id=127,
                name="ABC 4K Sports",
                cleaned_name="ABC 4K Sports",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.post(
            "/api/epg-match-rules/name-mappings/preview",
            json={
                "old_name": r"\s*4K\s*",
                "new_name": " ",
                "match_type": "regex",
                "case_sensitive": False,
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["total_count"] >= 1


class TestExclusionPreviewExtended:
    """Additional tests for exclusion pattern preview"""

    def test_preview_exclusion_category_name(self, client, app, sample_account):
        """Test exclusion preview for category_name pattern type"""
        with app.app_context():
            from models import Category, Channel, db

            category = Category(
                account_id=sample_account.id,
                category_id=1,
                category_name="PPV Sports",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=sample_account.id,
                stream_id=200,
                name="Big Fight",
                cleaned_name="Big Fight",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.post(
            "/api/epg-match-rules/exclusions/preview",
            json={
                "pattern_type": "category_name",
                "pattern": "PPV",
                "is_regex": False,
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["total_count"] >= 1

    def test_preview_exclusion_channel_name_regex(self, client, app, sample_account):
        """Test exclusion preview with channel_name and regex"""
        with app.app_context():
            from models import Channel, db

            channel = Channel(
                account_id=sample_account.id,
                stream_id=201,
                name="PPV Event 123",
                cleaned_name="PPV Event 123",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.post(
            "/api/epg-match-rules/exclusions/preview",
            json={
                "pattern_type": "channel_name",
                "pattern": r"PPV\s+Event\s+\d+",
                "is_regex": True,
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["total_count"] >= 1


class TestRulePreviewExtended:
    """Additional tests for rule pattern preview"""

    def test_preview_rule_category_pattern(self, client, app, sample_account):
        """Test rule preview with category_pattern"""
        with app.app_context():
            from models import Category, Channel, db

            category = Category(
                account_id=sample_account.id,
                category_id=2,
                category_name="US Sports",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=sample_account.id,
                stream_id=300,
                name="ESPN",
                cleaned_name="ESPN",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.post(
            "/api/epg-match-rules/rules/preview",
            json={
                "match_type": "exact_name",
                "source": "cleaned_name",
                "pattern": "ESPN",
                "category_pattern": "Sports",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["total_count"] >= 1

    def test_preview_rule_with_exclude_category(self, client, app, sample_account):
        """Test rule preview with category_exclude_pattern"""
        with app.app_context():
            from models import Category, Channel, db

            category = Category(
                account_id=sample_account.id,
                category_id=3,
                category_name="UK Sports",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=sample_account.id,
                stream_id=301,
                name="ESPN UK",
                cleaned_name="ESPN UK",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.post(
            "/api/epg-match-rules/rules/preview",
            json={
                "match_type": "exact_name",
                "source": "cleaned_name",
                "pattern": "ESPN UK",
                "category_exclude_pattern": "PPV",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        # Should match - category is "UK Sports", not PPV
        assert data["total_count"] >= 1


class TestChannelNameMappingsService:
    """Tests for channel name mapping service methods"""

    def test_apply_exact_mapping(self, app):
        """Test applying exact channel name mapping"""
        from services.epg_match_rules_service import CachedChannelNameMapping, EpgMatchRulesService

        with app.app_context():
            mapping = CachedChannelNameMapping(
                id=1,
                name="Fox to FOX",
                old_name="Fox News",
                new_name="FOX News Channel",
                match_type="exact",
                case_sensitive=False,
            )

            result, mapping_name = EpgMatchRulesService.apply_channel_name_mappings("Fox News", [mapping])
            assert result == "FOX News Channel"
            assert mapping_name == "Fox to FOX"

    def test_apply_exact_mapping_case_sensitive(self, app):
        """Test case sensitive exact mapping"""
        from services.epg_match_rules_service import CachedChannelNameMapping, EpgMatchRulesService

        with app.app_context():
            mapping = CachedChannelNameMapping(
                id=1,
                name="Case Sensitive",
                old_name="ESPN",
                new_name="ESPN HD",
                match_type="exact",
                case_sensitive=True,
            )

            # Should not match different case
            result, _ = EpgMatchRulesService.apply_channel_name_mappings("espn", [mapping])
            assert result == "espn"  # Unchanged

            # Should match exact case
            result, name = EpgMatchRulesService.apply_channel_name_mappings("ESPN", [mapping])
            assert result == "ESPN HD"
            assert name == "Case Sensitive"

    def test_apply_contains_mapping(self, app):
        """Test applying contains channel name mapping"""
        from services.epg_match_rules_service import CachedChannelNameMapping, EpgMatchRulesService

        with app.app_context():
            mapping = CachedChannelNameMapping(
                id=1,
                name="Remove HD",
                old_name=" HD",
                new_name="",
                match_type="contains",
                case_sensitive=False,
            )

            result, _ = EpgMatchRulesService.apply_channel_name_mappings("ESPN HD Channel", [mapping])
            assert result == "ESPN Channel"

    def test_apply_prefix_mapping(self, app):
        """Test applying prefix channel name mapping"""
        from services.epg_match_rules_service import CachedChannelNameMapping, EpgMatchRulesService

        with app.app_context():
            mapping = CachedChannelNameMapping(
                id=1,
                name="Remove US prefix",
                old_name="US| ",
                new_name="",
                match_type="prefix",
                case_sensitive=False,
            )

            result, _ = EpgMatchRulesService.apply_channel_name_mappings("US| ESPN", [mapping])
            assert result == "ESPN"

    def test_apply_suffix_mapping(self, app):
        """Test applying suffix channel name mapping"""
        from services.epg_match_rules_service import CachedChannelNameMapping, EpgMatchRulesService

        with app.app_context():
            mapping = CachedChannelNameMapping(
                id=1,
                name="Remove SD suffix",
                old_name=" SD",
                new_name=" HD",
                match_type="suffix",
                case_sensitive=False,
            )

            result, _ = EpgMatchRulesService.apply_channel_name_mappings("ESPN SD", [mapping])
            assert result == "ESPN HD"

    def test_apply_regex_mapping(self, app):
        """Test applying regex channel name mapping"""
        from services.epg_match_rules_service import CachedChannelNameMapping, EpgMatchRulesService

        with app.app_context():
            mapping = CachedChannelNameMapping(
                id=1,
                name="Remove 4K markers",
                old_name=r"\s*\[?4K\]?\s*",
                new_name=" ",
                match_type="regex",
                case_sensitive=False,
            )

            result, _ = EpgMatchRulesService.apply_channel_name_mappings("ESPN [4K] Sports", [mapping])
            assert "4K" not in result

    def test_apply_mapping_empty_name(self, app):
        """Test that empty name returns unchanged"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            result, mapping = EpgMatchRulesService.apply_channel_name_mappings("", [])
            assert result == ""
            assert mapping is None

    def test_apply_mapping_invalid_regex(self, app):
        """Test that invalid regex is skipped gracefully"""
        from services.epg_match_rules_service import CachedChannelNameMapping, EpgMatchRulesService

        with app.app_context():
            mapping = CachedChannelNameMapping(
                id=1,
                name="Invalid Regex",
                old_name="[invalid",  # Invalid regex
                new_name="test",
                match_type="regex",
                case_sensitive=False,
            )

            # Should not raise, just skip the invalid pattern
            result, _ = EpgMatchRulesService.apply_channel_name_mappings("Some Channel", [mapping])
            assert result == "Some Channel"


class TestNetworkDetection:
    """Tests for network detection from tags"""

    def test_detect_network_direct_tag(self, app):
        """Test detecting network from direct tag match"""
        from models import FccMatchNetwork
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            clear_fcc_pattern_cache()

            # Create a network
            network = FccMatchNetwork(
                name="NBC",
                display_name="NBC",
                fcc_affiliation_pattern="%NBC%",
                enabled=True,
                priority=10,
            )
            db.session.add(network)
            db.session.commit()

            result = EpgMatchRulesService.detect_network_from_tags({"NBC", "HD", "US"})
            assert result is not None
            assert result.name == "NBC"

            clear_fcc_pattern_cache()

    def test_detect_network_tag_pattern(self, app):
        """Test detecting network from tag patterns"""
        import json

        from models import FccMatchNetwork
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            clear_fcc_pattern_cache()

            # Create a network with tag patterns
            network = FccMatchNetwork(
                name="FOX",
                display_name="FOX",
                fcc_affiliation_pattern="%FOX%",
                tag_patterns=json.dumps(["FOXNEWS", "FOX-HD"]),
                enabled=True,
                priority=10,
            )
            db.session.add(network)
            db.session.commit()

            result = EpgMatchRulesService.detect_network_from_tags({"FOXNEWS", "HD"})
            assert result is not None
            assert result.name == "FOX"

            clear_fcc_pattern_cache()

    def test_detect_network_no_match(self, app):
        """Test that no network is detected when no match"""
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            clear_fcc_pattern_cache()

            result = EpgMatchRulesService.detect_network_from_tags({"UNKNOWN", "HD", "US"})
            assert result is None


class TestExclusionPatternTypes:
    """Tests for different exclusion pattern types"""

    def test_exclude_by_channel_name_regex(self, app):
        """Test excluding channel by name with regex pattern"""
        from models import Account, Category, Channel, EpgExclusionPattern
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            clear_fcc_pattern_cache()

            account = Account(
                name="Exclusion Test Account",
                server="http://test.server.com",
                username="extest",
                password="testpass",
            )
            db.session.add(account)
            db.session.commit()

            pattern = EpgExclusionPattern(
                name="PPV Regex",
                pattern_type="channel_name",
                pattern=r"PPV\s*\d+",
                is_regex=True,
                enabled=True,
                priority=10,
            )
            db.session.add(pattern)

            category = Category(
                account_id=account.id,
                category_id=1,
                category_name="Sports",
            )
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="exc1",
                name="PPV 123",
                category_id=category.id,
            )
            db.session.add(channel)
            db.session.commit()

            should_exclude, name, hide = EpgMatchRulesService.should_exclude_channel(channel)
            assert should_exclude is True
            assert name == "PPV Regex"

            clear_fcc_pattern_cache()

    def test_exclude_by_tag(self, app):
        """Test excluding channel by tag"""
        from models import Account, Category, Channel, ChannelTag, EpgExclusionPattern, Tag
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            clear_fcc_pattern_cache()

            account = Account(
                name="Tag Exclusion Test",
                server="http://test.server.com",
                username="tagtest",
                password="testpass",
            )
            db.session.add(account)
            db.session.commit()

            pattern = EpgExclusionPattern(
                name="PPV Tag",
                pattern_type="tag",
                pattern="PPV",
                is_regex=False,
                enabled=True,
                priority=10,
            )
            db.session.add(pattern)

            category = Category(
                account_id=account.id,
                category_id=1,
                category_name="Sports",
            )
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="tagch1",
                name="Some Event",
                category_id=category.id,
            )
            db.session.add(channel)
            db.session.commit()

            # Create PPV tag
            tag = Tag(name="PPV")
            db.session.add(tag)
            db.session.commit()

            # Associate tag with channel
            channel_tag = ChannelTag(account_id=account.id, stream_id="tagch1", tag_id=tag.id)
            db.session.add(channel_tag)
            db.session.commit()

            should_exclude, name, hide = EpgMatchRulesService.should_exclude_channel(channel)
            assert should_exclude is True
            assert name == "PPV Tag"

            clear_fcc_pattern_cache()


class TestNormalizeName:
    """Tests for name normalization"""

    def test_normalize_lowercase(self, app):
        """Test that names are lowercased"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            result = EpgMatchRulesService._normalize_name("ESPN HD")
            assert result == "espn hd"

    def test_normalize_removes_special_chars(self, app):
        """Test that special characters are removed"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            result = EpgMatchRulesService._normalize_name("ESPN-HD!")
            assert result == "espnhd"

    def test_normalize_collapses_whitespace(self, app):
        """Test that multiple spaces are collapsed"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            result = EpgMatchRulesService._normalize_name("ESPN   HD   Sports")
            assert result == "espn hd sports"

    def test_normalize_empty_string(self, app):
        """Test normalizing empty string"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            result = EpgMatchRulesService._normalize_name("")
            assert result == ""


class TestCachedDataclasses:
    """Tests for cached dataclass creation"""

    def test_cached_fcc_network_from_orm(self, app):
        """Test creating CachedFccNetwork from ORM object"""
        import json

        from models import FccMatchNetwork
        from services.epg_match_rules_service import CachedFccNetwork

        with app.app_context():
            network = FccMatchNetwork(
                name="NBC",
                display_name="NBC",
                fcc_affiliation_pattern="%NBC%",
                tag_patterns=json.dumps(["NBC-HD", "NBCSPORTS"]),
                enabled=True,
                priority=10,
            )
            db.session.add(network)
            db.session.commit()

            cached = CachedFccNetwork.from_orm(network)
            assert cached.name == "NBC"
            assert cached.fcc_affiliation_pattern == "%NBC%"
            assert cached.tag_patterns == ["NBC-HD", "NBCSPORTS"]

    def test_cached_channel_name_mapping_from_orm(self, app):
        """Test creating CachedChannelNameMapping from ORM object"""
        from models import EpgChannelNameMapping
        from services.epg_match_rules_service import CachedChannelNameMapping

        with app.app_context():
            mapping = EpgChannelNameMapping(
                name="Test Mapping",
                old_name="Old Channel",
                new_name="New Channel",
                match_type="exact",
                case_sensitive=True,
                enabled=True,
                priority=10,
            )
            db.session.add(mapping)
            db.session.commit()

            cached = CachedChannelNameMapping.from_orm(mapping)
            assert cached.name == "Test Mapping"
            assert cached.old_name == "Old Channel"
            assert cached.new_name == "New Channel"
            assert cached.match_type == "exact"
            assert cached.case_sensitive is True

    def test_cached_channel_pattern_from_orm(self, app):
        """Test creating CachedChannelPattern from ORM object"""
        import json

        from models import FccMatchChannelPattern
        from services.epg_match_rules_service import CachedChannelPattern

        with app.app_context():
            pattern = FccMatchChannelPattern(
                name="Network Number",
                pattern=r"(\d{1,2})\s*(?:HD|SD)",
                capture_group=1,
                networks=json.dumps(["NBC", "ABC"]),
                enabled=True,
                priority=10,
            )
            db.session.add(pattern)
            db.session.commit()

            cached = CachedChannelPattern.from_orm(pattern)
            assert cached.name == "Network Number"
            assert cached.capture_group == 1
            assert cached.networks == ["NBC", "ABC"]

    def test_cached_location_pattern_from_orm(self, app):
        """Test creating CachedLocationPattern from ORM object"""
        from models import FccMatchLocationPattern
        from services.epg_match_rules_service import CachedLocationPattern

        with app.app_context():
            pattern = FccMatchLocationPattern(
                name="City State",
                pattern=r"\[([A-Z]+),\s*([A-Z]{2})\]",
                extract_city=True,
                extract_state=True,
                city_group=1,
                state_group=2,
                enabled=True,
                priority=10,
            )
            db.session.add(pattern)
            db.session.commit()

            cached = CachedLocationPattern.from_orm(pattern)
            assert cached.name == "City State"
            assert cached.extract_city is True
            assert cached.extract_state is True
            assert cached.city_group == 1
            assert cached.state_group == 2

    def test_cached_exclusion_pattern_from_orm(self, app):
        """Test creating CachedExclusionPattern from ORM object"""
        from models import EpgExclusionPattern
        from services.epg_match_rules_service import CachedExclusionPattern

        with app.app_context():
            pattern = EpgExclusionPattern(
                name="PPV Pattern",
                pattern_type="category_name",
                pattern="PPV",
                is_regex=False,
                hide_channel=True,
                enabled=True,
                priority=10,
            )
            db.session.add(pattern)
            db.session.commit()

            cached = CachedExclusionPattern.from_orm(pattern)
            assert cached.name == "PPV Pattern"
            assert cached.pattern_type == "category_name"
            assert cached.pattern == "PPV"
            assert cached.is_regex is False
            assert cached.hide_channel is True


class TestCacheLoading:
    """Tests for cache loading methods"""

    def test_get_quality_tags_from_db(self, app):
        """Test loading quality tags from database"""
        from models import QualityTag
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            clear_fcc_pattern_cache()

            # Create some quality tags
            tag1 = QualityTag(tag_name="HD", enabled=True, exclude_from_location=True)
            tag2 = QualityTag(tag_name="4K", enabled=True, exclude_from_location=True)
            db.session.add_all([tag1, tag2])
            db.session.commit()

            tags = EpgMatchRulesService.get_quality_tags()
            assert "HD" in tags
            assert "4K" in tags

            clear_fcc_pattern_cache()

    def test_get_country_tags_from_db(self, app):
        """Test loading country tags from database"""
        from models import CountryTag
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            clear_fcc_pattern_cache()

            # Create some country tags
            tag1 = CountryTag(tag_name="US", enabled=True, exclude_from_location=True)
            tag2 = CountryTag(tag_name="UK", enabled=True, exclude_from_location=True)
            db.session.add_all([tag1, tag2])
            db.session.commit()

            tags = EpgMatchRulesService.get_country_tags()
            assert "US" in tags
            assert "UK" in tags

            clear_fcc_pattern_cache()

    def test_get_callsign_suffixes_from_db(self, app):
        """Test loading callsign suffixes from database"""
        from models import CallsignSuffix
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            clear_fcc_pattern_cache()

            # Create some callsign suffixes
            s1 = CallsignSuffix(suffix="-TV", enabled=True, try_on_miss=True, priority=1)
            s2 = CallsignSuffix(suffix="-DT", enabled=True, try_on_miss=True, priority=2)
            db.session.add_all([s1, s2])
            db.session.commit()

            suffixes = EpgMatchRulesService.get_callsign_suffixes()
            assert "-TV" in suffixes
            assert "-DT" in suffixes

            clear_fcc_pattern_cache()

    def test_get_country_suffix_mappings_from_db(self, app):
        """Test loading country suffix mappings from database"""
        import json

        from models import EpgCountrySuffix
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            clear_fcc_pattern_cache()

            # Create a country suffix mapping
            mapping = EpgCountrySuffix(
                country_code="US",
                country_name="United States",
                epg_suffixes=json.dumps([".us", ".us2"]),
                enabled=True,
                priority=1,
            )
            db.session.add(mapping)
            db.session.commit()

            mappings = EpgMatchRulesService.get_country_suffix_mappings()
            assert "US" in mappings
            assert ".us" in mappings["US"]

            clear_fcc_pattern_cache()


class TestGetSourceValue:
    """Tests for _get_source_value helper method"""

    def test_get_channel_name(self, app):
        """Test getting channel_name source"""
        from services.epg_match_rules_service import EpgMatchRule, EpgMatchRulesService

        with app.app_context():
            # Create a minimal mock channel
            class MockChannel:
                name = "ESPN HD"
                cleaned_name = "ESPN"
                category = None
                epg_channel_id = "ESPN.us"

            channel = MockChannel()
            result = EpgMatchRulesService._get_source_value(channel, EpgMatchRule.SOURCE_CHANNEL_NAME)
            assert result == "ESPN HD"

    def test_get_cleaned_name(self, app):
        """Test getting cleaned_name source"""
        from services.epg_match_rules_service import EpgMatchRule, EpgMatchRulesService

        with app.app_context():

            class MockChannel:
                name = "ESPN HD"
                cleaned_name = "ESPN"
                category = None
                epg_channel_id = "ESPN.us"

            channel = MockChannel()
            result = EpgMatchRulesService._get_source_value(channel, EpgMatchRule.SOURCE_CLEANED_NAME)
            assert result == "ESPN"

    def test_get_epg_channel_id(self, app):
        """Test getting epg_channel_id source"""
        from services.epg_match_rules_service import EpgMatchRule, EpgMatchRulesService

        with app.app_context():

            class MockChannel:
                name = "ESPN HD"
                cleaned_name = "ESPN"
                category = None
                epg_channel_id = "ESPN.us"

            channel = MockChannel()
            result = EpgMatchRulesService._get_source_value(channel, EpgMatchRule.SOURCE_EPG_CHANNEL_ID)
            assert result == "ESPN.us"

    def test_get_category_name(self, app):
        """Test getting category_name source"""
        from services.epg_match_rules_service import EpgMatchRule, EpgMatchRulesService

        with app.app_context():

            class MockCategory:
                category_name = "Sports"

            class MockChannel:
                name = "ESPN HD"
                cleaned_name = "ESPN"
                category = MockCategory()
                epg_channel_id = "ESPN.us"

            channel = MockChannel()
            result = EpgMatchRulesService._get_source_value(channel, EpgMatchRule.SOURCE_CATEGORY_NAME)
            assert result == "Sports"

    def test_get_source_with_name_mapping(self, app):
        """Test getting source value with name mapping applied"""
        from services.epg_match_rules_service import CachedChannelNameMapping, EpgMatchRule, EpgMatchRulesService

        with app.app_context():

            class MockChannel:
                name = "Fox News"
                cleaned_name = "Fox News"
                category = None
                epg_channel_id = None

            mapping = CachedChannelNameMapping(
                id=1,
                name="Fox to FOX",
                old_name="Fox News",
                new_name="FOX News Channel",
                match_type="exact",
                case_sensitive=False,
            )

            channel = MockChannel()
            result = EpgMatchRulesService._get_source_value(channel, EpgMatchRule.SOURCE_CHANNEL_NAME, [mapping])
            assert result == "FOX News Channel"


class TestGetChannelTags:
    """Tests for _get_channel_tags helper"""

    def test_get_channel_tags(self, app):
        """Test getting tags for a channel"""
        from models import Account, ChannelTag, Tag
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            # Create account
            account = Account(
                name="Tag Test Account",
                server="test.server.com",
                username="tagtest",
                password="testpass",
            )
            db.session.add(account)
            db.session.commit()

            # Create tags
            tag1 = Tag(name="HD")
            tag2 = Tag(name="SPORTS")
            db.session.add_all([tag1, tag2])
            db.session.commit()

            # Associate tags with channel
            channel_tag1 = ChannelTag(account_id=account.id, stream_id="test123", tag_id=tag1.id)
            channel_tag2 = ChannelTag(account_id=account.id, stream_id="test123", tag_id=tag2.id)
            db.session.add_all([channel_tag1, channel_tag2])
            db.session.commit()

            # Get tags
            tags = EpgMatchRulesService._get_channel_tags(account.id, "test123")
            assert "HD" in tags
            assert "SPORTS" in tags

    def test_get_channel_tags_none(self, app):
        """Test getting tags for channel with no tags"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            tags = EpgMatchRulesService._get_channel_tags(999999, "nonexistent")
            assert tags == set()


class TestFccStrategies:
    """Tests for FCC matching strategies"""

    def test_get_fcc_strategies(self, app):
        """Test getting FCC matching strategies from DB"""
        from models import FccMatchStrategy
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            clear_fcc_pattern_cache()

            # Create a strategy
            strategy = FccMatchStrategy(
                name="Test Strategy",
                strategy_type="state_channel",
                description="Test",
                require_channel_number=True,
                require_state=True,
                require_city=False,
                enabled=True,
                priority=10,
            )
            db.session.add(strategy)
            db.session.commit()

            strategies = EpgMatchRulesService.get_fcc_strategies()
            assert len(strategies) >= 1
            assert any(s.name == "Test Strategy" for s in strategies)

            clear_fcc_pattern_cache()

    def test_get_fcc_location_patterns(self, app):
        """Test getting FCC location patterns from DB"""
        from models import FccMatchLocationPattern
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            clear_fcc_pattern_cache()

            # Create a location pattern
            pattern = FccMatchLocationPattern(
                name="Bracket City State",
                pattern=r"\[([A-Z]+),\s*([A-Z]{2})\]",
                extract_city=True,
                extract_state=True,
                city_group=1,
                state_group=2,
                enabled=True,
                priority=10,
            )
            db.session.add(pattern)
            db.session.commit()

            patterns = EpgMatchRulesService.get_fcc_location_patterns()
            assert len(patterns) >= 1
            assert any(p.name == "Bracket City State" for p in patterns)

            clear_fcc_pattern_cache()

    def test_get_network_names(self, app):
        """Test getting network names set"""
        from models import FccMatchNetwork
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            clear_fcc_pattern_cache()

            # Create networks
            net1 = FccMatchNetwork(
                name="NBC",
                display_name="NBC",
                fcc_affiliation_pattern="%NBC%",
                enabled=True,
                priority=10,
            )
            net2 = FccMatchNetwork(
                name="ABC",
                display_name="ABC",
                fcc_affiliation_pattern="%ABC%",
                enabled=True,
                priority=20,
            )
            db.session.add_all([net1, net2])
            db.session.commit()

            names = EpgMatchRulesService.get_network_names()
            assert "NBC" in names
            assert "ABC" in names

            clear_fcc_pattern_cache()


class TestExclusionPatternCaching:
    """Tests for exclusion pattern caching"""

    def test_get_enabled_exclusion_patterns(self, app):
        """Test getting enabled exclusion patterns with caching"""
        from models import EpgExclusionPattern
        from services.epg_match_rules_service import EpgMatchRulesService, clear_fcc_pattern_cache

        with app.app_context():
            clear_fcc_pattern_cache()

            # Create exclusion patterns
            p1 = EpgExclusionPattern(
                name="PPV Pattern",
                pattern_type="category_name",
                pattern="PPV",
                is_regex=False,
                enabled=True,
                priority=10,
            )
            p2 = EpgExclusionPattern(
                name="Adult Pattern",
                pattern_type="channel_name",
                pattern="XXX",
                is_regex=False,
                enabled=True,
                priority=20,
            )
            db.session.add_all([p1, p2])
            db.session.commit()

            patterns = EpgMatchRulesService.get_enabled_exclusion_patterns()
            assert len(patterns) >= 2
            assert patterns[0].name == "PPV Pattern"  # Lower priority first

            clear_fcc_pattern_cache()


class TestApplyMatchRule:
    """Tests for _apply_match_rule method"""

    def test_apply_match_rule_skip_action(self, app):
        """Test match rule with skip action returns None"""
        from models import Category, EpgChannel, EpgMatchRule, EpgSource
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            # Create account and channel
            account = Account(name="Test", server="test.com")
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="News",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="100",
                name="Test Channel",
                cleaned_name="Test Channel",
                category_id=category.id,
            )
            db.session.add(channel)

            # Create EPG source and channels
            source = EpgSource(name="Test", source_type="xmltv_url", url="http://test.com")
            db.session.add(source)
            db.session.flush()

            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="test.us",
                display_name="Test",
            )
            db.session.add(epg_channel)
            db.session.commit()

            # Create rule with skip action
            rule = EpgMatchRule(
                ruleset_id=1,
                name="Skip Rule",
                match_type="provider_id",
                action="skip",
            )

            result = EpgMatchRulesService._apply_match_rule(
                channel=channel,
                rule=rule,
                epg_channels=[epg_channel],
                epg_by_id={"test.us": epg_channel},
                epg_by_name={"test": epg_channel},
                epg_by_callsign={},
                channel_tags=set(),
                country_tags=set(),
            )
            assert result is None

    def test_apply_match_rule_fallback_action(self, app):
        """Test match rule with fallback action"""
        from models import Category, EpgChannel, EpgMatchRule, EpgSource
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            account = Account(name="Test", server="test.com")
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="News",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="100",
                name="Test Channel",
                cleaned_name="Test Channel",
                category_id=category.id,
            )
            db.session.add(channel)

            source = EpgSource(name="Test", source_type="xmltv_url", url="http://test.com")
            db.session.add(source)
            db.session.flush()

            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="fallback.us",
                display_name="Fallback",
            )
            db.session.add(epg_channel)
            db.session.commit()

            rule = EpgMatchRule(
                ruleset_id=1,
                name="Fallback Rule",
                match_type="provider_id",
                action="use_fallback",
                fallback_epg_id="fallback.us",
            )

            result = EpgMatchRulesService._apply_match_rule(
                channel=channel,
                rule=rule,
                epg_channels=[epg_channel],
                epg_by_id={"fallback.us": epg_channel},
                epg_by_name={},
                epg_by_callsign={},
                channel_tags=set(),
                country_tags=set(),
            )
            assert result is not None
            assert result[0].channel_id == "fallback.us"
            assert result[1] == 1.0

    def test_apply_match_rule_callsign_tag(self, app):
        """Test match rule with callsign_tag match type"""
        from models import Category, EpgChannel, EpgMatchRule, EpgSource
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            account = Account(name="Test", server="test.com")
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="News",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="100",
                name="KABC News",
                cleaned_name="KABC News",
                category_id=category.id,
            )
            db.session.add(channel)

            source = EpgSource(name="Test", source_type="xmltv_url", url="http://test.com")
            db.session.add(source)
            db.session.flush()

            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="kabc.us",
                display_name="KABC",
            )
            db.session.add(epg_channel)
            db.session.commit()

            rule = EpgMatchRule(
                ruleset_id=1,
                name="Callsign Tag Rule",
                match_type="callsign_tag",
            )

            # Channel has KABC as a tag
            result = EpgMatchRulesService._apply_match_rule(
                channel=channel,
                rule=rule,
                epg_channels=[epg_channel],
                epg_by_id={},
                epg_by_name={},
                epg_by_callsign={"KABC": epg_channel},
                channel_tags={"KABC"},  # Callsign-like tag
                country_tags=set(),
            )
            assert result is not None
            assert result[0].display_name == "KABC"
            assert result[1] == 0.95

    def test_apply_match_rule_callsign_from_name(self, app):
        """Test match rule with callsign_name match type"""
        from models import Category, EpgChannel, EpgMatchRule, EpgSource
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            account = Account(name="Test", server="test.com")
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="News",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="100",
                name="WABC News Channel",
                cleaned_name="WABC News Channel",
                category_id=category.id,
            )
            db.session.add(channel)

            source = EpgSource(name="Test", source_type="xmltv_url", url="http://test.com")
            db.session.add(source)
            db.session.flush()

            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="wabc.us",
                display_name="WABC",
            )
            db.session.add(epg_channel)
            db.session.commit()

            rule = EpgMatchRule(
                ruleset_id=1,
                name="Callsign Name Rule",
                match_type="callsign_name",
                source="channel_name",
            )

            result = EpgMatchRulesService._apply_match_rule(
                channel=channel,
                rule=rule,
                epg_channels=[epg_channel],
                epg_by_id={},
                epg_by_name={},
                epg_by_callsign={"WABC": epg_channel},
                channel_tags=set(),
                country_tags=set(),
            )
            assert result is not None
            assert result[0].display_name == "WABC"
            assert result[1] == 0.9

    def test_apply_match_rule_fuzzy_name(self, app):
        """Test match rule with fuzzy_name match type"""
        from models import Category, EpgChannel, EpgMatchRule, EpgSource
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            account = Account(name="Test", server="test.com")
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="Sports",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="100",
                name="ESPN Sports Network",
                cleaned_name="ESPN Sports Network",
                category_id=category.id,
            )
            db.session.add(channel)

            source = EpgSource(name="Test", source_type="xmltv_url", url="http://test.com")
            db.session.add(source)
            db.session.flush()

            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="espn.us",
                display_name="ESPN Sports",
            )
            db.session.add(epg_channel)
            db.session.commit()

            rule = EpgMatchRule(
                ruleset_id=1,
                name="Fuzzy Name Rule",
                match_type="fuzzy_name",
                source="cleaned_name",
                min_confidence=0.5,  # Lower threshold for test
            )

            result = EpgMatchRulesService._apply_match_rule(
                channel=channel,
                rule=rule,
                epg_channels=[epg_channel],
                epg_by_id={},
                epg_by_name={"espn sports": epg_channel},
                epg_by_callsign={},
                channel_tags=set(),
                country_tags=set(),
            )
            assert result is not None
            assert result[0].channel_id == "espn.us"

    def test_apply_match_rule_regex(self, app):
        """Test match rule with regex match type"""
        from models import Category, EpgChannel, EpgMatchRule, EpgSource
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            account = Account(name="Test", server="test.com")
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="Sports",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="100",
                name="ID:hbo.us| HBO",
                cleaned_name="ID:hbo.us| HBO",
                category_id=category.id,
            )
            db.session.add(channel)

            source = EpgSource(name="Test", source_type="xmltv_url", url="http://test.com")
            db.session.add(source)
            db.session.flush()

            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="hbo.us",
                display_name="HBO",
            )
            db.session.add(epg_channel)
            db.session.commit()

            rule = EpgMatchRule(
                ruleset_id=1,
                name="Regex Rule",
                match_type="regex",
                source="channel_name",
                pattern=r"ID:([a-z.]+)\|",  # Extract ID from name
            )

            result = EpgMatchRulesService._apply_match_rule(
                channel=channel,
                rule=rule,
                epg_channels=[epg_channel],
                epg_by_id={"hbo.us": epg_channel},
                epg_by_name={},
                epg_by_callsign={},
                channel_tags=set(),
                country_tags=set(),
            )
            assert result is not None
            assert result[0].channel_id == "hbo.us"
            assert result[1] == 0.9

    def test_apply_match_rule_tag_based(self, app):
        """Test match rule with tag_based match type"""
        from models import Category, EpgChannel, EpgMatchRule, EpgSource
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            account = Account(name="Test", server="test.com")
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="Local",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="100",
                name="Local News",
                cleaned_name="Local News",
                category_id=category.id,
            )
            db.session.add(channel)

            source = EpgSource(name="Test", source_type="xmltv_url", url="http://test.com")
            db.session.add(source)
            db.session.flush()

            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="nbc",
                display_name="NBC",
            )
            db.session.add(epg_channel)
            db.session.commit()

            rule = EpgMatchRule(
                ruleset_id=1,
                name="Tag Rule",
                match_type="tag_based",
                pattern=r"^(NBC|CBS|ABC)$",
            )

            result = EpgMatchRulesService._apply_match_rule(
                channel=channel,
                rule=rule,
                epg_channels=[epg_channel],
                epg_by_id={"nbc": epg_channel},
                epg_by_name={},
                epg_by_callsign={},
                channel_tags={"NBC", "LOCAL"},
                country_tags=set(),
            )
            assert result is not None
            assert result[0].channel_id == "nbc"
            assert result[1] == 0.85

    def test_apply_match_rule_category_pattern(self, app):
        """Test match rule with category_pattern match type"""
        from models import Category, EpgChannel, EpgMatchRule, EpgSource
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            account = Account(name="Test", server="test.com")
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="US | Sports",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="100",
                name="ESPN",
                cleaned_name="ESPN",
                category_id=category.id,
            )
            db.session.add(channel)

            source = EpgSource(name="Test", source_type="xmltv_url", url="http://test.com")
            db.session.add(source)
            db.session.flush()

            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="espn.us",
                display_name="ESPN",
            )
            db.session.add(epg_channel)
            db.session.commit()

            rule = EpgMatchRule(
                ruleset_id=1,
                name="Category Pattern Rule",
                match_type="category_pattern",
                pattern=r"US.*Sports",
                source="cleaned_name",
            )

            result = EpgMatchRulesService._apply_match_rule(
                channel=channel,
                rule=rule,
                epg_channels=[epg_channel],
                epg_by_id={},
                epg_by_name={"espn": epg_channel},
                epg_by_callsign={},
                channel_tags=set(),
                country_tags=set(),
            )
            assert result is not None
            assert result[0].channel_id == "espn.us"
            assert result[1] == 0.8

    def test_apply_match_rule_network_fallback(self, app):
        """Test match rule with network_fallback match type"""
        from models import Category, EpgChannel, EpgMatchRule, EpgSource
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            account = Account(name="Test", server="test.com")
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="Local",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="100",
                name="NBC News",
                cleaned_name="NBC News",
                category_id=category.id,
            )
            db.session.add(channel)

            source = EpgSource(name="Test", source_type="xmltv_url", url="http://test.com")
            db.session.add(source)
            db.session.flush()

            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="nbc.us",
                display_name="NBC",
            )
            db.session.add(epg_channel)
            db.session.commit()

            rule = EpgMatchRule(
                ruleset_id=1,
                name="Network Fallback Rule",
                match_type="network_fallback",
            )

            result = EpgMatchRulesService._apply_match_rule(
                channel=channel,
                rule=rule,
                epg_channels=[epg_channel],
                epg_by_id={"nbc.us": epg_channel},
                epg_by_name={},
                epg_by_callsign={},
                channel_tags={"NBC"},  # Has NBC tag
                country_tags=set(),
            )
            assert result is not None
            assert result[0].channel_id == "nbc.us"
            assert result[1] == 0.6


class TestNormalizeCallsign:
    """Tests for _normalize_callsign method"""

    def test_normalize_callsign_with_suffix(self, app):
        """Test normalizing callsigns with common suffixes"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            # Standard suffixes should be removed
            assert EpgMatchRulesService._normalize_callsign("KABC-TV") == "KABC"
            assert EpgMatchRulesService._normalize_callsign("WABC-DT") == "WABC"
            assert EpgMatchRulesService._normalize_callsign("KCBS-HD") == "KCBS"

    def test_normalize_callsign_without_suffix(self, app):
        """Test normalizing callsigns without suffixes"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            assert EpgMatchRulesService._normalize_callsign("KABC") == "KABC"
            assert EpgMatchRulesService._normalize_callsign("WGN") == "WGN"

    def test_normalize_callsign_empty(self, app):
        """Test normalizing empty or None callsigns"""
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            assert EpgMatchRulesService._normalize_callsign("") == ""
            assert EpgMatchRulesService._normalize_callsign(None) == ""


class TestMatchRuleFilters:
    """Tests for match rule filters (category, country, tags)"""

    def test_match_channels_with_category_filter(self, app):
        """Test that match rules with category filter are applied correctly"""
        from models import Category, EpgChannel, EpgMatchRule, EpgMatchRuleSet, EpgSource
        from services.epg_match_rules_service import EpgMatchRulesService

        with app.app_context():
            account = Account(name="Test", server="test.com")
            db.session.add(account)
            db.session.flush()

            category_sports = Category(
                account_id=account.id,
                category_id="1",
                category_name="Sports",
            )
            category_news = Category(
                account_id=account.id,
                category_id="2",
                category_name="News",
            )
            db.session.add_all([category_sports, category_news])
            db.session.flush()

            channel_espn = Channel(
                account_id=account.id,
                stream_id="100",
                name="ESPN",
                cleaned_name="ESPN",
                category_id=category_sports.id,
            )
            channel_cnn = Channel(
                account_id=account.id,
                stream_id="101",
                name="CNN",
                cleaned_name="CNN",
                category_id=category_news.id,
            )
            db.session.add_all([channel_espn, channel_cnn])

            source = EpgSource(name="Test", source_type="xmltv_url", url="http://test.com")
            db.session.add(source)
            db.session.flush()

            epg_espn = EpgChannel(
                source_id=source.id,
                channel_id="espn.us",
                display_name="ESPN",
            )
            db.session.add(epg_espn)
            db.session.commit()

            ruleset = EpgMatchRuleSet(name="Test", enabled=True, priority=10)
            db.session.add(ruleset)
            db.session.flush()

            # Rule only applies to Sports category
            rule = EpgMatchRule(
                ruleset_id=ruleset.id,
                name="Sports Only Rule",
                match_type="exact_name",
                source="cleaned_name",
                category_pattern=r"^Sports$",
                priority=10,
                enabled=True,
            )
            db.session.add(rule)
            db.session.commit()

            # ESPN should match (Sports category)
            result = EpgMatchRulesService._apply_match_rule(
                channel=channel_espn,
                rule=rule,
                epg_channels=[epg_espn],
                epg_by_id={"espn.us": epg_espn},
                epg_by_name={"espn": epg_espn},
                epg_by_callsign={},
                channel_tags=set(),
                country_tags=set(),
            )
            # ESPN with exact_name match should match
            assert result is not None
            assert result[0].display_name == "ESPN"
