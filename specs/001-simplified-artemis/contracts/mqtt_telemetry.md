# MQTT Telemetry Ingestion Contract

This contract defines the expected format of telemetry payloads sent by edge devices to the Mosquitto MQTT broker.

## Topic Structure

Devices MUST publish telemetry data to the following topic pattern:
`telemetry/<device_group>/<device_id>/<sensor_type>`

Example: `telemetry/alpha_site/device_104/temperature`

## Payload Format (JSON)

The payload MUST be a valid JSON object.

### Schema

```json
{
  "timestamp": "2026-08-28T14:30:00Z",
  "metric": "temperature",
  "value": 42.5,
  "unit": "celsius",
  "metadata": {
    "firmware": "v2.1.0",
    "location": "site_alpha"
  }
}
```

### Field Definitions

- `timestamp` (String, Required): ISO-8601 formatted UTC timestamp.
- `metric` (String, Required): The name of the metric being reported.
- `value` (Number/String, Required): The measured value.
- `unit` (String, Optional): The unit of measurement.
- `metadata` (Object, Optional): Additional key-value pairs providing context for the reading.

## Quality of Service (QoS)

- High-frequency edge devices SHOULD use **QoS 0** (At most once) to prioritize throughput over guaranteed delivery, unless strict ACID guarantees are explicitly required for the specific metric.
