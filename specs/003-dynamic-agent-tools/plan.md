# Implementation Plan: Dynamic Multi-Database Agent Tool Loop

**Branch**: `003-dynamic-agent-tools` | **Date**: 2026-10-11 | **Spec**: [specs/003-dynamic-agent-tools/spec.md](specs/003-dynamic-agent-tools/spec.md)

**Input**: Feature specification from `specs/003-dynamic-agent-tools/spec.md`

---

## Summary

Refactor the `artemis ask` interaction and `AIFacade` implementation from static retrieval-augmented generation to an autonomous **Dynamic Agent Tool Loop (ReAct / Function Calling)** using Google AI Studio / Gemini. The agent is provided with secure, schema-aware read-only tools: `query_analytics` (DuckDB over MinIO Parquet telemetry) and `query_graph` (Memgraph property graph). The LLM autonomously determines which database to query, formulates queries, executes intermediate hops, and returns a grounded response accompanied by a transparent tool execution audit trace.

---

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: `google-genai` (official Google AI Studio SDK), `pydantic` v2, `duckdb`, `pymgclient` / `neo4j` (Memgraph bolt driver), `redis`, `click`  
**Storage**:
- MinIO (S3-compatible Parquet telemetry partitions)
- Memgraph (in-memory C++ property graph)
- PostgreSQL (audit logging)
- Redis (semantic query cache & rate limiting)
**Testing**: `pytest`, `pytest-asyncio`, `pytest-timeout` with strict 60-second timeouts  
**Target Platform**: Linux server / VM (Dockerized services + native Python CLI)  
**Project Type**: Multi-domain microservice architecture with unified CLI (`artemis`)  
**Performance Goals**:
- Live agent tool loop completed in < 10 seconds.
- Offline deterministic simulator completed in < 50 milliseconds.
- Analytical queries completed in < 5 seconds.
**Constraints**:
- Single-VM idle memory budget < 12 GB RAM.
- Strict read-only query enforcement (zero database mutations).
- Maximum 5 iterations per agent loop to prevent runaways.
- Seamless offline/mock test execution when no Google API key is configured.
**Scale/Scope**: Unified across `src/domains/ai/` and `src/domains/analytics/` / `src/domains/graph/`.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Requirement | Plan Compliance Status |
| :--- | :--- | :--- |
| **I. Library-First & Modular** | Modular domains with strict Pydantic contracts | **PASS**: Tools wrap Domain Facades (`AnalyticsFacade`, `GraphFacade`) without coupling. |
| **II. Unified CLI Interface** | Expose functionality via `artemis` CLI with `--json` | **PASS**: `artemis ask` updated with `--json` audit trail of tool calls. |
| **III. Test-First Rigor** | Contract & integration tests across boundaries | **PASS**: Contract tests for tool schemas + integration tests for multi-database queries. |
| **IV. Resource Constraint & Zero-JVM** | Under 12 GB RAM, CPU-only, no JVM daemons | **PASS**: Uses existing C++ DuckDB and Memgraph engines; LLM reasoning executed via Google AI Studio API. |

---

## Project Structure

### Documentation (this feature)

```text
specs/003-dynamic-agent-tools/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan
├── research.md          # Phase 0: Function calling & guardrail research
├── data-model.md        # Phase 1: ToolCallRecord & ExecutionTrace schemas
├── quickstart.md        # Phase 1: Developer verification steps
├── contracts/           # Phase 1: Agent tools contracts
│   └── agent_tools.py
├── checklists/          # Requirements validation checklist
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
src/
├── domains/
│   ├── ai/
│   │   ├── api/
│   │   │   └── router.py                 # REST endpoint returning tool_calls
│   │   ├── facade/
│   │   │   └── ai.py                     # AIFacade delegating to DynamicAgentLoop
│   │   ├── models/
│   │   │   └── contract/
│   │   │       └── ai.py                 # AIQueryResponseContract extended with tool_calls
│   │   └── operations/
│   │       ├── ai_agents.py              # ADK Planner, GuardianCritic, Executor
│   │       ├── tools.py                  # Agent database tools (analytics, graph, schema)
│   │       ├── guardrails.py             # Read-only SQL/Cypher safety validator
│   │       └── dynamic_loop.py           # Multi-turn Gemini Function Calling & offline simulator
│   ├── analytics/
│   │   └── facade/analytics.py           # Queried by query_analytics tool
│   └── graph/
│       └── facade/graph.py               # Queried by query_graph tool
├── services/
│   └── ai/
│       └── genai_service.py              # Extended with function calling & tool dispatching
└── cli/
    └── commands/
        └── ask.py                        # Prints formatted sources & tool audit breakdown
```

**Structure Decision**: Fully encapsulated within existing `src/domains/ai/` domain and clean facade bindings to `analytics` and `graph` domains.

---

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
| :--- | :--- | :--- |
| *None* | N/A | Fully adheres to Constitution and Domain Facade architecture. |
