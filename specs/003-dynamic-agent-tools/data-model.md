# Phase 1 Data Model: Dynamic Multi-Database Agent Tool Loop

**Feature**: [003-dynamic-agent-tools](specs/003-dynamic-agent-tools/spec.md)  
**Date**: 2026-10-11  

---

## 1. Domain Entities & Schemas

### `ToolCallRecord`
Represents a single tool invocation executed during an agent reasoning loop.

| Field | Type | Description |
| :--- | :--- | :--- |
| `call_id` | `str` | Unique invocation identifier (e.g. `call-4f2a1b`). |
| `tool_name` | `str` | Name of tool called (`query_analytics`, `query_graph`, `get_schema_info`). |
| `arguments` | `Dict[str, Any]` | Parameters supplied by the agent (`sql_query`, `cypher_query`, etc.). |
| `result` | `Optional[Any]` | Output data returned by the tool (structured rows/nodes). |
| `error` | `Optional[str]` | Error message if query failed or was blocked by guardrails. |
| `duration_ms` | `int` | Execution latency of the tool call in milliseconds. |

---

### `AgentExecutionTrace`
Encapsulates the complete trajectory of the agent reasoning loop for a single query.

| Field | Type | Description |
| :--- | :--- | :--- |
| `query_id` | `str` | Unique query tracking UUID. |
| `prompt` | `str` | Original analyst question. |
| `tool_calls` | `List[ToolCallRecord]` | Sequential list of all tools executed during the session. |
| `total_iterations` | `int` | Number of model turns taken (1 to 5). |
| `databases_consulted` | `List[str]` | Set of storage backends accessed (`["duckdb", "memgraph"]`). |
| `final_response` | `str` | Grounded markdown response text. |
| `model_used` | `str` | Model identifier (e.g., `gemini-2.5-flash` or `offline-simulator`). |
| `total_duration_ms` | `int` | Total elapsed time from request to final response. |

---

### `ToolDefinitionContract`
Metadata definition for tools exposed to the LLM.

| Field | Type | Description |
| :--- | :--- | :--- |
| `name` | `str` | Identifier matching function name. |
| `description` | `str` | Human/LLM-readable guidance on when and how to call the tool. |
| `parameters_schema` | `Dict[str, Any]` | JSON Schema describing arguments. |
| `read_only` | `bool` | True (guaranteed non-mutating). |

---

## 2. Updated AI Contract Models

In `src/domains/ai/models/contract/ai.py`, the existing `AIQueryResponseContract` is extended with transparent tool audit fields while maintaining backward compatibility:

```python
class ToolCallRecord(BaseModel):
    call_id: str
    tool_name: str
    arguments: Dict[str, Any]
    duration_ms: int
    error: Optional[str] = None
    summary: Optional[str] = None

class AIQueryResponseContract(BaseModel):
    query_id: str
    response: str
    model_used: str
    cached: bool
    duration_ms: int
    context: List[Dict[str, Any]] = []
    # New Dynamic Agent Tool fields:
    tool_calls: List[ToolCallRecord] = []
    databases_consulted: List[str] = []
```
