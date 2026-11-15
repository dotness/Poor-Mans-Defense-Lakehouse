# Phase 0 Research: Dynamic Multi-Database Agent Tool Loop

**Feature**: [003-dynamic-agent-tools](specs/003-dynamic-agent-tools/spec.md)  
**Date**: 2026-10-11  

---

## 1. Google GenAI Function Calling Architecture

### Context & Findings
The Artemis platform uses the official `google-genai` SDK (`from google import genai`, `from google.genai import types`).

When invoking Gemini (`gemini-2.5-flash`), dynamic tool calling is enabled by declaring callable tool definitions or Python functions within `types.GenerateContentConfig(tools=[...])`.

```python
# Function Calling Pattern with google-genai
from google.genai import types

def query_graph(cypher_query: str) -> str:
    """Execute read-only Cypher query against Memgraph knowledge graph."""
    ...

def query_analytics(sql_query: str) -> str:
    """Execute read-only DuckDB SQL query over MinIO telemetry Parquet files."""
    ...

config = types.GenerateContentConfig(
    tools=[query_graph, query_analytics],
    temperature=0.1,
    system_instruction="You are Artemis AI. Autonomously choose the right database tools to answer analyst questions."
)
```

### Multi-Turn Agent Loop Execution Flow
1. **Turn 1 (Prompt)**: The analyst prompt is sent to `client.models.generate_content`.
2. **Tool Evaluation**: If the model determines database lookups are needed, it responds with one or more `function_call` objects in `candidate.content.parts`.
3. **Execution & Validation**: The agent's `ToolExecutor` validates that the query is strictly read-only, runs it against the target database (Memgraph or DuckDB), and formats the output.
4. **Observation Injection**: The tool results are formatted into `types.Part.from_function_response(name=func_name, response={"result": data})` and appended to the chat contents.
5. **Turn 2+ (Synthesis or Follow-Up)**: Gemini evaluates the tool response. It may emit another `function_call` (e.g. querying Memgraph with an IP address found in DuckDB telemetry) or formulate the final grounded answer.
6. **Termination**: The loop breaks when:
   - Gemini returns a text answer (`part.text`).
   - The loop reaches `MAX_TURNS` (default: 5).
   - A tool error or safety rejection occurs.

---

## 2. Read-Only Query Guardrails

### Risk Analysis
Because the LLM generates ad-hoc SQL and Cypher queries, any prompt injection or hallucination could potentially mutate database state or exhaust system resources.

### AST / Keyword Validation Rules

1. **SQL Guardrail (DuckDB)**:
   - Queries must begin with `SELECT`, `DESCRIBE`, `EXPLAIN`, or `SHOW`.
   - Disallowed keywords (regex-checked on normalized tokens):
     `DROP`, `DELETE`, `INSERT`, `UPDATE`, `ALTER`, `TRUNCATE`, `CREATE`, `ATTACH`, `DETACH`, `COPY`, `INSTALL`, `LOAD`.
   - Mandatory timeout: 5.0 seconds per execution.

2. **Cypher Guardrail (Memgraph)**:
   - Queries must be read-only read traversals.
   - Disallowed clauses:
     `CREATE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `MERGE`, `DROP`, `INDEX`, `CONSTRAINT`.
   - Mandatory timeout: 5.0 seconds per execution.

---

## 3. Database Tool Interfaces & Schemas

### Tool 1: `query_analytics`
- **Purpose**: Aggregation, anomaly detection, statistical summaries, and time-series telemetry.
- **Backend**: Embedded DuckDB querying `read_parquet('s3://telemetry/**/*.parquet')` with MinIO S3 credentials.
- **Parameters**: `sql_query: str`
- **Return**: JSON-serialized rows (up to 50 rows max to conserve context window).

### Tool 2: `query_graph`
- **Purpose**: Entity resolution, OSINT threat intelligence, relationship paths, and indicators.
- **Backend**: Memgraph property graph client (`bolt://localhost:7687`).
- **Parameters**: `cypher_query: str`
- **Return**: JSON-serialized nodes, relationships, and attributes.

### Tool 3: `get_schema_info`
- **Purpose**: Provides table schema and graph ontology to prevent hallucinated column or label names.
- **Parameters**: `target: str` ("analytics" or "graph")
- **Return**: Column definitions (telemetry: `event_id`, `timestamp`, `device_id`, `metric_name`, `value`, `unit`, `metadata`) or graph node/edge labels (`Entity`, `Incident`, `Indicator`, `ASSOCIATED_WITH`, `TRIGGERED_BY`).

---

## 4. Offline & Test Resilience Strategy

### Problem Statement
In CI/CD environments or developer workstations without `GOOGLE_AI_STUDIO_API_KEY`, tests must run without network access, third-party tokens, or cost.

### Solution: Deterministic Autonomous Simulation
When `api_key` is a placeholder or `mock_mode=True`:
1. The `DynamicAgentLoop` analyzes prompt keywords and simulated intent.
2. It generates realistic tool calls:
   - Telemetry keywords ("cpu", "temperature", "metric", "count") -> generates a `query_analytics` call to DuckDB.
   - Threat keywords ("malicious", "anomaly", "c2", "ip", "beaconing") -> generates a `query_graph` call to Memgraph.
3. It executes the tools against local test fixtures/databases.
4. It synthesizes a structured grounded response combining the outputs, returning an authentic `AgentExecutionTrace` with `tool_calls` populated.

This guarantees:
- 100% test coverage without external credentials.
- Strict compliance with Constitution Principle III (Test-First & Integration Rigor).
- Sub-50ms execution in test suites.
