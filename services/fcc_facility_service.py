"""
FCC Facility Service

Downloads and manages FCC TV station registration data from the LMS database.
This provides authoritative callsign-to-city mapping for US TV stations.

Data source: https://enterpriseefiling.fcc.gov/dataentry/public/tv/lmsDatabase.html

The facility.dat file is a pipe-delimited text file containing all licensed
broadcast facilities (TV, FM, AM, etc.). We filter for TV-related service codes:
- DTV: Digital Television
- TV: Analog Television (legacy)
- LPT: Low Power Television
- LPD: Low Power Digital
- LPA: Low Power Analog
- LPX: Low Power Experimental

Key fields used:
- callsign: Station callsign (e.g., "KABC-TV", "WNBC")
- community_served_city: Licensed city of service
- community_served_state: State code (2-letter)
- network_affiliation: Network affiliation (ABC, NBC, CBS, FOX, etc.)
- nielsen_dma_rank: DMA market name (e.g., "New York", "Los Angeles")
- service_code: Service type (DTV, TV, LPT, etc.)
"""

import io
import logging
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from models import FccCorrection, FccFacility, db

logger = logging.getLogger(__name__)

# FCC LMS database URLs
FCC_BASE_URL = "https://enterpriseefiling.fcc.gov/dataentry/api/download/dbfile"
FCC_FACILITY_FILE = "facility.zip"

# TV-related service codes to import
TV_SERVICE_CODES = {"DTV", "TV", "LPT", "LPD", "LPA", "LPX"}

# Column indices in facility.dat (0-based)
# Header: active_ind|atsc3_ind|authorizing_act|callsign|callsign_effective_date|channel|...
COL_ACTIVE = 0
COL_CALLSIGN = 3
COL_CHANNEL = 5
COL_CITY = 7  # community_served_city
COL_STATE = 8  # community_served_state
COL_FACILITY_ID = 12
COL_FACILITY_STATUS = 13
COL_LAST_UPDATE = 18
COL_NETWORK = 21  # network_affiliation
COL_NIELSEN_DMA = 22  # nielsen_dma_rank (actually contains DMA name)
COL_SERVICE_CODE = 25
COL_STATION_TYPE = 26
COL_VIRTUAL_CHANNEL = 30  # tv_virtual_channel

# Major broadcast networks for normalization (case-insensitive matching)
MAJOR_NETWORKS = {
    "ABC",
    "NBC",
    "CBS",
    "FOX",
    "PBS",
    "CW",
    "ION",
    "UNIV",
    "TELE",
    "MNT",
    "MYNT",
    "IND",
    "INDEPENDENT",
    "UNIVISION",
    "TELEMUNDO",
}

# Tags that indicate VOD/24-7 content that should not be FCC-enriched
# These channels are not live broadcasts and shouldn't match to stations
# Note: "247" is used because the slash in "24/7" is removed during tag processing
VOD_EXCLUSION_TAGS = {
    "247",
    "VOD",
    "ON DEMAND",
    "MOVIES",
    "SERIES",
}


@dataclass
class CachedFccCorrection:
    """Cached FCC correction data to avoid SQLAlchemy DetachedInstanceError.

    When ORM objects are cached and accessed outside the session,
    lazy-loaded attributes cause DetachedInstanceError. This dataclass
    holds all needed attributes as plain Python types.
    """

    callsign: str
    facility_id: Optional[int]
    network_affiliation: Optional[str]
    tv_virtual_channel: Optional[str]
    nielsen_dma: Optional[str]
    community_city: Optional[str]
    community_state: Optional[str]

    @classmethod
    def from_orm(cls, correction: "FccCorrection") -> "CachedFccCorrection":
        """Create from ORM object while still in session."""
        return cls(
            callsign=correction.callsign,
            facility_id=correction.facility_id,
            network_affiliation=correction.network_affiliation,
            tv_virtual_channel=correction.tv_virtual_channel,
            nielsen_dma=correction.nielsen_dma,
            community_city=correction.community_city,
            community_state=correction.community_state,
        )


class FccFacilityService:
    """Service for managing FCC facility data"""

    # Cache corrections to avoid repeated DB queries
    _corrections_cache: Optional[Dict[str, CachedFccCorrection]] = None
    _corrections_cache_time: Optional[datetime] = None
    CORRECTIONS_CACHE_TTL = 300  # 5 minutes

    @classmethod
    def get_corrections(cls) -> Dict[str, CachedFccCorrection]:
        """Get all FCC corrections, cached for performance.

        Returns CachedFccCorrection dataclasses instead of ORM objects to avoid
        DetachedInstanceError when accessing attributes outside the session.

        Returns:
            Dict mapping callsign (uppercase) to CachedFccCorrection object
        """
        now = datetime.now()

        # Check if cache is valid
        if (
            cls._corrections_cache is not None
            and cls._corrections_cache_time is not None
            and (now - cls._corrections_cache_time).total_seconds() < cls.CORRECTIONS_CACHE_TTL
        ):
            return cls._corrections_cache

        # Refresh cache
        try:
            corrections = FccCorrection.query.all()
            cls._corrections_cache = {c.callsign.upper(): CachedFccCorrection.from_orm(c) for c in corrections}
            cls._corrections_cache_time = now
            logger.debug(f"Loaded {len(cls._corrections_cache)} FCC corrections into cache")
        except Exception as e:
            logger.warning(f"Failed to load FCC corrections: {e}")
            cls._corrections_cache = {}
            cls._corrections_cache_time = now

        return cls._corrections_cache

    @classmethod
    def clear_corrections_cache(cls):
        """Clear the corrections cache (e.g., after adding new corrections)"""
        cls._corrections_cache = None
        cls._corrections_cache_time = None

    @classmethod
    def apply_correction(cls, facility: FccFacility) -> FccFacility:
        """Apply any corrections to an FCC facility record.

        This modifies the facility object in-place with corrected values.
        Only non-NULL correction fields are applied.

        Args:
            facility: FccFacility object to potentially correct

        Returns:
            The same facility object, potentially modified
        """
        if not facility or not facility.callsign:
            return facility

        corrections = cls.get_corrections()
        callsign_upper = facility.callsign.upper()

        # Look for exact match first
        correction = corrections.get(callsign_upper)

        # Also try without suffix (e.g., WBMA-LD -> WBMA)
        if not correction and "-" in callsign_upper:
            base_callsign = callsign_upper.split("-")[0]
            correction = corrections.get(base_callsign)

        if correction:
            # Apply non-NULL corrections
            if correction.network_affiliation is not None:
                facility.network_affiliation = correction.network_affiliation
                logger.debug(
                    f"Applied network_affiliation correction to {facility.callsign}: {correction.network_affiliation}"
                )
            if correction.tv_virtual_channel is not None:
                facility.tv_virtual_channel = correction.tv_virtual_channel
                logger.debug(
                    f"Applied tv_virtual_channel correction to {facility.callsign}: {correction.tv_virtual_channel}"
                )
            if correction.nielsen_dma is not None:
                facility.nielsen_dma = correction.nielsen_dma
            if correction.community_city is not None:
                facility.community_city = correction.community_city
            if correction.community_state is not None:
                facility.community_state = correction.community_state

        return facility

    @classmethod
    def query_with_corrections(cls, query) -> List[FccFacility]:
        """Execute an FCC facility query and apply corrections to results.

        Args:
            query: SQLAlchemy query for FccFacility

        Returns:
            List of FccFacility objects with corrections applied
        """
        facilities = query.all()
        return [cls.apply_correction(f) for f in facilities]

    @classmethod
    def first_with_correction(cls, query) -> Optional[FccFacility]:
        """Execute an FCC facility query for first result and apply corrections.

        Args:
            query: SQLAlchemy query for FccFacility

        Returns:
            FccFacility object with corrections applied, or None
        """
        facility = query.first()
        return cls.apply_correction(facility) if facility else None

    @staticmethod
    def _parse_network_affiliation(raw_network: Optional[str]) -> Optional[str]:
        """Parse and normalize network affiliation from FCC data.

        The FCC network_affiliation field can contain complex data with
        subchannel information that needs to be parsed down to the primary
        network only.

        Examples of raw data and expected output:
        - "ABC" -> "ABC"
        - "Fox" -> "FOX"
        - "FOX/COZI-TV" -> "FOX"
        - "5.1 FOX, 5.2 SSSEN, 5.3 Court TV Mystery" -> "FOX"
        - "FOX (25.1); Comet TV (25.2) & Laff TV (25.3)" -> "FOX"
        - "Independent" -> "INDEPENDENT"

        Args:
            raw_network: Raw network_affiliation value from FCC data

        Returns:
            Normalized primary network name (uppercase), or None if empty/invalid
        """
        import re

        if not raw_network or not raw_network.strip():
            return None

        network = raw_network.strip()

        # Try to extract primary network using various patterns

        # Pattern 1: Look for major network at start (with optional channel prefix)
        # e.g., "5.1 FOX, ..." or "FOX (25.1); ..."
        for major in MAJOR_NETWORKS:
            # Check if network starts with or contains major network name
            # Account for channel numbers like "5.1 FOX" or "25.1 FOX"
            pattern = rf"(?:^|\b)(?:\d+(?:\.\d+)?\s+)?({re.escape(major)})\b"
            match = re.search(pattern, network, re.IGNORECASE)
            if match:
                return match.group(1).upper()

        # Pattern 2: Split on common delimiters and take first part
        # Handle: "/" ";" "," "&" and parentheses
        # First, remove parenthetical content (subchannel numbers)
        cleaned = re.sub(r"\s*\([^)]*\)", "", network)

        # Split on delimiters
        parts = re.split(r"[/;,&]+", cleaned)
        if parts:
            first_part = parts[0].strip()
            # Remove leading channel numbers (e.g., "5.1 FOX" -> "FOX")
            first_part = re.sub(r"^\d+(?:\.\d+)?\s+", "", first_part)
            if first_part:
                return first_part.upper()

        # Fallback: just uppercase the whole thing if it's short enough
        # (to avoid garbage data)
        if len(network) <= 20:
            return network.upper()

        return None

    @staticmethod
    def _detect_network_from_name(channel_name: str) -> Optional[str]:
        """Detect network affiliation from channel name.

        Some stations are listed as "Independent" in FCC data but are clearly
        network affiliates based on their channel names (e.g., "US: CW (KSTW)").

        This method extracts network hints from channel names to supplement
        or override FCC network data.

        Args:
            channel_name: Channel name to analyze

        Returns:
            Network name if detected, None otherwise
        """
        import re

        if not channel_name:
            return None

        name_upper = channel_name.upper()

        # Networks to look for in channel names (excluding INDEPENDENT/IND)
        # Order matters - check more specific patterns first
        network_patterns = [
            (r"\bCW\b", "CW"),
            (r"\bABC\b", "ABC"),
            (r"\bNBC\b", "NBC"),
            (r"\bCBS\b", "CBS"),
            (r"\bFOX\b", "FOX"),
            (r"\bPBS\b", "PBS"),
            (r"\bION\b", "ION"),
            (r"\bMYNT\b", "MYNETWORK"),
            (r"\bMY\s*NETWORK", "MYNETWORK"),
            (r"\bUNIVISION\b", "UNIVISION"),
            (r"\bUNIV\b", "UNIVISION"),
            (r"\bTELEMUNDO\b", "TELEMUNDO"),
            (r"\bTELE\b", "TELEMUNDO"),
        ]

        for pattern, network in network_patterns:
            if re.search(pattern, name_upper):
                return network

        return None

    @staticmethod
    def get_download_url() -> str:
        """Get the URL for the current facility.zip file.

        The FCC updates data daily, so we use the Current_LMS_Dump.zip
        which always contains the latest data.
        """
        return f"{FCC_BASE_URL}/Current_LMS_Dump.zip"

    @staticmethod
    def get_facility_url() -> str:
        """Get URL for just the facility.zip file (smaller download)."""
        # Try to get today's date-specific file first
        today = datetime.now().strftime("%m-%d-%Y")
        return f"{FCC_BASE_URL}/{today}/{FCC_FACILITY_FILE}"

    @staticmethod
    def download_facility_data() -> Optional[bytes]:
        """Download the facility.zip file from FCC.

        Returns:
            Raw bytes of facility.dat content, or None on failure
        """
        url = FccFacilityService.get_facility_url()
        logger.info(f"Downloading FCC facility data from {url}")

        try:
            # Use 10 minute timeout for large file from rate-limited server
            response = requests.get(url, timeout=600)
            response.raise_for_status()

            # Extract facility.dat from the zip
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                with zf.open("facility.dat") as f:
                    return f.read()

        except requests.RequestException as e:
            logger.error(f"Failed to download FCC facility data: {e}")
            return None
        except (zipfile.BadZipFile, KeyError) as e:
            logger.error(f"Failed to extract facility.dat from zip: {e}")
            return None

    @staticmethod
    def parse_facility_data(data: bytes) -> List[Dict]:
        """Parse facility.dat pipe-delimited content.

        Args:
            data: Raw bytes of facility.dat

        Returns:
            List of dicts with parsed facility records (TV only)
        """
        records = []
        # Handle both Windows (\r\n) and Unix (\n) line endings
        # Lines end with ^| followed by line ending
        text = data.decode("utf-8", errors="replace")
        # Normalize line endings and split on ^| record delimiter
        text = text.replace("\r\n", "\n")
        lines = text.split("^|\n")

        # Skip header line
        for i, line in enumerate(lines[1:], start=2):
            if not line.strip():
                continue

            fields = line.split("|")
            if len(fields) < 31:
                continue

            # Only process TV-related service codes
            service_code = fields[COL_SERVICE_CODE].strip().upper()
            if service_code not in TV_SERVICE_CODES:
                continue

            callsign = fields[COL_CALLSIGN].strip().upper()
            if not callsign:
                continue

            # Parse facility_id
            try:
                facility_id = int(fields[COL_FACILITY_ID]) if fields[COL_FACILITY_ID].strip() else None
            except ValueError:
                facility_id = None

            # Parse last_update timestamp
            last_update = None
            if fields[COL_LAST_UPDATE].strip():
                try:
                    last_update = datetime.strptime(fields[COL_LAST_UPDATE].strip()[:19], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass

            # Extract DMA rank from nielsen_dma field if it's a number
            nielsen_dma = fields[COL_NIELSEN_DMA].strip()
            dma_rank = None
            # DMA field sometimes contains just the market name, sometimes rank too

            # Parse and normalize network affiliation
            raw_network = fields[COL_NETWORK].strip() or None
            network_affiliation = FccFacilityService._parse_network_affiliation(raw_network)

            records.append(
                {
                    "facility_id": facility_id,
                    "callsign": callsign,
                    "service_code": service_code,
                    "station_type": fields[COL_STATION_TYPE].strip() or None,
                    "community_city": fields[COL_CITY].strip().upper() or None,
                    "community_state": fields[COL_STATE].strip().upper() or None,
                    "channel": fields[COL_CHANNEL].strip() or None,
                    "tv_virtual_channel": fields[COL_VIRTUAL_CHANNEL].strip() or None,
                    "network_affiliation": network_affiliation,
                    "nielsen_dma": nielsen_dma or None,
                    "nielsen_dma_rank": dma_rank,
                    "active": fields[COL_ACTIVE].strip().upper() == "Y",
                    "facility_status": fields[COL_FACILITY_STATUS].strip() or None,
                    "last_update": last_update,
                }
            )

        logger.info(f"Parsed {len(records)} TV facility records from FCC data")
        return records

    @staticmethod
    def sync_facilities(records: List[Dict]) -> Dict:
        """Sync parsed facility records to database.

        Args:
            records: List of facility dicts from parse_facility_data

        Returns:
            Dict with sync statistics
        """
        stats = {
            "added": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": 0,
        }

        # Build lookup of existing records by facility_id
        existing_by_fid: Dict[int, FccFacility] = {}
        existing_by_callsign: Dict[str, List[FccFacility]] = {}

        for facility in FccFacility.query.all():
            if facility.facility_id:
                existing_by_fid[facility.facility_id] = facility
            if facility.callsign:
                if facility.callsign not in existing_by_callsign:
                    existing_by_callsign[facility.callsign] = []
                existing_by_callsign[facility.callsign].append(facility)

        for record in records:
            try:
                existing = None

                # Try to find by facility_id first (most reliable)
                if record["facility_id"] and record["facility_id"] in existing_by_fid:
                    existing = existing_by_fid[record["facility_id"]]

                if existing:
                    # Update existing record
                    changed = False
                    for key, value in record.items():
                        if getattr(existing, key) != value:
                            setattr(existing, key, value)
                            changed = True

                    if changed:
                        stats["updated"] += 1
                    else:
                        stats["unchanged"] += 1
                else:
                    # Create new record
                    facility = FccFacility(**record)
                    db.session.add(facility)
                    stats["added"] += 1

            except Exception as e:
                logger.warning(f"Error processing facility record {record.get('callsign')}: {e}")
                stats["errors"] += 1

        try:
            db.session.commit()
        except Exception as e:
            logger.error(f"Error committing facility records: {e}")
            db.session.rollback()
            raise

        logger.info(
            f"FCC facility sync complete: added={stats['added']}, "
            f"updated={stats['updated']}, unchanged={stats['unchanged']}, "
            f"errors={stats['errors']}"
        )
        return stats

    @staticmethod
    def full_sync() -> Dict:
        """Download and sync all FCC facility data.

        Returns:
            Dict with download and sync statistics
        """
        result = {
            "success": False,
            "message": "",
            "stats": {},
        }

        # Download data
        data = FccFacilityService.download_facility_data()
        if not data:
            result["message"] = "Failed to download FCC facility data"
            return result

        # Parse data
        records = FccFacilityService.parse_facility_data(data)
        if not records:
            result["message"] = "No TV facility records found in FCC data"
            return result

        # Sync to database
        try:
            stats = FccFacilityService.sync_facilities(records)
            result["success"] = True
            result["message"] = f"Synced {len(records)} TV facilities"
            result["stats"] = stats
        except Exception as e:
            result["message"] = f"Error syncing facilities: {e}"

        return result

    # =========================================================================
    # Lookup methods for EPG/channel matching
    # =========================================================================

    @staticmethod
    def lookup_by_callsign(callsign: str, service_codes: Optional[Set[str]] = None) -> Optional[FccFacility]:
        """Look up facility by callsign.

        Args:
            callsign: Station callsign (e.g., "KABC-TV", "WNBC")
            service_codes: Optional set of service codes to filter by

        Returns:
            FccFacility record or None
        """
        callsign = callsign.upper().strip()

        # Try exact match first
        query = FccFacility.query.filter(FccFacility.callsign == callsign)
        if service_codes:
            query = query.filter(FccFacility.service_code.in_(service_codes))

        # Prefer DTV over legacy TV, and main stations over translators
        query = query.order_by(
            db.case(
                (FccFacility.service_code == "DTV", 1),
                (FccFacility.service_code == "TV", 2),
                else_=3,
            ),
            db.case(
                (FccFacility.station_type == "M", 1),
                else_=2,
            ),
        )

        facility = query.first()
        if facility:
            return facility

        # Try without -TV, -DT suffixes
        for suffix in ["-TV", "-DT", "TV", "DT"]:
            if callsign.endswith(suffix):
                base_callsign = callsign[: -len(suffix)]
                facility = FccFacility.query.filter(FccFacility.callsign.like(f"{base_callsign}%")).first()
                if facility:
                    return facility

        # Try adding common suffixes
        for suffix in ["-TV", "-DT", "-LD", "-LP", "-CD"]:
            facility = FccFacility.query.filter(FccFacility.callsign == f"{callsign}{suffix}").first()
            if facility:
                return facility

        # Only do prefix matching for callsigns that are at least 4 characters
        # This prevents short strings like "WAR" from matching "WARP-LD"
        if len(callsign) >= 4:
            # Try prefix match (e.g., KABC matches KABC-TV)
            # But only if the prefix is the complete base callsign
            facility = FccFacility.query.filter(FccFacility.callsign.like(f"{callsign}-%")).first()
            if facility:
                return facility

        return None

    @staticmethod
    def lookup_by_city_state(city: str, state: str, network: Optional[str] = None) -> List[FccFacility]:
        """Look up facilities by city and state.

        Args:
            city: City name
            state: State code (2-letter)
            network: Optional network affiliation to filter by

        Returns:
            List of matching FccFacility records
        """
        city = city.upper().strip()
        state = state.upper().strip()

        query = FccFacility.query.filter(FccFacility.community_city == city, FccFacility.community_state == state)

        if network:
            query = query.filter(FccFacility.network_affiliation.ilike(f"%{network}%"))

        return query.all()

    @staticmethod
    def lookup_by_dma(dma_name: str) -> List[FccFacility]:
        """Look up facilities by DMA (market) name.

        Args:
            dma_name: DMA market name (e.g., "New York", "Los Angeles")

        Returns:
            List of matching FccFacility records
        """
        return FccFacility.query.filter(FccFacility.nielsen_dma.ilike(f"%{dma_name}%")).all()

    @staticmethod
    def get_city_for_callsign(callsign: str) -> Optional[Tuple[str, str]]:
        """Get city and state for a callsign.

        Convenience method for the most common lookup pattern.

        Args:
            callsign: Station callsign

        Returns:
            Tuple of (city, state) or None
        """
        facility = FccFacilityService.lookup_by_callsign(callsign)
        if facility and facility.community_city and facility.community_state:
            return (facility.community_city, facility.community_state)
        return None

    @staticmethod
    def get_callsigns_for_city(city: str, state: str) -> List[str]:
        """Get all callsigns for a city.

        Args:
            city: City name
            state: State code

        Returns:
            List of callsigns
        """
        facilities = FccFacilityService.lookup_by_city_state(city, state)
        return [f.callsign for f in facilities if f.callsign]

    @staticmethod
    def get_stats() -> Dict:
        """Get statistics about the FCC facility data.

        Returns:
            Dict with counts and data freshness info
        """
        total = FccFacility.query.count()
        by_service = (
            db.session.query(FccFacility.service_code, db.func.count()).group_by(FccFacility.service_code).all()
        )
        by_network = (
            db.session.query(FccFacility.network_affiliation, db.func.count())
            .filter(FccFacility.network_affiliation.isnot(None))
            .group_by(FccFacility.network_affiliation)
            .order_by(db.func.count().desc())
            .limit(20)
            .all()
        )
        latest_update = db.session.query(db.func.max(FccFacility.updated_at)).scalar()

        # Get top DMAs for the Popular DMAs sidebar
        top_dmas = (
            db.session.query(FccFacility.nielsen_dma, db.func.count())
            .filter(FccFacility.nielsen_dma.isnot(None))
            .filter(FccFacility.nielsen_dma != "")
            .group_by(FccFacility.nielsen_dma)
            .order_by(db.func.count().desc())
            .limit(20)
            .all()
        )

        return {
            "total_facilities": total,
            "by_service_code": dict(by_service),
            "top_networks": dict(by_network),
            "top_dmas": [[dma, count] for dma, count in top_dmas if dma],
            "last_sync": latest_update.isoformat() if latest_update else None,
        }

    @staticmethod
    def get_dma_list() -> List[Dict]:
        """Get list of all unique DMA (market) names with counts.

        Returns:
            List of dicts with dma name and count
        """
        results = (
            db.session.query(FccFacility.nielsen_dma, db.func.count())
            .filter(FccFacility.nielsen_dma.isnot(None))
            .filter(FccFacility.nielsen_dma != "")
            .group_by(FccFacility.nielsen_dma)
            .order_by(FccFacility.nielsen_dma)
            .all()
        )
        return [{"name": dma, "count": count} for dma, count in results if dma]

    @staticmethod
    def get_network_list() -> List[Dict]:
        """Get list of all unique network affiliations with counts.

        Returns:
            List of dicts with network name and count
        """
        results = (
            db.session.query(FccFacility.network_affiliation, db.func.count())
            .filter(FccFacility.network_affiliation.isnot(None))
            .filter(FccFacility.network_affiliation != "")
            .group_by(FccFacility.network_affiliation)
            .order_by(db.func.count().desc())
            .all()
        )
        return [{"name": network, "count": count} for network, count in results if network]

    # =========================================================================
    # Channel Enrichment methods
    # =========================================================================

    @staticmethod
    def extract_callsign_from_name(channel_name: str) -> Optional[str]:
        """Extract a potential callsign from a channel name.

        Callsigns are typically found in parentheses in channel names like:
        - "US: NBC (WNBC)" or "US: CW (KSTW)"
        - "US: ABC 7 (KABC) Los Angeles"

        We prioritize parenthesized callsigns as they are more reliable.

        Args:
            channel_name: Channel name to search

        Returns:
            Extracted callsign or None
        """
        import re

        name_upper = channel_name.upper()

        # Pattern for callsigns: K or W followed by 2-4 letters, optionally with suffix
        # Suffixes can include: -TV, -DT, -CD, -HD, -LP, -LD, -FM
        # And may have a subchannel number like -CD2, -LD2, -DT2
        callsign_pattern = r"[KW][A-Z]{2,4}(?:-(?:TV|DT|CD|HD|LP|LD|FM)\d?)?"

        # First, try to find callsign in parentheses - most reliable
        # Handle patterns like "(KABC)" or "(KABC-TV)" or "(WSVW/WHSV)" or "(WSVF-CD2)"
        paren_pattern = rf"\(({callsign_pattern})(?:/[A-Z]{{3,5}})?\)"
        paren_match = re.search(paren_pattern, name_upper)
        if paren_match:
            callsign = paren_match.group(1)
            # Strip any suffix for consistency (including subchannel numbers)
            callsign = re.sub(r"-(?:TV|DT|CD|HD|LP|LD|FM)\d?$", "", callsign)
            if len(callsign) >= 3:
                return callsign

        # If no parenthesized callsign, look for callsign patterns elsewhere
        # but be more conservative - require at least 4 characters
        matches = re.findall(rf"\b({callsign_pattern})\b", name_upper)
        if matches:
            for match in matches:
                # Strip any suffix (including subchannel numbers)
                callsign = re.sub(r"-(?:TV|DT|CD|HD|LP|LD|FM)\d?$", "", match)
                # Require at least 4 characters for non-parenthesized matches
                if len(callsign) >= 4:
                    return callsign

        return None

    @staticmethod
    def preview_channel_enrichment(account_id: int) -> List[Dict]:
        """Preview potential FCC-based enrichment for an account's channels.

        Analyzes channel names for potential callsign matches and shows
        what tags would be applied. Only includes channels tagged with "US"
        since FCC data is only relevant for US stations.

        Args:
            account_id: Account ID to preview

        Returns:
            List of dicts with channel info and potential enrichments
        """
        from models import Channel, ChannelTag, Tag

        matches: List[Dict[str, Any]] = []

        # Get the US tag ID if it exists
        us_tag = Tag.query.filter(Tag.name.ilike("US")).first()
        if not us_tag:
            # No US tag exists, so no channels can be enriched
            return matches

        # Get stream_ids for channels with the US tag
        us_channel_stream_ids = set(
            ct.stream_id for ct in ChannelTag.query.filter_by(account_id=account_id, tag_id=us_tag.id).all()
        )

        if not us_channel_stream_ids:
            # No US-tagged channels
            return matches

        # Get VOD exclusion tag IDs to filter out non-live content
        vod_tag_ids = set()
        for vod_tag_name in VOD_EXCLUSION_TAGS:
            tag = Tag.query.filter(Tag.name.ilike(vod_tag_name)).first()
            if tag:
                vod_tag_ids.add(tag.id)

        # Get stream_ids that have VOD exclusion tags (to skip them)
        excluded_stream_ids = set()
        if vod_tag_ids:
            excluded_tags = ChannelTag.query.filter(
                ChannelTag.account_id == account_id, ChannelTag.tag_id.in_(vod_tag_ids)
            ).all()
            excluded_stream_ids = {ct.stream_id for ct in excluded_tags}

        # Only process channels that have the US tag
        channels = Channel.query.filter(
            Channel.account_id == account_id, Channel.stream_id.in_(us_channel_stream_ids)
        ).all()

        for channel in channels:
            # Skip channels with VOD exclusion tags
            if channel.stream_id in excluded_stream_ids:
                continue

            # Try to extract callsign from channel name
            callsign = FccFacilityService.extract_callsign_from_name(channel.name)
            if not callsign:
                continue

            # Look up in FCC data
            facility = FccFacilityService.lookup_by_callsign(callsign)
            if not facility:
                continue

            # Validate that the extracted callsign reasonably matches the FCC callsign
            # The base callsigns should match (ignoring -TV, -LD, etc. suffixes)
            fcc_base = facility.callsign.split("-")[0] if facility.callsign else ""
            if not fcc_base.startswith(callsign) and callsign != fcc_base:
                # The callsigns don't match well enough - skip this match
                continue

            matches.append(
                {
                    "stream_id": channel.stream_id,
                    "account_id": channel.account_id,
                    "channel_name": channel.name,
                    "extracted_callsign": callsign,
                    "fcc_callsign": facility.callsign,
                    "city": facility.community_city,
                    "state": facility.community_state,
                    "network": facility.network_affiliation,
                    "dma": facility.nielsen_dma,
                    "potential_tags": FccFacilityService._get_potential_tags(facility, channel.name),
                }
            )

        return matches

    @staticmethod
    def _get_potential_tags(facility: FccFacility, channel_name: Optional[str] = None) -> List[str]:
        """Get potential tags from an FCC facility record.

        Args:
            facility: FccFacility record
            channel_name: Optional channel name for network detection fallback

        Returns:
            List of tag strings
        """
        tags = []

        network = None
        if facility.network_affiliation:
            # Normalize network name (handles legacy data that may not have been parsed)
            network = FccFacilityService._parse_network_affiliation(facility.network_affiliation)
            if network:
                # If FCC says "INDEPENDENT" but channel name indicates a network,
                # use the detected network instead
                if network in ("INDEPENDENT", "IND") and channel_name:
                    detected = FccFacilityService._detect_network_from_name(channel_name)
                    if detected:
                        network = detected

        # If FCC has no network data, try to detect from channel name
        if not network and channel_name:
            network = FccFacilityService._detect_network_from_name(channel_name)

        if network:
            tags.append(f"NETWORK:{network}")

        if facility.nielsen_dma:
            tags.append(f"DMA:{facility.nielsen_dma.upper()}")

        if facility.community_state:
            tags.append(f"STATE:{facility.community_state.upper()}")

        return tags

    @staticmethod
    def apply_channel_enrichment(account_id: int, options: Dict) -> Dict:
        """Apply FCC-based enrichment to channels.

        Creates tags for channels based on FCC data matches.

        Args:
            account_id: Account ID to enrich
            options: Dict with options:
                - create_network_tags: bool
                - create_dma_tags: bool
                - create_state_tags: bool

        Returns:
            Dict with enrichment results
        """
        from models import ChannelTag, Tag

        # Use typed variables for counters
        tags_created = 0
        channel_tags_added = 0
        errors: List[str] = []

        # Get preview matches
        matches = FccFacilityService.preview_channel_enrichment(account_id)
        channels_matched = len(matches)

        if not matches:
            return {
                "success": True,
                "message": "No channels matched FCC data",
                "channels_matched": 0,
                "tags_created": 0,
                "channel_tags_added": 0,
                "errors": [],
            }

        # Cache for tag lookups/creation
        tag_cache: Dict[str, Tag] = {}

        def get_or_create_tag(name: str) -> Tag:
            """Get existing tag or create new one."""
            nonlocal tags_created
            if name in tag_cache:
                return tag_cache[name]

            tag = Tag.query.filter_by(name=name).first()
            if not tag:
                tag = Tag(name=name)
                db.session.add(tag)
                db.session.flush()
                tags_created += 1

            tag_cache[name] = tag
            return tag

        # Apply enrichment
        for match in matches:
            try:
                stream_id = match["stream_id"]
                tags_to_add = []

                if options.get("create_network_tags"):
                    network = None
                    if match.get("network"):
                        # Normalize network name before creating tag
                        network = FccFacilityService._parse_network_affiliation(match["network"])
                        if network:
                            # If FCC says "INDEPENDENT" but channel name indicates a network,
                            # use the detected network instead
                            if network in ("INDEPENDENT", "IND") and match.get("channel_name"):
                                detected = FccFacilityService._detect_network_from_name(match["channel_name"])
                                if detected:
                                    network = detected

                    # If FCC has no network data, try to detect from channel name
                    if not network and match.get("channel_name"):
                        network = FccFacilityService._detect_network_from_name(match["channel_name"])

                    if network:
                        tags_to_add.append(f"NETWORK:{network}")

                if options.get("create_dma_tags") and match.get("dma"):
                    tags_to_add.append(f"DMA:{match['dma'].upper()}")

                if options.get("create_state_tags") and match.get("state"):
                    tags_to_add.append(f"STATE:{match['state'].upper()}")

                for tag_name in tags_to_add:
                    tag = get_or_create_tag(tag_name)

                    # Check if channel-tag association exists
                    existing = ChannelTag.query.filter_by(
                        account_id=account_id, stream_id=stream_id, tag_id=tag.id
                    ).first()

                    if not existing:
                        channel_tag = ChannelTag(
                            account_id=account_id,
                            stream_id=stream_id,
                            tag_id=tag.id,
                            source=ChannelTag.SOURCE_ENRICHMENT,
                        )
                        db.session.add(channel_tag)
                        channel_tags_added += 1

            except Exception as e:
                errors.append(f"Error processing channel {match.get('channel_name')}: {e}")

        try:
            db.session.commit()
            return {
                "success": True,
                "message": f"Enriched {channels_matched} channels with {channel_tags_added} tag associations",
                "channels_matched": channels_matched,
                "tags_created": tags_created,
                "channel_tags_added": channel_tags_added,
                "errors": errors,
            }
        except Exception as e:
            db.session.rollback()
            return {
                "success": False,
                "message": f"Error saving enrichment: {e}",
                "channels_matched": channels_matched,
                "tags_created": 0,
                "channel_tags_added": 0,
                "errors": errors,
            }
