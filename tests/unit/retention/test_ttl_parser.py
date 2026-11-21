import pytest
from src.domains.retention.operations.ttl_parser import (
    parse_ttl_expression,
    normalize_ttl_expression,
    format_ttl_seconds,
)


def test_parse_valid_shorthand_durations():
    assert parse_ttl_expression("30s") == 30
    assert parse_ttl_expression("15m") == 900
    assert parse_ttl_expression("24h") == 86400
    assert parse_ttl_expression("7d") == 604800
    assert parse_ttl_expression("30d") == 2592000
    assert parse_ttl_expression("2w") == 1209600
    assert parse_ttl_expression("3mo") == 7776000
    assert parse_ttl_expression("1y") == 31536000


def test_parse_iso_durations():
    assert parse_ttl_expression("P30D") == 2592000
    assert parse_ttl_expression("PT24H") == 86400
    assert parse_ttl_expression("PT15M") == 900


def test_parse_infinite_tokens():
    assert parse_ttl_expression("never") is None
    assert parse_ttl_expression("INFINITE") is None
    assert parse_ttl_expression("permanent") is None
    assert normalize_ttl_expression("NEVER") == "never"

    with pytest.raises(ValueError, match="Infinite duration"):
        parse_ttl_expression("never", allow_infinite=False)


def test_parse_zero_grace_period():
    assert parse_ttl_expression("0h", allow_zero=True) == 0
    assert parse_ttl_expression("0s", allow_zero=True) == 0
    assert normalize_ttl_expression("0h", allow_zero=True) == "0h"

    with pytest.raises(ValueError, match="greater than zero"):
        parse_ttl_expression("0h", allow_zero=False)
    with pytest.raises(ValueError, match="greater than zero"):
        parse_ttl_expression("0d", allow_zero=False)


def test_parse_negative_and_invalid_rejected():
    with pytest.raises(ValueError, match="cannot be negative"):
        parse_ttl_expression("-5d")
    with pytest.raises(ValueError, match="cannot be negative"):
        parse_ttl_expression("-1h", allow_zero=True)
    with pytest.raises(ValueError, match="Invalid TTL expression"):
        parse_ttl_expression("abc")
    with pytest.raises(ValueError, match="Invalid TTL expression"):
        parse_ttl_expression("30lightyears")
    with pytest.raises(ValueError, match="non-empty"):
        parse_ttl_expression("")


def test_format_ttl_seconds():
    assert format_ttl_seconds(None) == "never"
    assert format_ttl_seconds(0) == "0h"
    assert format_ttl_seconds(3600) == "1h"
    assert format_ttl_seconds(86400) == "1d"
    assert format_ttl_seconds(2592000) == "30d"
    assert format_ttl_seconds(31536000) == "1y"
    assert format_ttl_seconds(900) == "15m"
    assert format_ttl_seconds(45) == "45s"
