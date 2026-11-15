import os
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import timedelta
from temporalio import activity, workflow

from src.base.operations import BaseStep, BaseOperation
from src.config.settings import settings
from src.services.ingestion.models import TelemetryEvent
from src.services.ingestion.minio_writer import MinioParquetWriter
from src.pipelines.mqtt_to_minio import record_run_in_postgres

logger = logging.getLogger("artemis.domains.ingestion.operations.flush")


# ============================================================================
# Activity Steps
# ============================================================================

class RotateBufferStep(BaseStep):
    """Rotates local disk buffer into an isolated processing file."""

    @activity.defn(name="rotate_buffer_activity")
    async def execute_activity(self, buffer_dir_str: str) -> Optional[str]:
        return await self.execute({"buffer_dir": buffer_dir_str})

    async def execute(self, context: Dict[str, Any]) -> Optional[str]:
        buffer_dir = Path(context.get("buffer_dir", settings.disk_buffer_dir))
        buffer_file = buffer_dir / "events.jsonl"

        # Recover previously interrupted processing batches
        for old_proc in buffer_dir.glob("events.processing.*.jsonl"):
            if buffer_file.exists():
                with open(buffer_file, "a", encoding="utf-8") as bf, open(old_proc, "r", encoding="utf-8") as opf:
                    bf.write(opf.read())
                old_proc.unlink(missing_ok=True)
            else:
                old_proc.rename(buffer_file)

        if not buffer_file.exists() or buffer_file.stat().st_size == 0:
            logger.info("Buffer empty. No events to flush.")
            return None

        timestamp = int(time.time() * 1000)
        processing_file = buffer_dir / f"events.processing.{timestamp}.jsonl"
        buffer_file.rename(processing_file)
        return str(processing_file)


class ConvertToParquetStep(BaseStep):
    """Parses JSONL processing file into validated TelemetryEvents."""

    @activity.defn(name="convert_to_parquet_activity")
    async def execute_activity(self, processing_file_path: str) -> Dict[str, Any]:
        return await self.execute({"processing_file": processing_file_path})

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        processing_file_path = context.get("processing_file")
        if not processing_file_path or not Path(processing_file_path).exists():
            return {"events": [], "failed_lines": 0}

        events_data = []
        failed_lines = 0
        with open(processing_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    events_data.append(data)
                except Exception:
                    failed_lines += 1

        return {
            "events_data": events_data,
            "failed_lines": failed_lines,
        }


class UploadToMinioStep(BaseStep):
    """Compacts validated events into Parquet and uploads to MinIO bucket."""

    @activity.defn(name="upload_to_minio_activity")
    async def execute_activity(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self.execute(payload)

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        events_data = context.get("events_data", [])
        processing_file_path = context.get("processing_file")
        failed_lines = context.get("failed_lines", 0)

        if not events_data:
            if processing_file_path:
                Path(processing_file_path).unlink(missing_ok=True)
            return {"status": "SUCCESS", "events_processed": 0, "object_key": None}

        events = [TelemetryEvent.model_validate(d) for d in events_data]
        writer = MinioParquetWriter()
        object_key = writer.write_batch(events)

        if processing_file_path:
            Path(processing_file_path).unlink(missing_ok=True)

        details = {
            "object_key": object_key,
            "failed_lines": failed_lines,
            "bucket": settings.minio_bucket,
        }
        record_run_in_postgres(len(events), "SUCCESS", details)

        return {
            "status": "SUCCESS",
            "events_processed": len(events),
            "object_key": object_key,
            "details": details,
        }


# ============================================================================
# Temporal Workflow Definition
# ============================================================================

@workflow.defn
class FlushBufferWorkflow:
    """Temporal workflow executing the durable buffer flush sequence."""

    @workflow.run
    async def run(self, buffer_dir: str) -> Dict[str, Any]:
        # Step 1: Rotate Buffer
        processing_file = await workflow.execute_activity(
            "rotate_buffer_activity",
            buffer_dir,
            start_to_close_timeout=timedelta(seconds=10),
        )

        if not processing_file:
            return {"status": "SUCCESS", "events_processed": 0, "message": "Buffer was empty"}

        # Step 2: Parse and Convert
        convert_res = await workflow.execute_activity(
            "convert_to_parquet_activity",
            processing_file,
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Step 3: Upload to MinIO
        upload_payload = {
            "events_data": convert_res["events_data"],
            "processing_file": processing_file,
            "failed_lines": convert_res["failed_lines"],
        }
        upload_res = await workflow.execute_activity(
            "upload_to_minio_activity",
            upload_payload,
            start_to_close_timeout=timedelta(minutes=2),
        )

        return upload_res


# ============================================================================
# Standalone Operation Runner (Used directly or via Facade)
# ============================================================================

class FlushBufferOperation(BaseOperation):
    """Coordinates the flush workflow steps with fallback to direct execution."""

    def __init__(self):
        super().__init__("FlushBufferOperation")
        self.rotate_step = RotateBufferStep()
        self.convert_step = ConvertToParquetStep()
        self.upload_step = UploadToMinioStep()
        self.add_step(self.rotate_step)
        self.add_step(self.convert_step)
        self.add_step(self.upload_step)

    async def run(self, **kwargs) -> Dict[str, Any]:
        buffer_dir = kwargs.get("buffer_dir", settings.disk_buffer_dir)
        proc_file = await self.rotate_step.execute({"buffer_dir": buffer_dir})
        if not proc_file:
            return {"status": "SUCCESS", "events_processed": 0, "message": "Buffer was empty"}

        convert_res = await self.convert_step.execute({"processing_file": proc_file})
        upload_res = await self.upload_step.execute({
            "events_data": convert_res["events_data"],
            "processing_file": proc_file,
            "failed_lines": convert_res["failed_lines"],
        })
        return upload_res
