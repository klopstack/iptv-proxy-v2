"""Name and callsign normalization for EPG matching."""
import re
from typing import Optional, Set

from models import ChannelTag, Tag, db


class NormalizationMixin:
    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize a channel name for matching"""
        if not name:
            return ""
        name = name.lower()
        name = re.sub(r"[^a-z0-9\s]", "", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name

    @staticmethod
    def _get_channel_tags(account_id: int, stream_id: str) -> Set[str]:
        """Get all tags for a channel"""
        tag_rows = (
            db.session.query(Tag.name)
            .join(ChannelTag, Tag.id == ChannelTag.tag_id)
            .filter(ChannelTag.account_id == account_id, ChannelTag.stream_id == stream_id)
            .all()
        )
        return {row[0].upper() for row in tag_rows}

    # US State name to abbreviation mapping
    US_STATE_NAMES = {
        "ALABAMA": "AL",
        "ALASKA": "AK",
        "ARIZONA": "AZ",
        "ARKANSAS": "AR",
        "CALIFORNIA": "CA",
        "COLORADO": "CO",
        "CONNECTICUT": "CT",
        "DELAWARE": "DE",
        "FLORIDA": "FL",
        "GEORGIA": "GA",
        "HAWAII": "HI",
        "IDAHO": "ID",
        "ILLINOIS": "IL",
        "INDIANA": "IN",
        "IOWA": "IA",
        "KANSAS": "KS",
        "KENTUCKY": "KY",
        "LOUISIANA": "LA",
        "MAINE": "ME",
        "MARYLAND": "MD",
        "MASSACHUSETTS": "MA",
        "MICHIGAN": "MI",
        "MINNESOTA": "MN",
        "MISSISSIPPI": "MS",
        "MISSOURI": "MO",
        "MONTANA": "MT",
        "NEBRASKA": "NE",
        "NEVADA": "NV",
        "NEW HAMPSHIRE": "NH",
        "NEW JERSEY": "NJ",
        "NEW MEXICO": "NM",
        "NEW YORK": "NY",
        "NORTH CAROLINA": "NC",
        "NORTH DAKOTA": "ND",
        "OHIO": "OH",
        "OKLAHOMA": "OK",
        "OREGON": "OR",
        "PENNSYLVANIA": "PA",
        "RHODE ISLAND": "RI",
        "SOUTH CAROLINA": "SC",
        "SOUTH DAKOTA": "SD",
        "TENNESSEE": "TN",
        "TEXAS": "TX",
        "UTAH": "UT",
        "VERMONT": "VT",
        "VIRGINIA": "VA",
        "WASHINGTON": "WA",
        "WEST VIRGINIA": "WV",
        "WISCONSIN": "WI",
        "WYOMING": "WY",
    }
    # Valid US state abbreviations for parsing from compound tags
    US_STATE_ABBREVS = {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
        "PR",
        "VI",
        "GU",
    }

    @staticmethod
    def _extract_callsign(channel_id: str) -> Optional[str]:
        """Extract callsign from EPG channel ID"""
        if not channel_id:
            return None

        # Schedules Direct format
        sd_match = re.match(r"I(\d+)\.json\.schedulesdirect\.org", channel_id, re.IGNORECASE)
        if sd_match:
            return sd_match.group(1)

        # CALLSIGN.suffix format (e.g., KECI-DT.us_locals1, WHAS.us)
        # Match callsign before first dot - callsign can contain letters, numbers, and hyphens
        dot_match = re.match(r"^([A-Za-z][A-Za-z0-9\-]{2,9})\.", channel_id)
        if dot_match:
            return dot_match.group(1)

        # Simple callsign (no dot, reasonable length)
        if "." not in channel_id and len(channel_id) <= 10:
            return channel_id

        return None

    @staticmethod
    def _normalize_callsign(callsign: str) -> str:
        """Normalize callsign by removing common suffixes like -TV, -DT, -HD, etc."""
        if not callsign:
            return ""
        # Remove common broadcast suffixes
        return re.sub(r"-(TV|DT|HD|FM|AM|LP|CA|CD|LD|D\d?)$", "", callsign.upper())
