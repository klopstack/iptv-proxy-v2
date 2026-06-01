"""
EPG Utility Functions

Contains utility functions for XMLTV handling, callsign extraction,
time manipulation, and other common operations.
"""
import gzip
import io
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Many Xtream/Cloudflare providers reject the default python-requests User-Agent (HTTP 520).
XMLTV_FETCH_USER_AGENT = "9XtreamPlayer"
XMLTV_FETCH_TIMEOUT = 600


def fetch_xmltv_url_content(source) -> bytes:
    """
    Download raw XMLTV bytes for an xmltv_url EPG source.

    Account-linked sources use IPTVService (Xtream xmltv.php with provider headers).
    Other URLs use requests with a player User-Agent instead of python-requests.
    """
    if source.account_id:
        from models import Account, db
        from services.iptv_service import get_iptv_service_for_account

        account = db.session.get(Account, source.account_id)
        if account:
            return get_iptv_service_for_account(account).get_xmltv()

    if not source.url:
        raise ValueError("No URL configured for this source")

    import requests

    url = normalize_xmltv_url(source.url)
    response = requests.get(
        url,
        timeout=XMLTV_FETCH_TIMEOUT,
        headers={"User-Agent": XMLTV_FETCH_USER_AGENT},
    )
    response.raise_for_status()
    return response.content


def extract_callsign_from_xmltv_id(xmltv_id: str) -> Optional[str]:
    """
    Extract a callsign/identifier from various XMLTV channel ID formats.

    Args:
        xmltv_id: The XMLTV channel ID string

    Returns:
        Extracted callsign or None if extraction fails

    Examples:
        "ESPN.us" -> "ESPN"
        "AntennaTV.us" -> "AntennaTV"
        "I10021.json.schedulesdirect.org" -> "10021"
        "BBC One" -> "BBC One"
        "CNN" -> "CNN"
    """
    if not xmltv_id:
        return None

    # Pattern 1: Schedules Direct format (I{station_id}.json.schedulesdirect.org)
    sd_match = re.match(r"I(\d+)\.json\.schedulesdirect\.org", xmltv_id, re.IGNORECASE)
    if sd_match:
        return sd_match.group(1)

    # Pattern 2: CALLSIGN.country or CALLSIGN.tld (e.g., ESPN.us, BBC1.uk)
    # Match alphanumeric callsign before the first dot
    dot_match = re.match(r"^([A-Za-z0-9]+(?:[A-Za-z0-9\-]*[A-Za-z0-9])?)\.(?:[a-z]{2,}|[A-Z]{2,})$", xmltv_id)
    if dot_match:
        return dot_match.group(1)

    # Pattern 3: Return as-is if it looks like a simple callsign (no dots, reasonable length)
    if "." not in xmltv_id and len(xmltv_id) <= 20:
        return xmltv_id

    # Pattern 4: Try to extract first segment before any dot
    if "." in xmltv_id:
        first_segment = xmltv_id.split(".")[0]
        if first_segment and len(first_segment) >= 2:
            return first_segment

    return xmltv_id


def make_sd_xmltv_id(station_id: str) -> str:
    """
    Create a Schedules Direct style XMLTV channel ID.

    Args:
        station_id: The numeric Schedules Direct station ID

    Returns:
        XMLTV-format ID like "I10021.json.schedulesdirect.org"
    """
    return f"I{station_id}.json.schedulesdirect.org"


def normalize_xmltv_url(url: str) -> str:
    """
    Normalize an XMLTV URL to ensure it returns raw content.

    Converts GitHub blob URLs to raw.githubusercontent.com URLs.

    Args:
        url: The URL to normalize

    Returns:
        The normalized URL

    Examples:
        "https://github.com/user/repo/blob/main/guide.xml"
        -> "https://raw.githubusercontent.com/user/repo/main/guide.xml"
    """
    # Convert GitHub blob URLs to raw URLs
    github_blob_pattern = r"^https?://github\.com/([^/]+)/([^/]+)/blob/(.+)$"
    match = re.match(github_blob_pattern, url)
    if match:
        owner, repo, path = match.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{path}"
    return url


def shift_xmltv_time(time_str: str, hours: int) -> str:
    """
    Shift an XMLTV datetime string by a number of hours.

    XMLTV format: YYYYMMDDHHmmss +ZZZZ (e.g., "20231215140000 +0000")

    Args:
        time_str: XMLTV datetime string
        hours: Number of hours to shift (negative for earlier)

    Returns:
        Shifted XMLTV datetime string
    """
    if not time_str:
        return time_str

    # Split off timezone if present
    parts = time_str.split()
    datetime_part = parts[0]
    tz_part = parts[1] if len(parts) > 1 else "+0000"

    # Parse datetime
    try:
        if len(datetime_part) >= 14:
            dt = datetime.strptime(datetime_part[:14], "%Y%m%d%H%M%S")
        elif len(datetime_part) >= 12:
            dt = datetime.strptime(datetime_part[:12], "%Y%m%d%H%M")
        elif len(datetime_part) >= 8:
            dt = datetime.strptime(datetime_part[:8], "%Y%m%d")
        else:
            return time_str
    except ValueError:
        return time_str

    # Apply shift
    dt = dt + timedelta(hours=hours)

    # Format back to XMLTV format
    return f"{dt.strftime('%Y%m%d%H%M%S')} {tz_part}"


def decompress_content(content: bytes) -> bytes:
    """
    Decompress gzipped content if necessary.

    Args:
        content: Raw bytes that may be gzip-compressed

    Returns:
        Decompressed bytes, or original content if not gzipped
    """
    # Check for gzip magic bytes
    if content[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(content)
        except gzip.BadGzipFile:
            logger.warning("Content has gzip header but failed to decompress")
            return content
    return content


def get_decompressing_stream(content: bytes) -> io.BufferedIOBase:
    """
    Get a file-like object for reading content, with streaming decompression if gzipped.

    Args:
        content: Raw bytes that may be gzip-compressed

    Returns:
        A file-like object for reading the (decompressed) content
    """
    # Check for gzip magic bytes
    if content[:2] == b"\x1f\x8b":
        # Use streaming gzip decompression
        return gzip.GzipFile(fileobj=io.BytesIO(content), mode="rb")
    return io.BytesIO(content)


def copy_element(elem: ET.Element) -> ET.Element:
    """
    Deep copy an XML element.

    Args:
        elem: Element to copy

    Returns:
        New element with all attributes and children copied
    """
    new_elem = ET.Element(elem.tag, elem.attrib)
    new_elem.text = elem.text
    new_elem.tail = elem.tail
    for child in elem:
        new_elem.append(copy_element(child))
    return new_elem


def parse_xmltv_time(time_str: str) -> Optional[datetime]:
    """Parse XMLTV datetime format and return naive UTC datetime."""
    if not time_str:
        return None

    parts = time_str.split()
    datetime_part = parts[0]
    tz_part = parts[1] if len(parts) > 1 else None

    try:
        parsed = datetime.strptime(datetime_part, "%Y%m%d%H%M%S")
    except ValueError:
        try:
            parsed = datetime.strptime(datetime_part, "%Y%m%d%H%M")
        except ValueError:
            return None

    # XMLTV offsets are source-local offsets from UTC.
    # Convert to UTC while keeping storage convention as naive datetime.
    if tz_part and re.match(r"^[+-]\d{4}$", tz_part):
        sign = 1 if tz_part[0] == "+" else -1
        offset_hours = int(tz_part[1:3])
        offset_minutes = int(tz_part[3:5])
        offset = timedelta(hours=offset_hours, minutes=offset_minutes)
        if sign > 0:
            parsed -= offset
        else:
            parsed += offset

    return parsed


def normalize_channel_name(name: str) -> str:
    """Normalize a channel name for matching"""
    if not name:
        return ""
    # Lowercase, keep only ASCII alphanumeric and spaces, collapse whitespace
    name = name.lower()
    # Only keep a-z, 0-9, and spaces (removes all Unicode special chars)
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name
