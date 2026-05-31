"""
EPG Constants and Patterns

Contains all constant definitions, patterns, and static data used across EPG modules.
"""

# Major broadcast networks that should match EPG network channels
MAJOR_BROADCAST_NETWORKS = {"ABC", "NBC", "CBS", "FOX", "PBS", "CW", "ION"}

# Fallback generic EPG channel IDs for networks without local market coverage
# Used as last resort when no local station EPG data is available
# Maps network name to (epg_channel_id, display_name) tuples in priority order
NETWORK_FALLBACK_EPG_IDS = {
    "CW": [("CW.us2", "CW")],
    # Add more networks as generic feeds become available
    # "ABC": [("ABC.National.Feed.us2", "ABC National Feed")],
    # "CBS": [("cbs-news", "CBS News 24/7")],  # Not a real affiliate substitute
    # "NBC": [("nbc-news-now", "NBC News NOW")],  # Not a real affiliate substitute
}

# PPV (Pay-Per-View) category patterns
# PPV channels update their names dynamically when events are scheduled,
# so they should not have traditional EPG mappings.
# These patterns match the category NAME (not channel names).
# Based on analysis of actual IPTV provider data, PPV categories typically
# have "PPV" somewhere in their category name.
PPV_CATEGORY_PATTERNS = [
    r"\bPPV\b",  # Most common: "UK| DAZN PPV", "US| ESPN+ PPV", "NL| MAX PPV"
    r"PAY[\s-]?PER[\s-]?VIEW",  # "Pay-Per-View", "Pay Per View", "PAY-PER-VIEW"
    # Note: We intentionally don't match generic "EVENT" categories as those
    # are often legitimate sports channels with regular EPG data.
    # PPV categories almost always have "PPV" in the name explicitly.
]

# PPV placeholder name patterns
# When no event is scheduled, PPV channels have generic placeholder names
# When an event IS scheduled, the provider changes the channel name to the event title
# We detect "inactive" PPV channels by matching these placeholder patterns.
#
# Based on analysis of actual IPTV provider channel names:
# - Inactive: "UK: DAZN PPV 1 ᴿᴬᵂ", "US: ESPN PLUS 01 PPV", "NL: MAX PPV 1 - NO EVENT STREAMING -"
# - Active: "UK: DAZN PPV 1 - UFC 300: Jones vs Miocic", "EPL 01: 20:00 Manchester United vs Newcastle"
PPV_PLACEHOLDER_PATTERNS = [
    # Explicit "NO EVENT" markers (very common)
    r"NO\s+EVENT\s+STREAMING",  # "NO EVENT STREAMING", "- NO EVENT STREAMING -"
    r"NO\s+EVENT\s+SCHEDULED",  # Less common variant
    r"NO\s+SCHEDULED\s+EVENT",  # Another variant
    # Basic numbered PPV channels without event info: "PPV 1", "PPV 2", "PPV-01"
    r"^(?:[A-Z]{2}[:\s])?(?:[A-Z0-9\+\s]+)?PPV[\s\-]*\d+\s*(?:ᴿᴬᵂ|ᴴᴰ|⁴ᴷ|4K|HD|SD)?$",
    # Event channels with just numbers: "EVENT 1", "VIDIO EVENT 1"
    r"EVENT\s+\d+\s*$",
    # Empty event slots: "PPV 1 -", "UFC 09:", ":MAX NL 05"
    r"(?:PPV|UFC|NBA|NHL|MLB|MLS|WNBA)\s*\d+\s*[:\-]?\s*$",
    # Placeholder colon format: ":Viaplay NL  14", ":MAX US 03"
    r"^:?\s*(?:[A-Z]+\s+)?(?:Viaplay|MAX|ESPN)\s+[A-Z]{2}\s+\d+\s*$",
    # Coming Soon/TBA placeholders
    r"^(?:COMING\s+SOON|TBA|TBD|OFFLINE).*$",
    # Florugby/generic sport numbered: "Florugby 00", "Florugby 01"
    r"^[A-Za-z]+\s+\d{2}\s*$",
    # Empty fixture slots: "GaaGo Fixtures 10:", "LOI 06 |"
    r"Fixtures?\s+\d+\s*[:\|]?\s*$",
    # NIFL/GAA empty: "NIFL 5 |", "ULSTER GAA 06 |"
    r"(?:NIFL|GAA|ULSTER)\s*\d+\s*\|?\s*$",
]

# Tag names that indicate east/west variants (used for auto-detection during sync)
EAST_TAGS = {"EAST", "E", "ET", "EST", "EASTERN"}
WEST_TAGS = {"WEST", "W", "PT", "PST", "PACIFIC", "WESTERN"}

# Feed direction markers that resemble W/K broadcast callsigns but are not station IDs.
# Channels like "NBC BRAVO WEST" must not match EPG callsign WEST.
FEED_DIRECTION_PSEUDO_CALLSIGNS = frozenset(
    tag for tag in (EAST_TAGS | WEST_TAGS) if len(tag) >= 3 and tag[0] in ("K", "W")
)

# Common suffixes/prefixes to strip when trying name variations
# These are quality/region markers that don't affect channel identity
STRIP_WORDS = {
    "hd",
    "sd",
    "fhd",
    "uhd",
    "4k",
    "8k",
    "the",
    "channel",
    "channels",
    "tv",
    "network",
    "networks",
    "television",
    "us",
    "uk",
    "ca",
    "au",
    "de",
    "fr",
    "es",
    "it",
    "east",
    "west",
    "pacific",
    "central",
    "plus",
    "extra",
    "max",
    "international",
    "world",
    "global",
}
