"""Data contracts for Dynamic Multi-Database Agent Tool loop."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolCallRecordContract(BaseModel):
    """Execution record of a single tool invocation made by the LLM."""
    call_id: str = Field(..., description="Unique tool call invocation ID")
    tool_name: str = Field(..., description="Name of the invoked tool")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments supplied by the LLM")
    duration_ms: int = Field(0, description="Execution duration in milliseconds")
    error: Optional[str] = Field(None, description="Error message if tool execution failed")
    summary: Optional[str] = Field(None, description="Concise summary of the data returned by the tool")


class AgentExecutionTraceContract(BaseModel):
    """Complete trace of an autonomous agent session."""
    query_id: str
    prompt: str
    tool_calls: List[ToolCallRecordContract] = Field(default_factory=list)
    total_iterations: int = 1
    databases_consulted: List[str] = Field(default_factory=list)
    final_response: str
    model_used: str
    total_duration_ms: int
