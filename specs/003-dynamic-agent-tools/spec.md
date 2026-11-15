# Feature Specification: Dynamic Multi-Database Agent Tool Loop

**Feature Branch**: `003-dynamic-agent-tools`  
**Created**: 2026-10-11  
**Status**: Draft  
**Input**: User description: "refactor 'artemis ask' to use Dynamic Agent Tool loop , where Agent decides what data to fetch, from which database, to answer the user's query."

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Multi-Database Autonomous Tool Selection (Priority: P1)

An intelligence analyst asks a question whose answer is spread across both historical telemetry metrics and threat intelligence relationships (e.g., "Which sensor reported high temperature anomalies and what malicious IP addresses are associated with it?"). Instead of following a rigid, static retrieval path, the AI Agent dynamically inspects available tools, formulates an analytical query to DuckDB for metric anomalies, inspects the result, formulates a subsequent graph query to Memgraph for linked threat entities, and produces a single cohesive answer grounded in both datasets.

**Why this priority**: Delivers the core capability requested by the user: allowing the agent to autonomously decide what data to fetch, from which database, rather than being constrained to a single pre-selected data source.

**Independent Test**: Can be tested by running `artemis ask` with a cross-cutting question and verifying that both DuckDB and Memgraph queries are generated and executed dynamically to construct the answer.

**Acceptance Scenarios**:

1. **Given** an authenticated analyst user, **When** they submit a query requiring graph data, **Then** the Agent decides to invoke the Graph Query tool, retrieves related entities from Memgraph, and synthesizes the response.
2. **Given** an authenticated analyst user, **When** they submit a query requiring numerical or aggregate telemetry metrics, **Then** the Agent decides to invoke the Analytics Query tool, retrieves aggregated Parquet data via DuckDB, and synthesizes the response.
3. **Given** a cross-cutting query, **When** the Agent receives results from the first tool call, **Then** it can issue a second tool call to another database before generating the final response.

---

### User Story 2 - Agent Tool Definition & Schema Awareness (Priority: P1)

The AI Agent is provided with strongly typed, schema-documented tools that it can call:
- `query_analytics(sql: str)`: Executes analytical queries against DuckDB over MinIO Parquet telemetry partitions.
- `query_graph(cypher: str)`: Executes graph queries against the Memgraph property graph.
- `get_schema_info(target: str)`: Returns table or node/edge label schemas to help the agent construct valid queries without hallucination.

**Why this priority**: The agent must understand database schemas and capabilities to generate syntactically correct and meaningful queries without trial-and-error failures.

**Independent Test**: The agent accurately uses table names (`read_parquet('s3://telemetry/**/*.parquet')`) and node labels (`Entity`, `Incident`, `Indicator`) during autonomous tool calls.

**Acceptance Scenarios**:

1. **Given** an unknown schema context, **When** the Agent needs schema details, **Then** it inspects database schemas using `get_schema_info` or embedded prompt descriptions.
2. **Given** a tool invocation, **When** the tool returns data, **Then** the response is structured and fed back into the agent conversation loop as a tool observation.

---

### User Story 3 - Guardrails & Read-Only Safety Bounds (Priority: P2)

Because the Agent dynamically writes queries, strict guardrails must ensure it cannot alter, corrupt, or exfiltrate unintended data. All tools must enforce read-only execution. Any query containing mutating keywords (e.g., `DELETE`, `DROP`, `INSERT`, `CREATE`, `UPDATE`, `ALTER`, `DETACH DELETE`) must be immediately blocked before execution.

**Why this priority**: Autonomous code/query execution must be bounded to protect system integrity and comply with data governance policies.

**Independent Test**: Test by submitting prompts attempting prompt injection or table truncation; verify the tool layer rejects the mutation and the agent reports a safety refusal.

**Acceptance Scenarios**:

1. **Given** an agent generating a SQL query with `DROP` or `DELETE`, **When** the tool is called, **Then** the tool layer rejects the execution with a permission error.
2. **Given** an agent generating a Cypher query with `CREATE` or `SET`, **When** the tool is called, **Then** the tool layer rejects the mutation.
3. **Given** a loop exceeding the maximum iteration limit (e.g., 5 turns), **When** no final answer is reached, **Then** the agent terminates safely with a partial summary.

---

### User Story 4 - Transparent Execution Trace & Auditability (Priority: P2)

Analysts and automated systems consuming `artemis ask` need visibility into what decisions the agent made: which tools were called, which queries were issued, execution times, and whether results were retrieved from cache.

**Why this priority**: Auditability and explainability are critical in sovereign intelligence and mission-critical operations.

**Independent Test**: Run `artemis ask "..." --json` and verify the output contains a `tool_calls` array detailing every tool invocation, query executed, and database response summary.

**Acceptance Scenarios**:

1. **Given** a query executed with dynamic tools, **When** requesting `--json` format, **Then** the output payload includes `tool_calls` containing tool names, arguments, and execution duration.
2. **Given** standard text output, **When** the response is displayed, **Then** a concise summary of sources consulted (e.g., "Consulted: Memgraph, DuckDB") is printed.

---

### Edge Cases

- **Agent Tool Execution Timeout**: What happens if a DuckDB or Memgraph query takes too long? The tool enforces a strict 5-second per-call timeout; if exceeded, the agent receives a timeout error observation and can retry or answer with available data.
- **Empty Query Results**: What happens if a database returns zero records? The agent receives an empty dataset observation and can try alternative search parameters or notify the user that no records were found.
- **Offline / Mock Mode**: How does the system behave when `GOOGLE_AI_STUDIO_API_KEY` is not present? The system executes a deterministic tool-loop simulation so local development and automated CI testing work without network dependencies.
- **Cyclic Tool Calling**: What happens if the agent enters an infinite loop calling the same tool? A hard limit of 5 tool turns is enforced per question.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST implement a dynamic agent tool loop using Google AI Studio / Gemini Function Calling where the model autonomously selects and invokes tools.
- **FR-002**: The agent MUST have access to a Graph Query tool capable of executing read-only Cypher queries against Memgraph.
- **FR-003**: The agent MUST have access to an Analytics Query tool capable of executing read-only SQL queries against DuckDB over MinIO Parquet files.
- **FR-004**: The system MUST validate every agent-generated query against a read-only safety filter, rejecting any mutating statement.
- **FR-005**: The agent loop MUST support multi-turn reasoning (calling a tool, observing output, and optionally calling another tool) up to a configurable maximum of 5 iterations.
- **FR-006**: The system MUST return an execution trace listing all tools called, queries executed, and latency breakdown.
- **FR-007**: The system MUST maintain backward compatibility with `artemis ask` CLI arguments and the `AIFacade.ask` contract schema.
- **FR-008**: The system MUST provide an offline deterministic fallback when no Google API key is supplied, enabling local test suite execution.

---

### Key Entities

- **AgentTool**: A callable capability exposed to the LLM, containing a name, description, JSON Schema parameter definitions, and an asynchronous execution handler.
- **ToolCallStep**: A single step within an agent loop record, tracking the tool called, arguments provided, execution result or error, and duration in milliseconds.
- **AgentExecutionTrace**: The complete history of an agent interaction, including the initial prompt, intermediate tool calls, grounding context, and final synthesized response.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The agent autonomously executes queries across at least two distinct database backends (DuckDB and Memgraph) for cross-domain queries.
- **SC-002**: 100% of mutating queries (`DROP`, `DELETE`, `CREATE`, `UPDATE`) are blocked by the tool safety layer before execution.
- **SC-003**: The complete multi-turn tool loop finishes in under 10 seconds for standard live queries, and under 50 milliseconds in cached/offline test mode.
- **SC-004**: All 35+ existing contract and integration tests pass without regression, augmented by new tests verifying dynamic tool dispatching.

---

## Assumptions

- Users have configured read access to DuckDB telemetry parquet files in MinIO and the Memgraph bolt endpoint.
- Google AI Studio API provides Gemini models supporting Function Calling (`gemini-2.5-flash`, `gemini-1.5-flash`).
- When offline or during unit tests, mock tool execution deterministically returns representative subgraphs and metric aggregates without making external API calls.
