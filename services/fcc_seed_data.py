"""Default FCC match pattern seed data (shared by reset CLI and legacy migration)."""

from __future__ import annotations

import json

from models import (
    FccMatchChannelPattern,
    FccMatchLocationPattern,
    FccMatchNetwork,
    FccMatchStrategy,
    db,
)

_DEFAULT_NETWORKS: tuple[tuple[str, str, str, str, list[str], bool, int], ...] = (
    ("NBC", "NBC", "National Broadcasting Company", "%NBC%", ["NBC"], True, 10),
    ("ABC", "ABC", "American Broadcasting Company", "%ABC%", ["ABC"], True, 20),
    ("CBS", "CBS", "Columbia Broadcasting System", "%CBS%", ["CBS"], True, 30),
    ("FOX", "FOX", "Fox Broadcasting Company", "%FOX%", ["FOX"], True, 40),
    ("PBS", "PBS", "Public Broadcasting Service", "%PBS%", ["PBS"], True, 50),
    ("CW", "CW", "The CW Television Network", "%CW%", ["CW"], True, 60),
    ("ION", "ION", "ION Television", "%ION%", ["ION"], True, 70),
    ("MyNetwork", "MyNetwork TV", "MyNetworkTV", "%MYNETWORK%", ["MYNETWORK", "MNTV"], True, 80),
    ("Univision", "Univision", "Univision Network", "%UNIVISION%", ["UNIVISION", "UNI"], True, 90),
    ("Telemundo", "Telemundo", "Telemundo Network", "%TELEMUNDO%", ["TELEMUNDO"], True, 100),
)

_DEFAULT_CHANNEL_PATTERNS: tuple[tuple, ...] = (
    (
        "Network followed by number",
        "Extract channel number after network name (NBC 13, ABC 7)",
        r"\b(?:NBC|ABC|CBS|FOX|PBS|CW)\s*(\d{1,2})\b",
        "regex",
        1,
        ["NBC", "ABC", "CBS", "FOX", "PBS", "CW"],
        True,
        10,
    ),
    (
        "Number followed by network/HD",
        "Extract channel number before network or HD (13 NBC HD)",
        r"\b(\d{1,2})\s*(?:NBC|ABC|CBS|FOX|HD|SD)\b",
        "regex",
        1,
        None,
        True,
        20,
    ),
    (
        "Separator then number",
        "Extract channel number after colon/separator (US: 13 HD)",
        r"[\s:|]\s*(\d{1,2})\s*(?:HD|SD|\s|$|\[)",
        "regex",
        1,
        None,
        True,
        30,
    ),
)

_DEFAULT_LOCATION_PATTERNS: tuple[tuple, ...] = (
    (
        "City underscore State",
        "Parse CITY_STATE format (WICHITA_KS -> Wichita, KS)",
        r"^([A-Z_]+)_([A-Z]{2})$",
        "regex",
        True,
        True,
        1,
        2,
        True,
        10,
    ),
    (
        "City space State",
        "Parse CITY STATE format (WICHITA KS -> Wichita, KS)",
        r"^(.+)\s+([A-Z]{2})$",
        "regex",
        True,
        True,
        1,
        2,
        True,
        20,
    ),
    (
        "State abbreviation only",
        "Match 2-letter state abbreviation",
        r"^([A-Z]{2})$",
        "regex",
        False,
        True,
        0,
        1,
        True,
        30,
    ),
    (
        "Full state name",
        "Match full US state names (MONTANA, CALIFORNIA, NEW_YORK, etc.)",
        r"^(ALABAMA|ALASKA|ARIZONA|ARKANSAS|CALIFORNIA|COLORADO|CONNECTICUT|DELAWARE|FLORIDA|GEORGIA|HAWAII|IDAHO|ILLINOIS|INDIANA|IOWA|KANSAS|KENTUCKY|LOUISIANA|MAINE|MARYLAND|MASSACHUSETTS|MICHIGAN|MINNESOTA|MISSISSIPPI|MISSOURI|MONTANA|NEBRASKA|NEVADA|NEW[_ ]HAMPSHIRE|NEW[_ ]JERSEY|NEW[_ ]MEXICO|NEW[_ ]YORK|NORTH[_ ]CAROLINA|NORTH[_ ]DAKOTA|OHIO|OKLAHOMA|OREGON|PENNSYLVANIA|RHODE[_ ]ISLAND|SOUTH[_ ]CAROLINA|SOUTH[_ ]DAKOTA|TENNESSEE|TEXAS|UTAH|VERMONT|VIRGINIA|WASHINGTON|WEST[_ ]VIRGINIA|WISCONSIN|WYOMING)$",
        "regex",
        False,
        True,
        0,
        1,
        True,
        40,
    ),
    (
        "City only",
        "Match single word city name",
        r"^([A-Z][A-Z_\-]+)$",
        "regex",
        True,
        False,
        1,
        0,
        True,
        100,
    ),
)

_DEFAULT_STRATEGIES: tuple[tuple, ...] = (
    (
        "City + State + Channel",
        "Most precise: match network affiliate in specific city and state with channel number",
        "city_state_channel",
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        10,
    ),
    (
        "State + Channel",
        "Match network affiliate in state with channel number",
        "state_channel",
        True,
        True,
        True,
        False,
        False,
        True,
        True,
        True,
        20,
    ),
    (
        "City/DMA + Channel",
        "Match network affiliate in city or DMA with channel number",
        "city_dma_channel",
        True,
        True,
        False,
        True,
        True,
        True,
        False,
        True,
        30,
    ),
    (
        "State only",
        "Fallback: match any network affiliate in state",
        "state_only",
        True,
        False,
        True,
        False,
        False,
        True,
        True,
        True,
        40,
    ),
    (
        "City/DMA only",
        "Fallback: match any network affiliate in city or DMA",
        "city_dma_only",
        True,
        False,
        False,
        True,
        True,
        True,
        False,
        True,
        50,
    ),
)


def _json_text(value: list[str] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def seed_fcc_match_patterns_defaults() -> None:
    """Insert migration-default FCC match pattern rows via ORM."""
    for name, display_name, description, fcc_pattern, tag_patterns, enabled, priority in _DEFAULT_NETWORKS:
        db.session.add(
            FccMatchNetwork(
                name=name,
                display_name=display_name,
                description=description,
                fcc_affiliation_pattern=fcc_pattern,
                tag_patterns=_json_text(tag_patterns),
                enabled=enabled,
                priority=priority,
            )
        )

    for (
        name,
        description,
        pattern,
        pattern_type,
        capture_group,
        networks,
        enabled,
        priority,
    ) in _DEFAULT_CHANNEL_PATTERNS:
        db.session.add(
            FccMatchChannelPattern(
                name=name,
                description=description,
                pattern=pattern,
                pattern_type=pattern_type,
                capture_group=capture_group,
                networks=_json_text(networks),
                enabled=enabled,
                priority=priority,
            )
        )

    for (
        name,
        description,
        pattern,
        pattern_type,
        extract_city,
        extract_state,
        city_group,
        state_group,
        enabled,
        priority,
    ) in _DEFAULT_LOCATION_PATTERNS:
        db.session.add(
            FccMatchLocationPattern(
                name=name,
                description=description,
                pattern=pattern,
                pattern_type=pattern_type,
                extract_city=extract_city,
                extract_state=extract_state,
                city_group=city_group,
                state_group=state_group,
                enabled=enabled,
                priority=priority,
            )
        )

    for (
        name,
        description,
        strategy_type,
        require_network,
        require_channel_number,
        require_state,
        require_city,
        match_nielsen_dma,
        match_community_city,
        match_community_state,
        enabled,
        priority,
    ) in _DEFAULT_STRATEGIES:
        db.session.add(
            FccMatchStrategy(
                name=name,
                description=description,
                strategy_type=strategy_type,
                require_network=require_network,
                require_channel_number=require_channel_number,
                require_state=require_state,
                require_city=require_city,
                match_nielsen_dma=match_nielsen_dma,
                match_community_city=match_community_city,
                match_community_state=match_community_state,
                enabled=enabled,
                priority=priority,
            )
        )

    db.session.commit()
