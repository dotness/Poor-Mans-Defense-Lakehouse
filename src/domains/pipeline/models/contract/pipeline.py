from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class PipelineRunRequestContract(BaseModel):
    pipeline_name: str


class PipelineRunResponseContract(BaseModel):
    status: str
    pipeline_name: str
    events_processed: int = 0
    object_key: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
