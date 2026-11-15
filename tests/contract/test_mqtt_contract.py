import pytest
from pydantic import ValidationError

try:
    from src.services.ingestion.models import TelemetryEvent
except ImportError:
    from services.ingestion.models import TelemetryEvent


def test_valid_mqtt_telemetry_payload():
    payload = {
        "timestamp": "2026-08-28T14:30:00Z",
        "metric": "temperature",
        "value": 42.5,
        "unit": "celsius",
        "metadata": {
            "firmware": "v2.1.0",
            "location": "site_alpha"
        }
    }
    event = TelemetryEvent.from_payload(payload, device_id="device_104")
    assert event.device_id == "device_104"
    assert event.metric_name == "temperature"
    assert event.value == 42.5
    assert event.unit == "celsius"
    assert event.metadata["location"] == "site_alpha"


def test_mqtt_telemetry_missing_required_fields():
    # Missing metric
    with pytest.raises(ValidationError):
        TelemetryEvent.from_payload({
            "timestamp": "2026-08-28T14:30:00Z",
            "value": 42.5
        }, device_id="device_104")

    # Missing value
    with pytest.raises(ValidationError):
        TelemetryEvent.from_payload({
            "timestamp": "2026-08-28T14:30:00Z",
            "metric": "temperature"
        }, device_id="device_104")

    # Missing timestamp
    with pytest.raises(ValidationError):
        TelemetryEvent.from_payload({
            "metric": "temperature",
            "value": 42.5
        }, device_id="device_104")


def test_mqtt_telemetry_invalid_value_type():
    with pytest.raises(ValidationError):
        TelemetryEvent.from_payload({
            "timestamp": "2026-08-28T14:30:00Z",
            "metric": "temperature",
            "value": "not-a-number"
        }, device_id="device_104")
