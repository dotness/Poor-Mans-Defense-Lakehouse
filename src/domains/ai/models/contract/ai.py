from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AIQueryRequestContract(BaseModel):
    prompt: str
    user_id: str = "analyst"


class ToolCallRecord(BaseModel):
    call_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0
    error: Optional[str] = None
    summary: Optional[str] = None


class AIQueryResponseContract(BaseModel):
    query_id: str
    response: str
    model_used: str
    cached: bool
    duration_ms: int
    context: Any = Field(default_factory=list)
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    databases_consulted: List[str] = Field(default_factory=list)
