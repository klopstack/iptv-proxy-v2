"""
Tests for FCC match patterns routes to boost coverage

Uses shared fixtures from conftest.py for proper test isolation.
"""
import json

from models import (
    CallsignSuffix,
    CountryTag,
    EpgCountrySuffix,
    FccMatchChannelPattern,
    FccMatchLocationPattern,
    FccMatchNetwork,
    FccMatchStrategy,
    QualityTag,
    db,
)

# app and client fixtures are provided by conftest.py


class TestFccMatchPatternsPages:
    """Test FCC match patterns web pages"""

    def test_fcc_match_patterns_page(self, client, app):
        """Test FCC match patterns page loads"""
        with app.app_context():
            response = client.get("/fcc-match-patterns")
            assert response.status_code in (200, 204)

    def test_configurable_patterns_page(self, client, app):
        """Test configurable patterns page loads"""
        with app.app_context():
            response = client.get("/configurable-patterns")
            assert response.status_code in (200, 204)


class TestNetworkPatterns:
    """Test network pattern CRUD operations"""

    def test_get_networks_empty(self, client, app):
        """Test getting networks when none exist"""
        with app.app_context():
            response = client.get("/api/fcc-match-patterns/networks")
            assert response.status_code in (200, 204)
            assert response.get_json() == []

    def test_create_network(self, client, app):
        """Test creating a network pattern"""
        with app.app_context():
            response = client.post(
                "/api/fcc-match-patterns/networks",
                json={
                    "name": "ABC",
                    "display_name": "ABC",
                    "description": "ABC Network",
                    "fcc_affiliation_pattern": "ABC",
                    "tag_patterns": ["ABC"],
                    "enabled": True,
                    "priority": 10,
                },
            )
            assert response.status_code == 201
            data = response.get_json()
            assert data["name"] == "ABC"
            assert data["enabled"] is True

    def test_get_networks_with_data(self, client, app):
        """Test getting networks when some exist"""
        with app.app_context():
            network = FccMatchNetwork(
                name="NBC",
                display_name="NBC",
                fcc_affiliation_pattern="NBC",
                tag_patterns=json.dumps(["NBC"]),
                enabled=True,
                priority=10,
            )
            db.session.add(network)
            db.session.commit()

            response = client.get("/api/fcc-match-patterns/networks")
            assert response.status_code in (200, 204)
            data = response.get_json()
            assert len(data) >= 1
            # Find our network in the list
            nbc_networks = [n for n in data if n["name"] == "NBC"]
            assert len(nbc_networks) >= 1

    def test_update_network(self, client, app):
        """Test updating a network pattern"""
        with app.app_context():
            network = FccMatchNetwork(
                name="CBS",
                display_name="CBS",
                fcc_affiliation_pattern="CBS",
                enabled=True,
                priority=10,
            )
            db.session.add(network)
            db.session.commit()
            network_id = network.id

            response = client.put(
                f"/api/fcc-match-patterns/networks/{network_id}",
                json={
                    "display_name": "CBS Updated",
                    "enabled": False,
                },
            )
            assert response.status_code in (200, 204)
            data = response.get_json()
            assert data["display_name"] == "CBS Updated"
            assert data["enabled"] is False

    def test_delete_network(self, client, app):
        """Test deleting a network pattern"""
        with app.app_context():
            network = FccMatchNetwork(
                name="FOX",
                display_name="FOX",
                fcc_affiliation_pattern="FOX",
                enabled=True,
                priority=10,
            )
            db.session.add(network)
            db.session.commit()
            network_id = network.id

            response = client.delete(f"/api/fcc-match-patterns/networks/{network_id}")
            assert response.status_code in (200, 204)

            # Verify deleted - look for the specific network by ID
            response = client.get(f"/api/fcc-match-patterns/networks/{network_id}")
            assert response.status_code == 404


class TestChannelPatterns:
    """Test channel number pattern CRUD operations"""

    def test_get_channel_patterns_empty(self, client, app):
        """Test getting channel patterns when none exist"""
        with app.app_context():
            response = client.get("/api/fcc-match-patterns/channel-patterns")
            assert response.status_code in (200, 204)
            assert response.get_json() == []

    def test_create_channel_pattern(self, client, app):
        """Test creating a channel pattern"""
        with app.app_context():
            response = client.post(
                "/api/fcc-match-patterns/channel-patterns",
                json={
                    "name": "Channel Number",
                    "description": "Extract channel numbers",
                    "pattern": r"(\d+)",
                    "pattern_type": "regex",
                    "capture_group": 1,
                    "enabled": True,
                    "priority": 10,
                },
            )
            assert response.status_code == 201
            data = response.get_json()
            assert data["name"] == "Channel Number"

    def test_update_channel_pattern(self, client, app):
        """Test updating a channel pattern"""
        with app.app_context():
            pattern = FccMatchChannelPattern(
                name="Test Pattern",
                pattern=r"(\d+)",
                pattern_type="regex",
                enabled=True,
                priority=10,
            )
            db.session.add(pattern)
            db.session.commit()
            pattern_id = pattern.id

            response = client.put(
                f"/api/fcc-match-patterns/channel-patterns/{pattern_id}",
                json={"name": "Updated Pattern", "enabled": False},
            )
            assert response.status_code in (200, 204)
            data = response.get_json()
            assert data["name"] == "Updated Pattern"

    def test_delete_channel_pattern(self, client, app):
        """Test deleting a channel pattern"""
        with app.app_context():
            pattern = FccMatchChannelPattern(
                name="Delete Me",
                pattern=r"test",
                pattern_type="regex",
                enabled=True,
                priority=10,
            )
            db.session.add(pattern)
            db.session.commit()
            pattern_id = pattern.id

            response = client.delete(f"/api/fcc-match-patterns/channel-patterns/{pattern_id}")
            assert response.status_code in (200, 204)


class TestLocationPatterns:
    """Test location pattern CRUD operations"""

    def test_get_location_patterns_empty(self, client, app):
        """Test getting location patterns when none exist"""
        with app.app_context():
            response = client.get("/api/fcc-match-patterns/location-patterns")
            assert response.status_code in (200, 204)
            assert response.get_json() == []

    def test_create_location_pattern(self, client, app):
        """Test creating a location pattern"""
        with app.app_context():
            response = client.post(
                "/api/fcc-match-patterns/location-patterns",
                json={
                    "name": "City State",
                    "description": "Extract city and state",
                    "pattern": r"([A-Z]+),\s*([A-Z]{2})",
                    "pattern_type": "regex",
                    "extract_city": True,
                    "extract_state": True,
                    "city_group": 1,
                    "state_group": 2,
                    "enabled": True,
                    "priority": 10,
                },
            )
            assert response.status_code == 201

    def test_update_location_pattern(self, client, app):
        """Test updating a location pattern"""
        with app.app_context():
            pattern = FccMatchLocationPattern(
                name="Test Location",
                pattern=r"test",
                pattern_type="regex",
                enabled=True,
                priority=10,
            )
            db.session.add(pattern)
            db.session.commit()
            pattern_id = pattern.id

            response = client.put(
                f"/api/fcc-match-patterns/location-patterns/{pattern_id}",
                json={"name": "Updated Location"},
            )
            assert response.status_code in (200, 204)

    def test_delete_location_pattern(self, client, app):
        """Test deleting a location pattern"""
        with app.app_context():
            pattern = FccMatchLocationPattern(
                name="Delete Me",
                pattern=r"test",
                pattern_type="regex",
                enabled=True,
                priority=10,
            )
            db.session.add(pattern)
            db.session.commit()
            pattern_id = pattern.id

            response = client.delete(f"/api/fcc-match-patterns/location-patterns/{pattern_id}")
            assert response.status_code in (200, 204)


class TestStrategies:
    """Test match strategy CRUD operations"""

    def test_get_strategies_empty(self, client, app):
        """Test getting strategies when none exist"""
        with app.app_context():
            response = client.get("/api/fcc-match-patterns/strategies")
            assert response.status_code in (200, 204)
            assert response.get_json() == []

    def test_create_strategy(self, client, app):
        """Test creating a match strategy"""
        with app.app_context():
            response = client.post(
                "/api/fcc-match-patterns/strategies",
                json={
                    "name": "Standard Match",
                    "description": "Standard matching strategy",
                    "strategy_type": "standard",
                    "require_network": True,
                    "require_channel_number": False,
                    "require_state": False,
                    "require_city": False,
                    "match_nielsen_dma": True,
                    "match_community_city": False,
                    "match_community_state": False,
                    "enabled": True,
                    "priority": 10,
                },
            )
            assert response.status_code == 201

    def test_update_strategy(self, client, app):
        """Test updating a strategy"""
        with app.app_context():
            strategy = FccMatchStrategy(
                name="Test Strategy",
                strategy_type="standard",
                enabled=True,
                priority=10,
            )
            db.session.add(strategy)
            db.session.commit()
            strategy_id = strategy.id

            response = client.put(
                f"/api/fcc-match-patterns/strategies/{strategy_id}",
                json={"name": "Updated Strategy"},
            )
            assert response.status_code in (200, 204)

    def test_delete_strategy(self, client, app):
        """Test deleting a strategy"""
        with app.app_context():
            strategy = FccMatchStrategy(
                name="Delete Me",
                strategy_type="standard",
                enabled=True,
                priority=10,
            )
            db.session.add(strategy)
            db.session.commit()
            strategy_id = strategy.id

            response = client.delete(f"/api/fcc-match-patterns/strategies/{strategy_id}")
            assert response.status_code in (200, 204)


class TestCountryTags:
    """Test country tag CRUD operations"""

    def test_get_country_tags_empty(self, client, app):
        """Test getting country tags when none exist"""
        with app.app_context():
            response = client.get("/api/fcc-match-patterns/country-tags")
            assert response.status_code in (200, 204)
            assert response.get_json() == []

    def test_create_country_tag(self, client, app):
        """Test creating a country tag"""
        with app.app_context():
            response = client.post(
                "/api/fcc-match-patterns/country-tags",
                json={
                    "tag_name": "US",
                    "country_name": "United States",
                    "enabled": True,
                },
            )
            assert response.status_code == 201

    def test_update_country_tag(self, client, app):
        """Test updating a country tag"""
        with app.app_context():
            tag = CountryTag(tag_name="UK", country_name="United Kingdom", enabled=True)
            db.session.add(tag)
            db.session.commit()
            tag_id = tag.id

            response = client.put(
                f"/api/fcc-match-patterns/country-tags/{tag_id}",
                json={"country_name": "Great Britain"},
            )
            assert response.status_code in (200, 204)

    def test_delete_country_tag(self, client, app):
        """Test deleting a country tag"""
        with app.app_context():
            tag = CountryTag(tag_name="CA", country_name="Canada", enabled=True)
            db.session.add(tag)
            db.session.commit()
            tag_id = tag.id

            response = client.delete(f"/api/fcc-match-patterns/country-tags/{tag_id}")
            assert response.status_code in (200, 204)


class TestQualityTags:
    """Test quality tag CRUD operations"""

    def test_get_quality_tags_empty(self, client, app):
        """Test getting quality tags when none exist"""
        with app.app_context():
            response = client.get("/api/fcc-match-patterns/quality-tags")
            assert response.status_code in (200, 204)
            assert response.get_json() == []

    def test_create_quality_tag(self, client, app):
        """Test creating a quality tag"""
        with app.app_context():
            response = client.post(
                "/api/fcc-match-patterns/quality-tags",
                json={
                    "tag_name": "HD",
                    "display_name": "High Definition",
                    "quality_score": 2,
                    "enabled": True,
                },
            )
            assert response.status_code == 201

    def test_update_quality_tag(self, client, app):
        """Test updating a quality tag"""
        with app.app_context():
            tag = QualityTag(tag_name="4K", display_name="4K Ultra HD", quality_score=4, enabled=True)
            db.session.add(tag)
            db.session.commit()
            tag_id = tag.id

            response = client.put(
                f"/api/fcc-match-patterns/quality-tags/{tag_id}",
                json={"display_name": "4K UHD"},
            )
            assert response.status_code in (200, 204)

    def test_delete_quality_tag(self, client, app):
        """Test deleting a quality tag"""
        with app.app_context():
            tag = QualityTag(tag_name="SD", display_name="Standard Definition", quality_score=1, enabled=True)
            db.session.add(tag)
            db.session.commit()
            tag_id = tag.id

            response = client.delete(f"/api/fcc-match-patterns/quality-tags/{tag_id}")
            assert response.status_code in (200, 204)


class TestEpgCountrySuffixes:
    """Test EPG country suffix CRUD operations"""

    def test_get_epg_suffixes_empty(self, client, app):
        """Test getting EPG suffixes when none exist"""
        with app.app_context():
            response = client.get("/api/fcc-match-patterns/country-suffixes")
            assert response.status_code in (200, 204)
            assert response.get_json() == []

    def test_create_epg_suffix(self, client, app):
        """Test creating an EPG suffix"""
        with app.app_context():
            response = client.post(
                "/api/fcc-match-patterns/country-suffixes",
                json={
                    "country_code": "US",
                    "country_name": "United States",
                    "epg_suffixes": [".us", ".us2"],
                    "enabled": True,
                },
            )
            assert response.status_code == 201

    def test_update_epg_suffix(self, client, app):
        """Test updating an EPG suffix"""
        with app.app_context():
            import json

            suffix = EpgCountrySuffix(
                country_code="UK",
                country_name="United Kingdom",
                epg_suffixes=json.dumps([".uk"]),
                enabled=True,
            )
            db.session.add(suffix)
            db.session.commit()
            suffix_id = suffix.id

            response = client.put(
                f"/api/fcc-match-patterns/country-suffixes/{suffix_id}",
                json={"country_name": "Great Britain"},
            )
            assert response.status_code in (200, 204)

    def test_delete_epg_suffix(self, client, app):
        """Test deleting an EPG suffix"""
        with app.app_context():
            import json

            suffix = EpgCountrySuffix(
                country_code="CA",
                epg_suffixes=json.dumps([".ca"]),
                enabled=True,
            )
            db.session.add(suffix)
            db.session.commit()
            suffix_id = suffix.id

            response = client.delete(f"/api/fcc-match-patterns/country-suffixes/{suffix_id}")
            assert response.status_code in (200, 204)


class TestCallsignSuffixes:
    """Test callsign suffix CRUD operations"""

    def test_get_callsign_suffixes_empty(self, client, app):
        """Test getting callsign suffixes when none exist"""
        with app.app_context():
            response = client.get("/api/fcc-match-patterns/callsign-suffixes")
            assert response.status_code in (200, 204)
            assert response.get_json() == []

    def test_create_callsign_suffix(self, client, app):
        """Test creating a callsign suffix"""
        with app.app_context():
            response = client.post(
                "/api/fcc-match-patterns/callsign-suffixes",
                json={
                    "suffix": "-DT",
                    "description": "Digital TV",
                    "priority": 1,
                    "enabled": True,
                },
            )
            assert response.status_code == 201

    def test_update_callsign_suffix(self, client, app):
        """Test updating a callsign suffix"""
        with app.app_context():
            suffix = CallsignSuffix(suffix="-TV", description="Television", priority=2, enabled=True)
            db.session.add(suffix)
            db.session.commit()
            suffix_id = suffix.id

            response = client.put(
                f"/api/fcc-match-patterns/callsign-suffixes/{suffix_id}",
                json={"description": "Television Broadcast"},
            )
            assert response.status_code in (200, 204)

    def test_delete_callsign_suffix(self, client, app):
        """Test deleting a callsign suffix"""
        with app.app_context():
            suffix = CallsignSuffix(suffix="-HD", description="High Definition", priority=3, enabled=True)
            db.session.add(suffix)
            db.session.commit()
            suffix_id = suffix.id

            response = client.delete(f"/api/fcc-match-patterns/callsign-suffixes/{suffix_id}")
            assert response.status_code in (200, 204)
