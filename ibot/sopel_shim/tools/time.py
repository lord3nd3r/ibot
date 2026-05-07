"""Sopel-compatible time utilities."""

import re
from datetime import timedelta


# Pattern for parsing time duration strings like "1h30m"
_DURATION_RE = re.compile(
    r'(?:(\d+)w)?'   # weeks
    r'(?:(\d+)d)?'   # days
    r'(?:(\d+)h)?'   # hours
    r'(?:(\d+)m)?'   # minutes
    r'(?:(\d+)s)?',  # seconds
    re.IGNORECASE,
)


def parse_duration(duration_str):
    """Parse a duration string into a timedelta.

    Supported formats: 1w2d3h4m5s, or just seconds as an integer.
    """
    try:
        return timedelta(seconds=int(duration_str))
    except ValueError:
        pass

    match = _DURATION_RE.match(duration_str)
    if not match or not any(match.groups()):
        raise ValueError(f"Invalid duration: {duration_str}")

    weeks = int(match.group(1) or 0)
    days = int(match.group(2) or 0)
    hours = int(match.group(3) or 0)
    minutes = int(match.group(4) or 0)
    seconds = int(match.group(5) or 0)

    return timedelta(
        weeks=weeks,
        days=days,
        hours=hours,
        minutes=minutes,
        seconds=seconds,
    )
