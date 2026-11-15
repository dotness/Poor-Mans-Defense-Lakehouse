import json
import io
from pathlib import Path
from datetime import datetime, timezone
import pyarrow.parquet as pq

try:
    from src.services.ingestion.models import TelemetryEvent
    from src.services.ingestion.mqtt_listener import MqttIngestionListener
    from src.services.ingestion.minio_writer import PARQUET_SCHEMA
except ImportError:
    from services.ingestion.models import TelemetryEvent
    from services.ingestion.mqtt_listener import MqttIngestionListener
    from services.ingestion.minio_writer import PARQUET_SCHEMA
import pyarrow as pa


def test_mqtt_buffering_and_parquet_serialization(tmp_path):
    # 1. Test disk buffer writing
    listener = MqttIngestionListener(buffer_dir=str(tmp_path))
    
    events = [
        TelemetryEvent(
            timestamp=datetime.now(timezone.utc),
            device_id=f"sensor_{i}",
            metric_name="temperature",
            value=25.0 + i,
            unit="celsius",
            metadata={"test": True, "index": i}
        )
        for i in range(50)
    ]

    for event in events:
        listener.write_to_buffer(event)

    buffer_file = tmp_path / "events.jsonl"
    assert buffer_file.exists()

    # Verify lines in buffer
    with open(buffer_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    assert len(lines) == 50

    # 2. Test Parquet conversion of buffered events
    loaded_events = [TelemetryEvent.model_validate(json.loads(line)) for line in lines]
    
    record_data = {
        "event_id": [e.event_id for e in loaded_events],
        "timestamp": [e.timestamp for e in loaded_events],
        "device_id": [e.device_id for e in loaded_events],
        "metric_name": [e.metric_name for e in loaded_events],
        "value": [e.value for e in loaded_events],
        "unit": [e.unit for e in loaded_events],
        "metadata": [json.dumps(e.metadata) for e in loaded_events],
    }
    table = pa.Table.from_pydict(record_data, schema=PARQUET_SCHEMA)
    sink = io.BytesIO()
    pq.write_table(table, sink, compression="SNAPPY")
    sink.seek(0)

    # Read back and assert
    read_table = pq.read_table(sink)
    assert read_table.num_rows == 50
    assert "metric_name" in read_table.column_names
    assert read_table["value"][0].as_py() == 25.0
    assert read_table["value"][49].as_py() == 74.0
