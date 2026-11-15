import pytest
from src.domains.discovery.operations.pattern_profiler import PatternProfiler


def test_uuid_detection():
    profiler = PatternProfiler()
    samples = [
        "123e4567-e89b-12d3-a456-426614174000",
        "c9a646d3-9c61-4cd7-bf15-97eac2f9638d",
        "d8b375b4-9c04-4c55-b77a-245b9db0b31b",
        "not-a-uuid",
    ]
    # 3 out of 4 = 75% -> below 80%
    assert profiler.detect_pattern(samples) is None

    # 4 out of 5 = 80% -> matches
    samples.append("550e8400-e29b-41d4-a716-446655440000")
    assert profiler.detect_pattern(samples) == "UUID"


def test_hash_detection():
    profiler = PatternProfiler()
    sha256_samples = [
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8",
        "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        "8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4",
    ]
    assert profiler.detect_pattern(sha256_samples) == "HASH"


def test_iso_timestamp_detection():
    profiler = PatternProfiler()
    iso_samples = [
        "2026-10-19T20:00:00Z",
        "2026-05-12T14:30:00+02:00",
        "2025-01-01 10:00:00",
        "2026-12-31T23:59:59.123Z",
    ]
    assert profiler.detect_pattern(iso_samples) == "ISO_TIMESTAMP"


def test_unix_timestamp_detection():
    profiler = PatternProfiler()
    unix_samples = [
        "1729368000",
        "1729368001",
        "1729368002",
        "1729368003",
    ]
    assert profiler.detect_pattern(unix_samples) == "UNIX_TIMESTAMP"


def test_ip_address_detection():
    profiler = PatternProfiler()
    ip_samples = [
        "192.168.1.1",
        "10.0.0.254",
        "172.16.0.1",
        "8.8.8.8",
    ]
    assert profiler.detect_pattern(ip_samples) == "IP_ADDRESS"

    ipv6_samples = [
        "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
        "fe80::1ff:fe23:4567:890a",
        "::1",
        "2001:db8::1",
    ]
    assert profiler.detect_pattern(ipv6_samples) == "IP_ADDRESS"


def test_url_detection():
    profiler = PatternProfiler()
    url_samples = [
        "https://example.com/api/v1",
        "http://telemetry.local:8080/data",
        "ftp://files.example.org/export.csv",
        "https://sub.domain.org/path?q=1#frag",
    ]
    assert profiler.detect_pattern(url_samples) == "URL"


def test_email_detection():
    profiler = PatternProfiler()
    email_samples = [
        "alice@example.com",
        "bob.smith@telemetry.health.gov",
        "user_123@hospital.org",
        "doctor.clark+tag@med.univ.edu",
    ]
    assert profiler.detect_pattern(email_samples) == "EMAIL"


def test_phone_detection():
    profiler = PatternProfiler()
    phone_samples = [
        "+1-800-555-0199",
        "+33 1 42 68 55 00",
        "+44 20 7946 0991",
        "+14155552671",
    ]
    assert profiler.detect_pattern(phone_samples) == "PHONE"


def test_coordinates_detection():
    profiler = PatternProfiler()
    coord_samples = [
        "48.8566, 2.3522",
        "-33.8688, 151.2093",
        "37.7749, -122.4194",
        "51.5074, -0.1278",
    ]
    assert profiler.detect_pattern(coord_samples) == "COORDINATES"


def test_null_and_empty_filtering():
    profiler = PatternProfiler()
    samples = [
        None,
        "",
        "   ",
        "alice@example.com",
        "bob@example.com",
        "carol@example.com",
        "dave@example.com",
    ]
    # Non-null non-empty count is 4. 4/4 = 100% email.
    assert profiler.detect_pattern(samples) == "EMAIL"


def test_entity_candidate_classification():
    profiler = PatternProfiler()
    assert profiler.is_entity_candidate(pattern="UUID", cardinality_ratio=0.9) is True
    assert profiler.is_entity_candidate(pattern="EMAIL", cardinality_ratio=0.8) is True
    assert profiler.is_entity_candidate(pattern=None, cardinality_ratio=0.95) is True
    assert profiler.is_entity_candidate(pattern="ISO_TIMESTAMP", cardinality_ratio=0.95) is False
