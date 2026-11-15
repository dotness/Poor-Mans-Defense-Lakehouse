# Phase 0 Research: Microservice Architecture Alignment

**Feature**: [002-uservice-alignment](specs/002-uservice-alignment/spec.md)  
**Date**: 2026-10-11  

---

## 1. Research Objectives

Investigate and document the concrete technical patterns required to align all Artemis Python services with `github.com/dotness/uservice-template`:
1. Domain package structure (`api/`, `facade/`, `models/`, `operations/`).
2. Temporal Workflow Engine deployment and Python SDK integration.
3. Full JWT / OAuth2 authentication stack and CLI session management.
4. Google ADK 2.0 multi-agent pipelines for intelligence operations.
5. Pluggable Langfuse distributed tracing and observability.
6. Memory and performance impact on the <12 GB platform constraint.

---

## 2. Technical Evaluations & Decisions

### Decision 1: Domain Package Organization (`src/domains/`)

- **Context**: Artemis currently houses flat service directories under `src/services/` (`ingestion`, `analytics`, `graph`, `ai`) and procedural pipelines in `src/pipelines/`.
- **Selected Pattern**: Adopt `uservice-template`'s DDD domain package convention inside `src/domains/`:
  - `src/domains/ingestion/` (MQTT listener, buffer rotation, MinIO Parquet writer)
  - `src/domains/analytics/` (DuckDB SQL execution, Parquet query engine, formatters)
  - `src/domains/graph/` (Memgraph Bolt client, SpiderFoot OSINT importer)
  - `src/domains/ai/` (GenAI RAG service, Redis cache, PostgreSQL audit logger)
  - `src/domains/pipeline/` (Batch orchestration, run tracking)
  - `src/domains/auth/` (User authentication, JWT generation, password hashing)
- **Sub-package Structure per Domain**:
  ```text
  src/domains/<domain>/
  ├── api/             # FastAPI routers (thin, no business logic)
  ├── facade/          # DomainFacade subclasses encapsulating all domain operations
  ├── models/
  │   ├── api/         # Request and Response Pydantic wrappers
  │   ├── contract/    # Canonical Pydantic DTOs (the layer boundary)
  │   └── storage/     # Database models (SQLAlchemy ORM / PyArrow schemas)
  └── operations/      # Temporal workflows and activity steps
  ```
- **Shared Infrastructure**:
  - `src/base/`: `DomainFacade`, `BaseModel`, `BaseOperation`, and permission models.
  - `src/security/`: JWT token decoding, password hashing (bcrypt), and `ContextVar` user context.
  - `src/database/`: Async SQLAlchemy engine, session factories, and base mixins.
  - `src/api.py`: Master FastAPI application aggregating all domain routers.

---

### Decision 2: Temporal Server & Orchestration Integration

- **Context**: In Q2, the user chose the full Temporal Workflow Engine for durable workflows, activities, and step executions.
- **Container Strategy**:
  - Image: `temporalio/auto-setup:1.24` (or latest stable).
  - Database: Reuses the existing PostgreSQL 16 container (`artemis-postgres:5432`) by provisioning a dedicated `temporal` database alongside `artemis`.
  - Memory Footprint: `temporalio/auto-setup` consumes ~200–350 MB RAM, well within the platform's 12 GB budget.
- **Python Client**:
  - Library: `temporalio` (official Temporal Python SDK).
  - Client connection initialized in FastAPI lifespan (`app.state.temporal_client`).
  - Workflows defined with `@workflow.defn` and activities with `@activity.defn`.
  - Facades schedule workflows asynchronously via `client.start_workflow()`.

---

### Decision 3: JWT Security Stack & CLI Token Management

- **Context**: In Q3, the user selected mandatory JWT for both HTTP APIs and CLI commands, with an `artemis login` command caching tokens in `~/.artemis/token`.
- **JWT Architecture**:
  - Library: `pyjwt` and `passlib[bcrypt]`.
  - Cryptographic standard: `HS256` using `JWT_SECRET_KEY` configured in `.env`.
  - Token claims: `sub` (user_id), `username`, `roles`, `scopes`, `exp` (1-day expiration).
  - FastAPI Dependency: `authenticate_user` middleware decodes the Bearer token, validates expiration/signature, and sets the active `UserContext` via Python `contextvars.ContextVar`.
- **CLI Authentication**:
  - `artemis login --username <user> --password <pass>`: authenticates against the auth facade, obtains a JWT, and securely stores it in `~/.artemis/token` with `0600` POSIX permissions.
  - CLI command handlers read `~/.artemis/token`, pass it to the domain facade context, or prompt the user to log in if missing or expired.

---

### Decision 4: Targeted Google ADK 2.0 Agentic Workflows

- **Context**: In Q4, the user decided on targeted ADK agent pipelines for the AI and OSINT Graph domains.
- **Agent Architecture**:
  - Library: `google-adk>=2.0.0b1` + `google-genai`.
  - Implementation:
    - `src/domains/ai/operations/ai_agents.py`: Implements a 3-agent pipeline:
      1. **Planner Agent**: Analyzes the analyst's natural language intent and plans graph traversal queries.
      2. **Guardian Critic Agent**: Evaluates security constraints, prompt injection risks, and ensures output grounding.
      3. **Executor Agent**: Synthesizes the final grounded intelligence briefing via Google AI Studio API.
    - Batch telemetry (`src/domains/ingestion/operations/`) uses deterministic Temporal activities without LLM agent overhead.

---

### Decision 5: Pluggable Langfuse Tracing & Observability

- **Context**: In Q5, the user selected pluggable Langfuse distributed tracing.
- **Implementation**:
  - Libraries: `langfuse`, `openinference-instrumentation-google-adk`, `opentelemetry-sdk`.
  - Lifespan Hook: If `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are present in `.env`, the FastAPI lifespan initializes the OpenTelemetry tracer and instruments `GoogleADKInstrumentor()`.
  - Fallback: If absent, tracing initialization is silently skipped, and telemetry continues via standard logging and PostgreSQL audit tables (`ai_queries`).

---

## 3. Constitution & Resource Gate Validation

| Principle / Constraint | Status | Justification |
| :--- | :--- | :--- |
| **I. Library-First & Modular** | **PASS** | Domains strictly encapsulated with Facades; 0 monolithic coupling. |
| **II. Unified CLI Interface** | **PASS** | `artemis` CLI preserved; new `artemis login` command added. |
| **III. Test-First Rigor** | **PASS** | Contract tests for Pydantic models; integration tests for Facades and Temporal. |
| **IV. Resource Constraint (<12GB)** | **PASS** | Total memory addition: FastAPI (~40 MB) + Temporal Server (~300 MB) = ~340 MB total, leaving >8 GB free. |
