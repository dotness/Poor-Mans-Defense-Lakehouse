from fastapi import APIRouter
from src.domains.ingestion.facade.ingestion import IngestionFacade
from src.domains.ingestion.models.contract.telemetry import (
    TelemetryEventContract,
    BatchFlushResultContract,
)

router = APIRouter(prefix="/api/v1/ingestion", tags=["Ingestion"])


@router.post("/event", response_model=TelemetryEventContract)
async def ingest_event(event: TelemetryEventContract):
    """Buffers a high-frequency telemetry event."""
    facade = IngestionFacade()
    return facade.ingest_event(event)


@router.post("/flush", response_model=BatchFlushResultContract)
async def flush_buffer():
    """Flushes local disk buffer into MinIO Parquet."""
    facade = IngestionFacade()
    return await facade.flush_buffer_to_minio()
