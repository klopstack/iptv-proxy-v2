"""FCC match pattern CRUD and test helpers (extracted from routes/fcc_match_patterns.py)."""

from __future__ import annotations

import json
from typing import Any, cast

from models import (
    CallsignSuffix,
    Channel,
    CountryTag,
    EpgCountrySuffix,
    FccMatchChannelPattern,
    FccMatchLocationPattern,
    FccMatchNetwork,
    FccMatchStrategy,
    QualityTag,
    db,
)
from services.cache_service import cache_service
from services.epg.match_rules import clear_fcc_pattern_cache
from services.serializers.fcc import (
    serialize_callsign_suffix,
    serialize_country_suffix,
    serialize_country_tag,
    serialize_fcc_channel_pattern,
    serialize_fcc_location_pattern,
    serialize_fcc_network,
    serialize_fcc_strategy,
    serialize_quality_tag,
)


class FccMatchPatternsService:
    """CRUD operations for FCC match pattern admin APIs."""

    @staticmethod
    def _commit_and_clear_caches() -> None:
        db.session.commit()
        cache_service.clear_all()
        clear_fcc_pattern_cache()

    @staticmethod
    def _delete_entity(entity) -> None:
        db.session.delete(entity)
        FccMatchPatternsService._commit_and_clear_caches()

    # ------------------------------------------------------------------
    # Networks
    # ------------------------------------------------------------------

    @staticmethod
    def list_networks() -> list[dict[str, Any]]:
        networks = FccMatchNetwork.query.order_by(FccMatchNetwork.priority, FccMatchNetwork.name).all()
        return [serialize_fcc_network(n) for n in networks]

    @staticmethod
    def get_network(network_id: int) -> dict[str, Any] | None:
        network = db.session.get(FccMatchNetwork, network_id)
        if network is None:
            return None
        return serialize_fcc_network(network)

    @staticmethod
    def create_network(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        if not data.get("name"):
            return None, "Name is required", 400
        if not data.get("fcc_affiliation_pattern"):
            return None, "FCC affiliation pattern is required", 400

        existing = FccMatchNetwork.query.filter_by(name=data["name"]).first()
        if existing:
            return None, f"Network '{data['name']}' already exists", 409

        network = FccMatchNetwork(
            name=data["name"],
            display_name=data.get("display_name"),
            description=data.get("description"),
            fcc_affiliation_pattern=data["fcc_affiliation_pattern"],
            tag_patterns=json.dumps(data.get("tag_patterns", [])) if data.get("tag_patterns") else None,
            enabled=data.get("enabled", True),
            priority=data.get("priority", 100),
        )
        db.session.add(network)
        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_fcc_network(network), None, 201

    @staticmethod
    def update_network(network_id: int, data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        network = db.session.get(FccMatchNetwork, network_id)
        if network is None:
            return None, "Not found", 404

        network.name = data.get("name", network.name)
        network.display_name = data.get("display_name", network.display_name)
        network.description = data.get("description", network.description)
        network.fcc_affiliation_pattern = data.get("fcc_affiliation_pattern", network.fcc_affiliation_pattern)
        if "tag_patterns" in data:
            network.tag_patterns = json.dumps(data["tag_patterns"]) if data["tag_patterns"] else None
        network.enabled = data.get("enabled", network.enabled)
        network.priority = data.get("priority", network.priority)

        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_fcc_network(network), None, 200

    @staticmethod
    def delete_network(network_id: int) -> bool:
        network = db.session.get(FccMatchNetwork, network_id)
        if network is None:
            return False
        FccMatchPatternsService._delete_entity(network)
        return True

    # ------------------------------------------------------------------
    # Channel patterns
    # ------------------------------------------------------------------

    @staticmethod
    def list_channel_patterns() -> list[dict[str, Any]]:
        patterns = FccMatchChannelPattern.query.order_by(
            FccMatchChannelPattern.priority, FccMatchChannelPattern.name
        ).all()
        return [serialize_fcc_channel_pattern(p) for p in patterns]

    @staticmethod
    def get_channel_pattern(pattern_id: int) -> dict[str, Any] | None:
        pattern = db.session.get(FccMatchChannelPattern, pattern_id)
        if pattern is None:
            return None
        return serialize_fcc_channel_pattern(pattern)

    @staticmethod
    def create_channel_pattern(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        if not data.get("name"):
            return None, "Name is required", 400
        if not data.get("pattern"):
            return None, "Pattern is required", 400

        pattern = FccMatchChannelPattern(
            name=data["name"],
            description=data.get("description"),
            pattern=data["pattern"],
            pattern_type=data.get("pattern_type", "regex"),
            capture_group=data.get("capture_group", 1),
            networks=json.dumps(data.get("networks")) if data.get("networks") else None,
            enabled=data.get("enabled", True),
            priority=data.get("priority", 100),
        )
        db.session.add(pattern)
        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_fcc_channel_pattern(pattern), None, 201

    @staticmethod
    def update_channel_pattern(pattern_id: int, data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        pattern = db.session.get(FccMatchChannelPattern, pattern_id)
        if pattern is None:
            return None, "Not found", 404

        pattern.name = data.get("name", pattern.name)
        pattern.description = data.get("description", pattern.description)
        pattern.pattern = data.get("pattern", pattern.pattern)
        pattern.pattern_type = data.get("pattern_type", pattern.pattern_type)
        pattern.capture_group = data.get("capture_group", pattern.capture_group)
        if "networks" in data:
            pattern.networks = json.dumps(data["networks"]) if data["networks"] else None
        pattern.enabled = data.get("enabled", pattern.enabled)
        pattern.priority = data.get("priority", pattern.priority)

        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_fcc_channel_pattern(pattern), None, 200

    @staticmethod
    def delete_channel_pattern(pattern_id: int) -> bool:
        pattern = db.session.get(FccMatchChannelPattern, pattern_id)
        if pattern is None:
            return False
        FccMatchPatternsService._delete_entity(pattern)
        return True

    # ------------------------------------------------------------------
    # Location patterns
    # ------------------------------------------------------------------

    @staticmethod
    def list_location_patterns() -> list[dict[str, Any]]:
        patterns = FccMatchLocationPattern.query.order_by(
            FccMatchLocationPattern.priority, FccMatchLocationPattern.name
        ).all()
        return [serialize_fcc_location_pattern(p) for p in patterns]

    @staticmethod
    def get_location_pattern(pattern_id: int) -> dict[str, Any] | None:
        pattern = db.session.get(FccMatchLocationPattern, pattern_id)
        if pattern is None:
            return None
        return serialize_fcc_location_pattern(pattern)

    @staticmethod
    def create_location_pattern(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        if not data.get("name"):
            return None, "Name is required", 400
        if not data.get("pattern"):
            return None, "Pattern is required", 400

        pattern = FccMatchLocationPattern(
            name=data["name"],
            description=data.get("description"),
            pattern=data["pattern"],
            pattern_type=data.get("pattern_type", "regex"),
            extract_city=data.get("extract_city", True),
            extract_state=data.get("extract_state", True),
            city_group=data.get("city_group", 1),
            state_group=data.get("state_group", 2),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 100),
        )
        db.session.add(pattern)
        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_fcc_location_pattern(pattern), None, 201

    @staticmethod
    def update_location_pattern(pattern_id: int, data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        pattern = db.session.get(FccMatchLocationPattern, pattern_id)
        if pattern is None:
            return None, "Not found", 404

        pattern.name = data.get("name", pattern.name)
        pattern.description = data.get("description", pattern.description)
        pattern.pattern = data.get("pattern", pattern.pattern)
        pattern.pattern_type = data.get("pattern_type", pattern.pattern_type)
        pattern.extract_city = data.get("extract_city", pattern.extract_city)
        pattern.extract_state = data.get("extract_state", pattern.extract_state)
        pattern.city_group = data.get("city_group", pattern.city_group)
        pattern.state_group = data.get("state_group", pattern.state_group)
        pattern.enabled = data.get("enabled", pattern.enabled)
        pattern.priority = data.get("priority", pattern.priority)

        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_fcc_location_pattern(pattern), None, 200

    @staticmethod
    def delete_location_pattern(pattern_id: int) -> bool:
        pattern = db.session.get(FccMatchLocationPattern, pattern_id)
        if pattern is None:
            return False
        FccMatchPatternsService._delete_entity(pattern)
        return True

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    @staticmethod
    def list_strategies() -> list[dict[str, Any]]:
        strategies = FccMatchStrategy.query.order_by(FccMatchStrategy.priority, FccMatchStrategy.name).all()
        return [serialize_fcc_strategy(s) for s in strategies]

    @staticmethod
    def get_strategy(strategy_id: int) -> dict[str, Any] | None:
        strategy = db.session.get(FccMatchStrategy, strategy_id)
        if strategy is None:
            return None
        return serialize_fcc_strategy(strategy)

    @staticmethod
    def create_strategy(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        if not data.get("name"):
            return None, "Name is required", 400
        if not data.get("strategy_type"):
            return None, "Strategy type is required", 400

        strategy = FccMatchStrategy(
            name=data["name"],
            description=data.get("description"),
            strategy_type=data["strategy_type"],
            require_network=data.get("require_network", True),
            require_channel_number=data.get("require_channel_number", False),
            require_state=data.get("require_state", False),
            require_city=data.get("require_city", False),
            match_nielsen_dma=data.get("match_nielsen_dma", True),
            match_community_city=data.get("match_community_city", True),
            match_community_state=data.get("match_community_state", True),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 100),
        )
        db.session.add(strategy)
        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_fcc_strategy(strategy), None, 201

    @staticmethod
    def update_strategy(strategy_id: int, data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        strategy = db.session.get(FccMatchStrategy, strategy_id)
        if strategy is None:
            return None, "Not found", 404

        strategy.name = data.get("name", strategy.name)
        strategy.description = data.get("description", strategy.description)
        strategy.strategy_type = data.get("strategy_type", strategy.strategy_type)
        strategy.require_network = data.get("require_network", strategy.require_network)
        strategy.require_channel_number = data.get("require_channel_number", strategy.require_channel_number)
        strategy.require_state = data.get("require_state", strategy.require_state)
        strategy.require_city = data.get("require_city", strategy.require_city)
        strategy.match_nielsen_dma = data.get("match_nielsen_dma", strategy.match_nielsen_dma)
        strategy.match_community_city = data.get("match_community_city", strategy.match_community_city)
        strategy.match_community_state = data.get("match_community_state", strategy.match_community_state)
        strategy.enabled = data.get("enabled", strategy.enabled)
        strategy.priority = data.get("priority", strategy.priority)

        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_fcc_strategy(strategy), None, 200

    @staticmethod
    def delete_strategy(strategy_id: int) -> bool:
        strategy = db.session.get(FccMatchStrategy, strategy_id)
        if strategy is None:
            return False
        FccMatchPatternsService._delete_entity(strategy)
        return True

    # ------------------------------------------------------------------
    # Pattern testing
    # ------------------------------------------------------------------

    @staticmethod
    def test_patterns(data: dict[str, Any]) -> dict[str, Any]:
        from services.epg.match_rules import EpgMatchRulesService

        channel_name = data.get("channel_name", "")
        tags = set(data.get("tags", []))

        channel_number = EpgMatchRulesService._extract_channel_number(channel_name)

        location_results = []
        for tag in tags:
            city, state = EpgMatchRulesService._parse_location_tag(tag)
            if city or state:
                location_results.append({"tag": tag, "city": city, "state": state})

        class MockChannel:
            def __init__(self, name):
                self.name = name

        mock_channel = cast(Channel, MockChannel(channel_name))
        callsign = EpgMatchRulesService._lookup_fcc_callsign(mock_channel, tags)

        return {
            "channel_name": channel_name,
            "tags": list(tags),
            "extracted_channel_number": channel_number,
            "location_parsing": location_results,
            "fcc_callsign": callsign,
        }

    # ------------------------------------------------------------------
    # Country suffixes
    # ------------------------------------------------------------------

    @staticmethod
    def list_country_suffixes() -> list[dict[str, Any]]:
        suffixes = EpgCountrySuffix.query.order_by(EpgCountrySuffix.priority, EpgCountrySuffix.country_code).all()
        return [serialize_country_suffix(s) for s in suffixes]

    @staticmethod
    def get_country_suffix(suffix_id: int) -> dict[str, Any] | None:
        suffix = db.session.get(EpgCountrySuffix, suffix_id)
        if suffix is None:
            return None
        return serialize_country_suffix(suffix)

    @staticmethod
    def create_country_suffix(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        suffix = EpgCountrySuffix(
            country_code=data["country_code"].upper(),
            country_name=data.get("country_name"),
            epg_suffixes=json.dumps(data.get("epg_suffixes", [])),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 100),
        )
        db.session.add(suffix)
        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_country_suffix(suffix), None, 201

    @staticmethod
    def update_country_suffix(suffix_id: int, data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        suffix = db.session.get(EpgCountrySuffix, suffix_id)
        if suffix is None:
            return None, "Not found", 404

        suffix.country_code = data.get("country_code", suffix.country_code).upper()
        suffix.country_name = data.get("country_name", suffix.country_name)
        if "epg_suffixes" in data:
            suffix.epg_suffixes = json.dumps(data["epg_suffixes"])
        suffix.enabled = data.get("enabled", suffix.enabled)
        suffix.priority = data.get("priority", suffix.priority)

        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_country_suffix(suffix), None, 200

    @staticmethod
    def delete_country_suffix(suffix_id: int) -> bool:
        suffix = db.session.get(EpgCountrySuffix, suffix_id)
        if suffix is None:
            return False
        FccMatchPatternsService._delete_entity(suffix)
        return True

    # ------------------------------------------------------------------
    # Quality tags
    # ------------------------------------------------------------------

    @staticmethod
    def list_quality_tags() -> list[dict[str, Any]]:
        tags = QualityTag.query.order_by(QualityTag.category, QualityTag.quality_score.desc()).all()
        return [serialize_quality_tag(t) for t in tags]

    @staticmethod
    def get_quality_tag(tag_id: int) -> dict[str, Any] | None:
        tag = db.session.get(QualityTag, tag_id)
        if tag is None:
            return None
        return serialize_quality_tag(tag)

    @staticmethod
    def create_quality_tag(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        tag = QualityTag(
            tag_name=data["tag_name"].upper(),
            display_name=data.get("display_name"),
            category=data.get("category"),
            quality_score=data.get("quality_score", 0),
            exclude_from_location=data.get("exclude_from_location", True),
            enabled=data.get("enabled", True),
        )
        db.session.add(tag)
        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_quality_tag(tag), None, 201

    @staticmethod
    def update_quality_tag(tag_id: int, data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        tag = db.session.get(QualityTag, tag_id)
        if tag is None:
            return None, "Not found", 404

        tag.tag_name = data.get("tag_name", tag.tag_name).upper()
        tag.display_name = data.get("display_name", tag.display_name)
        tag.category = data.get("category", tag.category)
        tag.quality_score = data.get("quality_score", tag.quality_score)
        tag.exclude_from_location = data.get("exclude_from_location", tag.exclude_from_location)
        tag.enabled = data.get("enabled", tag.enabled)

        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_quality_tag(tag), None, 200

    @staticmethod
    def delete_quality_tag(tag_id: int) -> bool:
        tag = db.session.get(QualityTag, tag_id)
        if tag is None:
            return False
        FccMatchPatternsService._delete_entity(tag)
        return True

    # ------------------------------------------------------------------
    # Country tags
    # ------------------------------------------------------------------

    @staticmethod
    def list_country_tags() -> list[dict[str, Any]]:
        tags = CountryTag.query.order_by(CountryTag.tag_name).all()
        return [serialize_country_tag(t) for t in tags]

    @staticmethod
    def get_country_tag(tag_id: int) -> dict[str, Any] | None:
        tag = db.session.get(CountryTag, tag_id)
        if tag is None:
            return None
        return serialize_country_tag(tag)

    @staticmethod
    def create_country_tag(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        tag = CountryTag(
            tag_name=data["tag_name"].upper(),
            country_name=data.get("country_name"),
            iso_code=data.get("iso_code"),
            exclude_from_location=data.get("exclude_from_location", True),
            enabled=data.get("enabled", True),
        )
        db.session.add(tag)
        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_country_tag(tag), None, 201

    @staticmethod
    def update_country_tag(tag_id: int, data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        tag = db.session.get(CountryTag, tag_id)
        if tag is None:
            return None, "Not found", 404

        tag.tag_name = data.get("tag_name", tag.tag_name).upper()
        tag.country_name = data.get("country_name", tag.country_name)
        tag.iso_code = data.get("iso_code", tag.iso_code)
        tag.exclude_from_location = data.get("exclude_from_location", tag.exclude_from_location)
        tag.enabled = data.get("enabled", tag.enabled)

        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_country_tag(tag), None, 200

    @staticmethod
    def delete_country_tag(tag_id: int) -> bool:
        tag = db.session.get(CountryTag, tag_id)
        if tag is None:
            return False
        FccMatchPatternsService._delete_entity(tag)
        return True

    # ------------------------------------------------------------------
    # Callsign suffixes
    # ------------------------------------------------------------------

    @staticmethod
    def list_callsign_suffixes() -> list[dict[str, Any]]:
        suffixes = CallsignSuffix.query.order_by(CallsignSuffix.priority, CallsignSuffix.suffix).all()
        return [serialize_callsign_suffix(s) for s in suffixes]

    @staticmethod
    def get_callsign_suffix(suffix_id: int) -> dict[str, Any] | None:
        suffix = db.session.get(CallsignSuffix, suffix_id)
        if suffix is None:
            return None
        return serialize_callsign_suffix(suffix)

    @staticmethod
    def create_callsign_suffix(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        suffix = CallsignSuffix(
            suffix=data["suffix"].upper(),
            description=data.get("description"),
            try_on_miss=data.get("try_on_miss", True),
            strip_on_normalize=data.get("strip_on_normalize", True),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 100),
        )
        db.session.add(suffix)
        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_callsign_suffix(suffix), None, 201

    @staticmethod
    def update_callsign_suffix(suffix_id: int, data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int]:
        suffix = db.session.get(CallsignSuffix, suffix_id)
        if suffix is None:
            return None, "Not found", 404

        suffix.suffix = data.get("suffix", suffix.suffix).upper()
        suffix.description = data.get("description", suffix.description)
        suffix.try_on_miss = data.get("try_on_miss", suffix.try_on_miss)
        suffix.strip_on_normalize = data.get("strip_on_normalize", suffix.strip_on_normalize)
        suffix.enabled = data.get("enabled", suffix.enabled)
        suffix.priority = data.get("priority", suffix.priority)

        FccMatchPatternsService._commit_and_clear_caches()
        return serialize_callsign_suffix(suffix), None, 200

    @staticmethod
    def delete_callsign_suffix(suffix_id: int) -> bool:
        suffix = db.session.get(CallsignSuffix, suffix_id)
        if suffix is None:
            return False
        FccMatchPatternsService._delete_entity(suffix)
        return True
