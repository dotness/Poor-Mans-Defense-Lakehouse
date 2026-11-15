import os
import json
import logging
from pathlib import Path
from typing import Optional
import paho.mqtt.client as mqtt

try:
    from src.config.settings import settings
    from src.services.ingestion.models import TelemetryEvent
except ImportError:
    from config.settings import settings
    from services.ingestion.models import TelemetryEvent

logger = logging.getLogger("artemis.ingestion.mqtt")


class MqttIngestionListener:
    def __init__(
        self,
        broker_host: Optional[str] = None,
        broker_port: Optional[int] = None,
        topic_prefix: Optional[str] = None,
        buffer_dir: Optional[str] = None,
    ):
        self.broker_host = broker_host or settings.mqtt_host
        self.broker_port = broker_port or settings.mqtt_port
        self.topic_prefix = topic_prefix or settings.mqtt_topic_prefix
        self.buffer_dir = Path(buffer_dir or settings.disk_buffer_dir)
        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        self.buffer_file = self.buffer_dir / "events.jsonl"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._is_running = False

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        topic = f"{self.topic_prefix}/#"
        client.subscribe(topic)
        logger.info(f"Connected to MQTT broker at {self.broker_host}:{self.broker_port}. Subscribed to {topic}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            topic_parts = msg.topic.split("/")
            device_id = topic_parts[2] if len(topic_parts) >= 3 else "unknown_device"
            
            event = TelemetryEvent.from_payload(payload, device_id=device_id)
            self.write_to_buffer(event)
        except Exception as e:
            logger.error(f"Error processing MQTT message on topic {msg.topic}: {e}")

    def write_to_buffer(self, event: TelemetryEvent):
        # Thread-safe atomic line write to disk buffer
        line = json.dumps(event.to_dict()) + "\n"
        with open(self.buffer_file, "a", encoding="utf-8") as f:
            f.write(line)

    def start(self, blocking: bool = True):
        self._is_running = True
        self.client.connect(self.broker_host, self.broker_port, keepalive=60)
        if blocking:
            self.client.loop_forever()
        else:
            self.client.loop_start()

    def stop(self):
        if self._is_running:
            self.client.loop_stop()
            self.client.disconnect()
            self._is_running = False
            logger.info("MQTT listener stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    listener = MqttIngestionListener()
    print("Starting MQTT ingestion listener. Press Ctrl+C to exit.")
    try:
        listener.start(blocking=True)
    except KeyboardInterrupt:
        listener.stop()
