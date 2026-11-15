import logging
import time
import asyncio
from typing import List, Optional, Dict, Any
from src.base.facade import DomainFacade
from src.config.settings import settings
from src.domains.ingestion.models.contract.telemetry import TelemetryEventContract, BatchFlushResultContract
from src.services.ingestion.mqtt_listener import MqttIngestionListener
from src.services.ingestion.models import TelemetryEvent
from src.domains.ingestion.operations.flush import FlushBufferOperation, FlushBufferWorkflow
from src.base.temporal import get_temporal_client

logger = logging.getLogger(__name__)


class IngestionFacade(DomainFacade):
    """Facade for high-frequency telemetry buffering and batch compaction."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._listener: Optional[MqttIngestionListener] = None
        self.operation = FlushBufferOperation()

    def ingest_event(self, contract: TelemetryEventContract) -> TelemetryEventContract:
        """Appends a validated telemetry event contract directly to the local disk buffer."""
        if self._listener is None:
            self._listener = MqttIngestionListener()

        event = TelemetryEvent(
            event_id=contract.event_id,
            timestamp=contract.timestamp,
            device_id=contract.device_id,
            metric_name=contract.metric_name,
            value=contract.value,
            unit=contract.unit,
            metadata=contract.metadata,
        )
        self._listener.write_to_buffer(event)
        return contract

    async def flush_buffer_to_minio(self) -> BatchFlushResultContract:
        """Flushes the local disk buffer into MinIO Parquet via workflow operations."""
        temporal_client = await get_temporal_client()
        if temporal_client:
            try:
                result_dict = await asyncio.wait_for(
                    temporal_client.execute_workflow(
                        FlushBufferWorkflow.run,
                        settings.disk_buffer_dir,
                        id=f"flush-workflow-{int(time.time()*1000)}",
                        task_queue="artemis-queue",
                    ),
                    timeout=3.0,
                )
            except Exception as e:
                logger.warning(f"Temporal execution error or worker timeout ({e}), executing via direct operation.")
                result_dict = await self.operation.run()
        else:
            result_dict = await self.operation.run()

        return BatchFlushResultContract(
            status=result_dict.get("status", "SUCCESS"),
            events_processed=result_dict.get("events_processed", 0),
            object_key=result_dict.get("object_key"),
            details=result_dict.get("details", {}),
        )
