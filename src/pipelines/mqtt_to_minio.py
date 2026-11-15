import os
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any
import psycopg2

try:
    from src.config.settings import settings
    from src.services.ingestion.models import TelemetryEvent
    from src.services.ingestion.minio_writer import MinioParquetWriter
except ImportError:
    from config.settings import settings
    from services.ingestion.models import TelemetryEvent
    from services.ingestion.minio_writer import MinioParquetWriter

logger = logging.getLogger("artemis.pipelines.mqtt_to_minio")


def record_run_in_postgres(events_count: int, status: str, details: Dict[str, Any]):
    try:
        conn = psycopg2.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
            connect_timeout=2,
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pipeline_runs (pipeline_name, status, completed_at, events_processed, details)
                VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s)
                """,
                ("mqtt_to_minio", status, events_count, json.dumps(details)),
            )
            cur.execute(
                """
                UPDATE pipelines
                SET last_status = %s, last_run_at = CURRENT_TIMESTAMP
                WHERE name = 'mqtt_to_minio'
                """,
                (status,),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not record pipeline run in PostgreSQL: {e}")


def run_flush() -> Dict[str, Any]:
    buffer_dir = Path(settings.disk_buffer_dir)
    buffer_file = buffer_dir / "events.jsonl"

    # Recover any previously interrupted processing batches
    for old_proc in buffer_dir.glob("events.processing.*.jsonl"):
        if buffer_file.exists():
            with open(buffer_file, "a", encoding="utf-8") as bf, open(old_proc, "r", encoding="utf-8") as opf:
                bf.write(opf.read())
            old_proc.unlink(missing_ok=True)
        else:
            old_proc.rename(buffer_file)

    if not buffer_file.exists() or buffer_file.stat().st_size == 0:
        logger.info("Buffer empty. No events to flush.")
        return {"status": "SUCCESS", "events_processed": 0, "message": "Buffer was empty"}

    # Rotate file for atomic processing
    timestamp = int(time.time() * 1000)
    processing_file = buffer_dir / f"events.processing.{timestamp}.jsonl"
    buffer_file.rename(processing_file)

    events = []
    failed_lines = 0
    with open(processing_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                events.append(TelemetryEvent.model_validate(data))
            except Exception:
                failed_lines += 1

    if not events:
        processing_file.unlink(missing_ok=True)
        return {"status": "SUCCESS", "events_processed": 0, "message": "No valid events found"}

    # Write to MinIO
    writer = MinioParquetWriter()
    object_key = writer.write_batch(events)

    # Clean up processing file
    processing_file.unlink(missing_ok=True)

    details = {
        "object_key": object_key,
        "failed_lines": failed_lines,
        "bucket": settings.minio_bucket,
    }
    record_run_in_postgres(len(events), "SUCCESS", details)

    result = {
        "status": "SUCCESS",
        "events_processed": len(events),
        "object_key": object_key,
        "details": details,
    }
    logger.info(f"Successfully processed {len(events)} events into {object_key}")
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = run_flush()
    print(json.dumps(res, indent=2))
