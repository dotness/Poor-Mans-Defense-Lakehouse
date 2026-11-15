#!/usr/bin/env python3
"""Telemetry ingestion load generator tool for Artemis platform."""

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: paho-mqtt package is required. Install via pip or run within active venv.", file=sys.stderr)
    sys.exit(1)


METRICS = [
    ("temperature", "celsius", 20.0, 85.0),
    ("cpu_load", "percent", 5.0, 99.0),
    ("battery_pct", "percent", 10.0, 100.0),
    ("vibration_hz", "hz", 10.0, 500.0),
]


def run_simulator(total_events: int = 10000, rate_per_sec: int = 1000, host: str = "localhost", port: int = 1883):
    print("\n--- Artemis Ingestion Simulator ---")
    print(f"Target: {host}:{port}")
    print(f"Plan: {total_events} events at {rate_per_sec} events/sec\n")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        client.connect(host, port, keepalive=60)
        client.loop_start()
    except Exception as e:
        raise ConnectionError(
            f"Could not connect to MQTT broker at {host}:{port} ({e}). "
            "Ensure the broker is running before launching load generation."
        ) from e

    start_time = time.time()
    published = 0

    batch_size = min(100, rate_per_sec)
    sleep_interval = batch_size / rate_per_sec if rate_per_sec > 0 else 0.01

    while published < total_events:
        for _ in range(batch_size):
            if published >= total_events:
                break
            device_num = random.randint(100, 150)
            metric_name, unit, low, high = random.choice(METRICS)
            value = round(random.uniform(low, high), 2)

            topic = f"telemetry/alpha_site/device_{device_num}/{metric_name}"
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metric": metric_name,
                "value": value,
                "unit": unit,
                "metadata": {
                    "firmware": "v2.1.0",
                    "location": "site_alpha",
                    "sequence": published,
                },
            }
            client.publish(topic, json.dumps(payload), qos=0)
            published += 1

        time.sleep(sleep_interval)

    duration = time.time() - start_time
    client.loop_stop()
    client.disconnect()

    actual_rate = published / duration if duration > 0 else published
    print(f"Completed publishing {published} events in {duration:.2f}s ({actual_rate:.1f} events/sec).")


def main():
    parser = argparse.ArgumentParser(
        description="Artemis Telemetry Ingestion Load Generator Tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--total-events", type=int, default=10000, help="Total number of telemetry events to generate")
    parser.add_argument("--rate-per-sec", type=int, default=1000, help="Target ingestion rate (events per second)")
    parser.add_argument("--host", type=str, default="localhost", help="MQTT broker hostname or IP")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")

    args = parser.parse_args()

    try:
        run_simulator(
            total_events=args.total_events,
            rate_per_sec=args.rate_per_sec,
            host=args.host,
            port=args.port,
        )
    except ConnectionError as e:
        print(f"Connection error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
