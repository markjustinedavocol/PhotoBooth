from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from django.utils import timezone

UTC = ZoneInfo("UTC")


def zone_for(tz_name):
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return UTC


def local_time(profile, when=None):
    """`when` (default: now) as seen on the clock in the profile's timezone."""
    when = when or timezone.now()
    return when.astimezone(zone_for(profile.timezone))


def clock(dt: datetime) -> str:
    """'9:14 PM' — built by hand because %-I isn't portable to Windows."""
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def pretty_date(dt: datetime) -> str:
    return f"{dt:%b} {dt.day}, {dt.year}"


def timezone_choices():
    zones = sorted(z for z in available_timezones() if "/" in z and not z.startswith("Etc/"))
    return [("UTC", "UTC")] + [(z, z.replace("_", " ")) for z in zones]


def is_valid_timezone(tz_name):
    return tz_name == "UTC" or tz_name in available_timezones()
