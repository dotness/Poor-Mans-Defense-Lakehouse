import re
from typing import Optional

_TTL_PATTERN = re.compile(r"^\s*([+-]?\d+)\s*(s|sec|secs|m|min|mins|h|hr|hrs|d|day|days|w|wk|wks|mo|month|months|y|yr|yrs)\s*$", re.IGNORECASE)
_ISO_DURATION_PATTERN = re.compile(r"^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$", re.IGNORECASE)

_UNIT_TO_SECONDS = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "w": 604800,
    "wk": 604800,
    "wks": 604800,
    "mo": 2592000,      # 30 days
    "month": 2592000,
    "months": 2592000,
    "y": 31536000,      # 365 days
    "yr": 31536000,
    "yrs": 31536000,
}

_INFINITE_TOKENS = {"never", "infinite", "inf", "permanent", "forever", "none"}


def parse_ttl_expression(
    expr: str,
    allow_zero: bool = False,
    allow_infinite: bool = True,
    min_seconds: int = 1,
) -> Optional[int]:
    """
    Parses a human-readable TTL or grace period expression into seconds.
    Returns None for 'never' / 'infinite' (when allow_infinite=True).
    Raises ValueError on malformed, negative, or out-of-bounds values.
    """
    if expr is None or not isinstance(expr, str) or not expr.strip():
        raise ValueError("TTL expression must be a non-empty string.")

    cleaned = expr.strip().lower()
    if cleaned in _INFINITE_TOKENS:
        if not allow_infinite:
            raise ValueError(f"Infinite duration ('{expr}') is not allowed for this field.")
        return None

    # Check standard shorthand e.g. 30d, 24h, 15m, 0h
    match = _TTL_PATTERN.match(cleaned)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        seconds = amount * _UNIT_TO_SECONDS[unit]
    else:
        # Check ISO-8601 duration e.g. P30D, PT24H
        iso_match = _ISO_DURATION_PATTERN.match(expr.strip())
        if iso_match and any(iso_match.groups()):
            years = int(iso_match.group(1) or 0)
            months = int(iso_match.group(2) or 0)
            weeks = int(iso_match.group(3) or 0)
            days = int(iso_match.group(4) or 0)
            hours = int(iso_match.group(5) or 0)
            minutes = int(iso_match.group(6) or 0)
            secs = int(iso_match.group(7) or 0)
            seconds = (
                years * 31536000
                + months * 2592000
                + weeks * 604800
                + days * 86400
                + hours * 3600
                + minutes * 60
                + secs
            )
        else:
            raise ValueError(
                f"Invalid TTL expression '{expr}'. Expected format like '30d', '24h', '15m', '7d', or 'never'."
            )

    if seconds < 0:
        raise ValueError(f"TTL duration cannot be negative ('{expr}').")
    if seconds == 0:
        if allow_zero:
            return 0
        raise ValueError(f"TTL duration must be greater than zero ('{expr}').")
    if seconds < min_seconds:
        raise ValueError(
            f"TTL duration '{expr}' ({seconds}s) is below the minimum allowed duration of {min_seconds}s."
        )

    return seconds


def normalize_ttl_expression(
    expr: str,
    allow_zero: bool = False,
    allow_infinite: bool = True,
) -> str:
    """Validates and normalizes a TTL expression string."""
    seconds = parse_ttl_expression(expr, allow_zero=allow_zero, allow_infinite=allow_infinite)
    if seconds is None:
        return "never"
    if seconds == 0:
        return "0h"
    return expr.strip().lower()


def format_ttl_seconds(seconds: Optional[int]) -> str:
    """Formats a duration in seconds back into a concise human-readable token."""
    if seconds is None:
        return "never"
    if seconds == 0:
        return "0h"
    if seconds % 31536000 == 0:
        return f"{seconds // 31536000}y"
    if seconds % 2592000 == 0 and (seconds // 2592000) not in (1,):
        return f"{seconds // 2592000}mo"
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"
