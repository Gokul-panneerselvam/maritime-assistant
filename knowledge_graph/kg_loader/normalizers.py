import re
from datetime import datetime, timezone
from typing import Optional

def _get_tz(tz_name: str):
    """Retrieves timezone using zoneinfo, with pytz fallback."""
    tz_clean = (tz_name or "UTC").strip()
    if tz_clean.upper() == "UTC":
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_clean)
    except Exception:
        try:
            import pytz
            return pytz.timezone(tz_clean)
        except Exception:
            return timezone.utc

def convert_local_to_utc(dt_str: Optional[str], tz_name: Optional[str]) -> Optional[str]:
    """
    Converts a local datetime string (e.g., '2026-07-18 12:00') into an ISO 8601 UTC string
    using the provided IANA timezone name (e.g., 'Europe/Amsterdam' -> '2026-07-18T10:00:00Z').
    """
    if not dt_str or not dt_str.strip():
        return None

    dt_str = dt_str.strip()
    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ]

    dt = None
    for fmt in formats:
        try:
            dt = datetime.strptime(dt_str, fmt)
            break
        except ValueError:
            continue

    if dt is None:
        try:
            dt = datetime.fromisoformat(dt_str)
        except ValueError:
            return None

    tz = _get_tz(tz_name or "UTC")

    # If datetime is naive, attach local timezone
    if dt.tzinfo is None:
        try:
            # pytz requires localize()
            if hasattr(tz, "localize"):
                dt = tz.localize(dt)
            else:
                dt = dt.replace(tzinfo=tz)
        except Exception:
            dt = dt.replace(tzinfo=timezone.utc)

    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc_iso(dt_str: Optional[str]) -> Optional[str]:
    """
    Normalizes an existing UTC datetime string (with Z or +00:00) into standardized ISO 'YYYY-MM-DDTHH:MM:SSZ'.
    """
    if not dt_str or not dt_str.strip():
        return None

    s = dt_str.strip()
    iso_clean = s.replace("Z", "+00:00") if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(iso_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                continue
    return None


def compute_duration_hours(start_iso: Optional[str], end_iso: Optional[str]) -> Optional[float]:
    """
    Computes duration in hours between two ISO UTC datetime strings (end - start).
    Returns None if either timestamp is missing or end < start.
    """
    if not start_iso or not end_iso:
        return None

    try:
        start_clean = start_iso.replace("Z", "+00:00")
        end_clean = end_iso.replace("Z", "+00:00")
        dt_start = datetime.fromisoformat(start_clean)
        dt_end = datetime.fromisoformat(end_clean)
        diff_hours = (dt_end - dt_start).total_seconds() / 3600.0
        return round(diff_hours, 2)
    except Exception:
        return None


def slugify(text: Optional[str]) -> str:
    """Creates a URL-safe lowercase slug from a string."""
    if not text:
        return ""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return slug.strip("-")


def normalize_type_id(type_name: Optional[str]) -> str:
    """Normalizes vessel type to uppercase snake case (e.g. 'Container ship' -> 'CONTAINER_SHIP')."""
    if not type_name:
        return "UNKNOWN"
    return re.sub(r"[^a-zA-Z0-9]+", "_", type_name.strip().upper()).strip("_")


def extract_rolled_voyage(status: Optional[str]) -> Optional[str]:
    """
    Extracts targeted voyage ID from status string if specified (e.g. 'Rolled to VG-1107' -> 'VG-1107').
    """
    if not status:
        return None
    match = re.search(r"Rolled to\s+([A-Za-z0-9\-]+)", status, re.IGNORECASE)
    if match:
        target = match.group(1).strip()
        # Verify it resembles a voyage ID like VG-xxxx
        if target.upper() != "NEXT" and target.upper() != "SAILING":
            return target
    return None

