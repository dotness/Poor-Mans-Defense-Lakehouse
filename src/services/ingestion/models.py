import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator


class TelemetryEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime
    device_id: str
    metric_name: str
    value: float
    unit: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("metric_name")
    @classmethod
    def validate_metric_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("metric_name cannot be empty")
        return v.strip()

    @classmethod
    def from_payload(cls, payload: Dict[str, Any], device_id: str = "unknown") -> "TelemetryEvent":
        data = dict(payload)
        if "metric" in data and "metric_name" not in data:
            data["metric_name"] = data.pop("metric")
        data["device_id"] = device_id
        return cls.model_validate(data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "device_id": self.device_id,
            "metric_name": self.metric_name,
            "value": self.value,
            "unit": self.unit,
            "metadata": self.metadata,
        }
