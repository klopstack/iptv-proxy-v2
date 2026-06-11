"""Regex patterns for PPV channel name extraction."""

import re

SPORT_PATTERN = r"\b(Field\s+Hockey|Ice\s+Hockey|NCAA\s+Football|College\s+Football|NFL|NBA|MLB|MILB|MiLB|NHL|Soccer|Football|Basketball|Volleyball|Tennis|Golf|Cricket|Rugby|Lacrosse|Curling|Skating|Weightlifting|Boxing|MMA|UFC|Wrestling|Judo|Karate|Taekwondo|Gymnastics|Swimming|Track\s+and\s+Field|Cross\s+Country|Rowing|Sailing|Cycling|Triathlon|Badminton|Squash|Table\s+Tennis|Handball|Netball|Australian\s+Rules|American\s+Football|Australian\s+Football)\b"

TOURNAMENT_STRUCTURE_PATTERN = r"\b(Round|Quarter|Semi|Final|Group|Stage|Match|Game|Heat|Leg|Lap)\s+(?:\d+[a-z]?|[A-Z])\s*-\s*(?:Final|Game|Match|Heat|Leg|Lap)\b"

COMPETITOR_PATTERN = (
    r"([#\w\s&\'\-,]+?)\s+(?:vs\.?)\s+([#\w\s&\'\-,\.:]+?)(?=\s*[|@()\[\]]|-\s+[A-Z]|-\s+\d|\s+\d|\s*$)"
    r"|([#\w\s&\'-]+?)\s+(?:at\.?|versus|@)\s+([#\w\s&\'-\-\.]+?)(?=\s*[|@()\[\]]|-\s+[A-Z]|-\s+\d|\s+\d|\s*$)"
    r"|([A-Z][A-Za-z\s&\'\-]+?)\s+-\s+([A-Z][A-Za-z\s&\'\-]+)(?=\s*[|@()\[\]]|\s*$)"
    r"|([#\w\s&\'\-,]+?)\s+x\s+([#\w\s&\'\-,\.:]+?)(?=\s*[|@()\[\]]|-\s+[A-Z]|-\s+\d|\s+\d|\s*$|start:)"
)

TRAILING_TIME_PATTERN = r"\s+\d{1,2}:\d{2}\s*(?:am|pm)?$"

NO_EVENT_PATTERN = r"NO EVENT STREAMING"

DATE_PATTERN = (
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{1,2}):(\d{2})(?:\s+(AM|PM))?"
)

ISO_DATE_PATTERN = r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})"

ISO_PIPE_DATE_PATTERN = r"(\d{4})-(\d{1,2})-(\d{1,2})\s*\|\s*(\d{1,2}):(\d{2})"

ISO_PAREN_DATETIME_PATTERN = r"\((\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\)"

DDMM_DATE_PATTERN = r"(?:(\d{4})\s+)?(\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2})(?:\s*(am|pm))?"

DAY_MONTH_TIME_PATTERN = (
    r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+" r"(\d{1,2}):(\d{2})(?:\s*(AM|PM))?"
)

WEEKDAY_NAMES_PATTERN = (
    r"(?:Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|Thu(?:rs(?:day)?)?|" r"Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)"
)
WEEKDAY_PATTERN = rf"\b({WEEKDAY_NAMES_PATTERN})\b"

_WEEKDAY_TO_ABBREV = {
    "mon": "mon",
    "monday": "mon",
    "tue": "tue",
    "tues": "tue",
    "tuesday": "tue",
    "wed": "wed",
    "wednesday": "wed",
    "thu": "thu",
    "thur": "thu",
    "thurs": "thu",
    "thursday": "thu",
    "fri": "fri",
    "friday": "fri",
    "sat": "sat",
    "saturday": "sat",
    "sun": "sun",
    "sunday": "sun",
}


def normalize_weekday(name: str) -> str | None:
    """Map weekday abbreviations and full names to three-letter lowercase."""
    return _WEEKDAY_TO_ABBREV.get(name.lower())


TIME_ONLY_PATTERN = r"\b(\d{1,2}):(\d{2})(?:\s*(am|pm))?\b"

STOP_TIME_PATTERN = r"stop:(\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)"

PIPE_DATE_PATTERN = (
    rf"\|\s*{WEEKDAY_NAMES_PATTERN}\s+(\d{{1,2}})\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}):(\d{2})"
)

COUNTRY_PREFIX_RE = re.compile(r"^[A-Z]{2,3}[:|]\s*", re.IGNORECASE)
PROVIDER_SLOT_RE = re.compile(
    r"^(?:DAZN|ESPN\s*(?:PLUS?|\+?)|MAX|TNT|FOX|SKY|BT\s*SPORT|beIN|ELEVEN)\s*(?:PPV\s*)?\d+\s*[-\u2013]\s*",
    re.IGNORECASE,
)
BARE_PPV_SLOT_RE = re.compile(r"^PPV\s*\d+\s*[-\u2013]\s*", re.IGNORECASE)

MONTH_ABBR_TO_NUM = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
