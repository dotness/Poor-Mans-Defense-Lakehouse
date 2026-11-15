import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class TelemetryEventContract(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    device_id: str
    metric_name: str
    value: float
    unit: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BatchFlushResultContract(BaseModel):
    status: str
    events_processed: int
    object_key: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
