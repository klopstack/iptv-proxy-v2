"""Unit tests for FccMatchPatternsService (no Flask request context)."""

import json

from models import FccMatchNetwork, db
from services.fcc_match_patterns_service import FccMatchPatternsService


class TestCreateNetwork:
    def test_create_network_missing_name(self, app):
        with app.app_context():
            payload, error, status = FccMatchPatternsService.create_network({"fcc_affiliation_pattern": "ABC"})
            assert payload is None
            assert error == "Name is required"
            assert status == 400

    def test_create_network_duplicate(self, app):
        with app.app_context():
            db.session.add(
                FccMatchNetwork(
                    name="ABC",
                    display_name="ABC",
                    fcc_affiliation_pattern="ABC",
                    enabled=True,
                    priority=10,
                )
            )
            db.session.commit()

            payload, error, status = FccMatchPatternsService.create_network(
                {"name": "ABC", "fcc_affiliation_pattern": "ABC"}
            )
            assert payload is None
            assert "already exists" in error
            assert status == 409

    def test_create_network_success(self, app):
        with app.app_context():
            payload, error, status = FccMatchPatternsService.create_network(
                {
                    "name": "FOX",
                    "fcc_affiliation_pattern": "FOX",
                    "tag_patterns": ["FOX"],
                    "enabled": True,
                    "priority": 5,
                }
            )
            assert error is None
            assert status == 201
            assert payload["name"] == "FOX"
            assert payload["tag_patterns"] == ["FOX"]

            stored = FccMatchNetwork.query.filter_by(name="FOX").first()
            assert stored is not None
            assert json.loads(stored.tag_patterns) == ["FOX"]


class TestTestPatterns:
    def test_test_patterns_returns_structure(self, app):
        with app.app_context():
            result = FccMatchPatternsService.test_patterns({"channel_name": "WABC 7", "tags": ["New York", "NY"]})
            assert result["channel_name"] == "WABC 7"
            assert "extracted_channel_number" in result
            assert "location_parsing" in result
            assert "fcc_callsign" in result
