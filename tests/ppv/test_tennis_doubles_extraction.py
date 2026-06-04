"""Tests for tennis doubles competitor extraction (TODO 127)."""

import json
from pathlib import Path

import pytest

from services.ppv.extraction import tennis_doubles
from services.ppv.extraction.competitors import extract_competitors_detail

FIXTURES = Path(__file__).parent / "fixtures" / "tennis_doubles_channels.json"


@pytest.fixture(scope="module")
def fixture_data():
    with FIXTURES.open(encoding="utf-8") as f:
        return json.load(f)


class TestParseTennisDoublesSide:
    def test_legends_initials(self):
        assert tennis_doubles.parse_tennis_doubles_side("A Cornet D Hantuchova") == [
            "A Cornet",
            "D Hantuchova",
        ]

    def test_four_initials(self):
        assert tennis_doubles.parse_tennis_doubles_side("T Golovin G Forget") == [
            "T Golovin",
            "G Forget",
        ]

    def test_wheelchair_doubles(self):
        assert tennis_doubles.parse_tennis_doubles_side("Y Kamiji Z Zhu") == [
            "Y Kamiji",
            "Z Zhu",
        ]

    def test_hyphenated_surname(self):
        assert tennis_doubles.parse_tennis_doubles_side("P Lucic-Baroni A Radwanska") == [
            "P Lucic-Baroni",
            "A Radwanska",
        ]

    def test_singles_side_not_parsed_as_doubles(self):
        assert tennis_doubles.parse_tennis_doubles_side("Anna Kalinskaya") is None

    def test_explicit_slash(self):
        assert tennis_doubles.parse_tennis_doubles_side("Cornet / Hantuchova") == [
            "Cornet",
            "Hantuchova",
        ]


class TestExtractCompetitorsDetail:
    @pytest.mark.parametrize("case", json.loads(FIXTURES.read_text())["doubles"], ids=lambda c: c["channel"][:40])
    def test_doubles_from_fixtures(self, case):
        detail = extract_competitors_detail(case["channel"])
        assert detail is not None
        assert detail.format == "doubles"
        assert detail.players == tuple(case["players"])
        assert detail.side1 == case["sides"][0]
        assert detail.side2 == case["sides"][1]

    @pytest.mark.parametrize(
        "case",
        json.loads(FIXTURES.read_text())["singles_controls"],
        ids=lambda c: c["channel"][:40],
    )
    def test_singles_controls(self, case):
        detail = extract_competitors_detail(case["channel"])
        assert detail is not None
        assert detail.format == "singles"
        assert detail.players is None
        assert (detail.side1, detail.side2) == tuple(case["competitors"])

    def test_non_tennis_four_token_side_stays_singles(self):
        """Team-sport titles must not be split as tennis doubles."""
        detail = extract_competitors_detail("Foo Bar Baz Qux vs Alpha Beta Gamma Delta")
        assert detail is not None
        assert detail.format == "singles"
