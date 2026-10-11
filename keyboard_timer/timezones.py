"""Offline time zone support.

Uses the standard-library ``zoneinfo`` (Python 3.9+).  On Windows the IANA
database is provided by the tiny pure-Python ``tzdata`` package listed in
requirements.txt, so everything keeps working with no internet connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone as _utc

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - very old Python
    ZoneInfo = None  # type: ignore[assignment]

LOCAL = "LOCAL"

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


@dataclass(frozen=True)
class Zone:
    """A selectable location: friendly name plus IANA key (or LOCAL)."""

    name: str
    key: str


# Curated list of common places.  "LOCAL" always means the PC's own clock.
COMMON_ZONES = [
    Zone("Local", LOCAL),
    Zone("UTC", "UTC"),
    Zone("New York", "America/New_York"),
    Zone("Toronto", "America/Toronto"),
    Zone("Chicago", "America/Chicago"),
    Zone("Mexico City", "America/Mexico_City"),
    Zone("Denver", "America/Denver"),
    Zone("Los Angeles", "America/Los_Angeles"),
    Zone("Anchorage", "America/Anchorage"),
    Zone("Honolulu", "Pacific/Honolulu"),
    Zone("Bogota", "America/Bogota"),
    Zone("Lima", "America/Lima"),
    Zone("Santiago", "America/Santiago"),
    Zone("Buenos Aires", "America/Argentina/Buenos_Aires"),
    Zone("Sao Paulo", "America/Sao_Paulo"),
    Zone("Reykjavik", "Atlantic/Reykjavik"),
    Zone("London", "Europe/London"),
    Zone("Dublin", "Europe/Dublin"),
    Zone("Lisbon", "Europe/Lisbon"),
    Zone("Paris", "Europe/Paris"),
    Zone("Brussels", "Europe/Brussels"),
    Zone("Amsterdam", "Europe/Amsterdam"),
    Zone("Madrid", "Europe/Madrid"),
    Zone("Barcelona", "Europe/Madrid"),
    Zone("Berlin", "Europe/Berlin"),
    Zone("Zurich", "Europe/Zurich"),
    Zone("Rome", "Europe/Rome"),
    Zone("Prague", "Europe/Prague"),
    Zone("Vienna", "Europe/Vienna"),
    Zone("Warsaw", "Europe/Warsaw"),
    Zone("Stockholm", "Europe/Stockholm"),
    Zone("Oslo", "Europe/Oslo"),
    Zone("Copenhagen", "Europe/Copenhagen"),
    Zone("Helsinki", "Europe/Helsinki"),
    Zone("Athens", "Europe/Athens"),
    Zone("Bucharest", "Europe/Bucharest"),
    Zone("Kyiv", "Europe/Kyiv"),
    Zone("Istanbul", "Europe/Istanbul"),
    Zone("Moscow", "Europe/Moscow"),
    Zone("Cairo", "Africa/Cairo"),
    Zone("Lagos", "Africa/Lagos"),
    Zone("Nairobi", "Africa/Nairobi"),
    Zone("Johannesburg", "Africa/Johannesburg"),
    Zone("Casablanca", "Africa/Casablanca"),
    Zone("Dubai", "Asia/Dubai"),
    Zone("Karachi", "Asia/Karachi"),
    Zone("Delhi", "Asia/Kolkata"),
    Zone("Mumbai", "Asia/Kolkata"),
    Zone("Bangkok", "Asia/Bangkok"),
    Zone("Jakarta", "Asia/Jakarta"),
    Zone("Singapore", "Asia/Singapore"),
    Zone("Hong Kong", "Asia/Hong_Kong"),
    Zone("Shanghai", "Asia/Shanghai"),
    Zone("Taipei", "Asia/Taipei"),
    Zone("Manila", "Asia/Manila"),
    Zone("Seoul", "Asia/Seoul"),
    Zone("Tokyo", "Asia/Tokyo"),
    Zone("Perth", "Australia/Perth"),
    Zone("Adelaide", "Australia/Adelaide"),
    Zone("Brisbane", "Australia/Brisbane"),
    Zone("Melbourne", "Australia/Melbourne"),
    Zone("Sydney", "Australia/Sydney"),
    Zone("Auckland", "Pacific/Auckland"),
]

_BY_KEY = {z.key: z for z in COMMON_ZONES}


def is_valid_zone(key: str) -> bool:
    """True if ``key`` can be resolved by the bundled tz database."""
    if key == LOCAL:
        return True
    if ZoneInfo is None:
        return False
    try:
        ZoneInfo(key)
        return True
    except Exception:
        return False


def zone_object(key: str):
    """Return a ZoneInfo for ``key`` or None (LOCAL / unknown)."""
    if key == LOCAL or ZoneInfo is None:
        return None
    try:
        return ZoneInfo(key)
    except Exception:
        return None


def now_for(key: str) -> datetime:
    """Current date/time in the given zone (falls back to PC local time)."""
    info = zone_object(key)
    return datetime.now(info) if info is not None else datetime.now()


def offset_label(key: str) -> str:
    """Human readable UTC offset for a zone at this moment, e.g. 'UTC-04:00'."""
    info = zone_object(key)
    dt = datetime.now(info) if info is not None else datetime.now().astimezone()
    delta = dt.utcoffset() or _utc.utc.utcoffset(dt)  # type: ignore[arg-type]
    total = int(delta.total_seconds()) if delta else 0
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return "UTC{}{:02d}:{:02d}".format(sign, total // 3600, (total % 3600) // 60)


def name_for(key: str) -> str:
    """Friendly display name for a zone key.

    The local PC clock deliberately has no label - the real time is shown
    on its own (name/title labels are hidden by the caller for LOCAL).
    """
    zone = _BY_KEY.get(key)
    if zone is not None:
        return "" if zone.key == LOCAL else zone.name
    if key == LOCAL:
        return ""
    return key.replace("_", " ").replace("/", " · ")


def search(query: str) -> list:
    """Filter ``COMMON_ZONES`` by name/key; accept any valid IANA key typed in."""
    q = query.strip().lower()
    if not q:
        return list(COMMON_ZONES)
    hits = [z for z in COMMON_ZONES if q in z.name.lower() or q in z.key.lower()]
    typed = query.strip()
    if typed.upper() != LOCAL and typed not in {z.key for z in hits} and is_valid_zone(typed):
        hits.append(Zone(typed, typed))
    return hits


def format_date(dt: datetime) -> str:
    """'Sunday, October 11, 2026' without leading zeros or locale surprises."""
    return "{}, {} {}, {}".format(
        WEEKDAYS[dt.weekday()], MONTHS[dt.month - 1], dt.day, dt.year
    )
