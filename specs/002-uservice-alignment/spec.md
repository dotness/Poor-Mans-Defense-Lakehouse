# Feature Specification: Microservice Architecture Alignment

**Feature Branch**: `[002-uservice-alignment]`

**Created**: 2026-10-11

**Status**: Specified

**Input**: User description: "make each of python services in the project to be aligned with github.com/dotness/uservice-template"

## Clarifications

### Session 2026-10-11
- Q: How should the Python package structure be arranged to adopt uservice-template's domain layout? → A: Option A: Refactor into `src/domains/<domain>/` with `api/`, `facade/`, `models/`, and `operations/` sub-packages while keeping `src/` as the Python root.
- Q: How should the Temporal Server container be provisioned and backed in Docker Compose? → A: Option A: Connect `temporalio/auto-setup` container to the existing PostgreSQL instance (`artemis-postgres`) using a dedicated `temporal` database.
- Q: How should authentication be handled for CLI commands versus HTTP API requests? → A: Option B: Mandatory JWT for both CLI and HTTP, with an `artemis login` command caching a token in `~/.artemis/token`.
- Q: How should Google ADK 2.0 Agentic Workflows be applied across domain operations? → A: Option A: Targeted ADK agents for AI & OSINT graph domains; keep telemetry batch ingestion deterministic.
- Q: How should observability and distributed tracing from uservice-template be integrated? → A: Option A: Pluggable Langfuse tracing for AI/ADK operations when env vars are present; fallback to structured logging.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Domain-Driven Facade & Contract Boundary Enforcement (Priority: P1)

As a software engineer and platform architect, I want every Python domain in Artemis to have strict layer boundaries with coarse-grained Domain Facades and Pydantic Contract models, so that business logic is isolated, decoupled from transport layers, and easily testable.

**Why this priority**: Strict layer separation (`Facade` -> `Contract` -> `Storage`) is the core architectural principle of `uservice-template`. Without it, components remain tightly coupled and inconsistent.

**Independent Test**: Can be tested by instantiating any domain facade (e.g. `IngestionFacade`, `AnalyticsFacade`, `GraphFacade`, `AIFacade`) directly in tests with contract DTOs, verifying that business operations succeed without importing database models or transport layers.

**Acceptance Scenarios**:

1. **Given** an analytics query request, **When** invoked via `AnalyticsFacade.execute_query(contract)`, **Then** the facade validates the input contract, executes the query, and returns a validated `QueryResultContract` without exposing internal database or storage cursors.
2. **Given** cross-domain interaction between AI correlation and the Knowledge Graph, **When** `AIFacade` requests related entities, **Then** it communicates strictly through `GraphFacade` using contract models, never executing raw Cypher queries directly against Memgraph.

---

### User Story 2 - Unified FastAPI Endpoints & Transport Decoupling (Priority: P1)

As an API consumer and frontend/agent developer, I want each domain to expose standardized FastAPI HTTP routes while maintaining full compatibility with the existing `artemis` CLI, so that services can be consumed via REST APIs and CLI commands identically.

**Why this priority**: `uservice-template` mandates thin FastAPI routers under each domain's `api/` package. The CLI and REST endpoints must share identical business facades.

**Independent Test**: Can be tested by submitting HTTP requests to domain endpoints (e.g., `/api/v1/analytics/query`, `/api/v1/ai/ask`, `/api/v1/ingestion/telemetry`) and verifying that responses match the outputs produced by `artemis query` and `artemis ask`.

**Acceptance Scenarios**:

1. **Given** a running Artemis FastAPI application, **When** a client posts a query to `/api/v1/analytics/query`, **Then** the thin router delegates to `AnalyticsFacade` and returns a standard response envelope.
2. **Given** existing CLI commands (`artemis status`, `artemis ask`, `artemis query`, `artemis pipeline run`), **When** executed from the terminal, **Then** they invoke the same domain facades with zero behavioral regression.

---

### User Story 3 - Structured Operations & Lifecycle Steps (Priority: P2)

As a data engineer and operations developer, I want multi-step and batch processes (such as telemetry buffer flushing, Parquet compaction, and OSINT graph ingestion) to be structured as domain `operations/` with reusable activity steps, so that complex workflows have clean lifecycle hooks, logging, and error boundaries.

**Why this priority**: `uservice-template` organizes state-mutating and asynchronous processes under `operations/` with explicit step classes, replacing monolithic procedural scripts.

**Independent Test**: Can be tested by triggering the `FlushBufferOperation` and `OsintImportOperation` independently and verifying step-by-step execution logging and rollback handling.

**Acceptance Scenarios**:

1. **Given** events waiting in the disk buffer, **When** `FlushBufferOperation.execute()` is called, **Then** it executes discrete steps (`RotateBufferStep`, `ConvertToParquetStep`, `UploadToMinioStep`, `RecordAuditStep`) with comprehensive logging.
2. **Given** an invalid data format in one step, **When** an operation step fails, **Then** error details are captured in the operation response and persisted in the audit log without crashing the worker.

---

### Edge Cases

- **CLI Compatibility**: How does the platform handle CLI invocations when routers and facades are refactored? The CLI command handlers must import Domain Facades directly, ensuring no breaking changes to CLI UX.
- **Resource Budget during Multi-Domain Execution**: Does introducing FastAPI routers increase the memory footprint beyond the 12 GB budget? Thin routers sharing a single FastAPI process keep memory consumption under 50 MB.
- **Missing or Partial Service Dependencies**: How do facades handle service outages (e.g. MinIO unreachable, Memgraph unavailable)? Facades must handle connection errors gracefully, returning structured error contracts rather than unhandled tracebacks.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST organize Python code into domain packages (`ingestion`, `analytics`, `graph`, `ai`, `pipeline`) each containing `facade/`, `models/` (`contract/`, `storage/`, `api/`), `api/`, and `operations/`.
- **FR-002**: System MUST encapsulate all business logic within coarse-grained `DomainFacade` classes that serve as the sole entry point for domain capabilities.
- **FR-003**: System MUST define Pydantic `contract` models as the canonical data shape for data exchange between API routers, facades, and CLI handlers.
- **FR-004**: System MUST maintain strict layer separation where API routers never access storage models directly and facades convert storage records to contract DTOs before returning.
- **FR-005**: Cross-domain communication MUST occur exclusively through facades (e.g., AI domain calling `GraphFacade`, never querying Memgraph directly).
- **FR-006**: System MUST organize asynchronous and multi-step tasks under domain `operations/` using modular step classes.
- **FR-007**: System MUST deploy domain routers under a unified FastAPI application gateway exposed behind Traefik reverse proxy.
- **FR-008**: System MUST preserve all existing `artemis` CLI commands (`status`, `query`, `ask`, `pipeline run`) by routing their execution through the new Domain Facades.
- **FR-009**: Domain architecture packaging boundary MUST be structured as modular domains in the Artemis codebase (`src/domains/`) sharing a unified FastAPI application gateway and Docker stack.
- **FR-010**: Operation orchestration mechanism MUST use the Temporal Workflow Engine with a `temporalio/auto-setup` container connecting to the existing PostgreSQL service (`artemis-postgres`) with a dedicated `temporal` database schema for durable workflows, activities, and step executions.
- **FR-011**: Authentication and security middleware MUST enforce the full JWT / OAuth2 Security Stack with Bearer tokens, permission scopes, and role-based access control adapted from `uservice-template` across both HTTP API endpoints and CLI commands. The CLI MUST provide an `artemis login` command that authenticates user credentials and caches the resulting JWT token in `~/.artemis/token` for subsequent CLI command execution.
- **FR-012**: System MUST integrate Google ADK 2.0 multi-agent pipelines (Planner -> Guardian Critic -> Executor) specifically for complex reasoning tasks in the AI and OSINT Graph domains, while maintaining deterministic Temporal activities for high-throughput batch operations (telemetry ingestion and analytical queries).
- **FR-013**: System MUST support pluggable Langfuse observability and distributed tracing for AI and ADK agent workflows when `LANGFUSE_PUBLIC_KEY` and related environment variables are configured, falling back gracefully to structured JSON logging and PostgreSQL audit records when disabled.

### Key Entities

- **Domain Facade**: Coarse-grained class (e.g., `AnalyticsFacade`, `IngestionFacade`) encapsulating domain business logic, CRUD, and cross-domain interactions.
- **Contract Model (DTO)**: Pydantic model representing the single source of truth for domain data exchange across layer boundaries.
- **Storage Model**: Data definitions bound to persistence engines (e.g., SQLAlchemy ORM tables for PostgreSQL, PyArrow schemas for MinIO Parquet).
- **API Model**: Request and response wrapper models used by FastAPI routers for HTTP serialization.
- **Operation / Step**: Structured class managing multi-step workflows, activity execution, and compensation logic.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of domain business logic across ingestion, analytics, graph, AI, and pipelines is accessible via Domain Facades with zero direct internal helper coupling.
- **SC-002**: 100% of data crossing domain boundaries conforms to validated Pydantic Contract models.
- **SC-003**: All existing CLI commands (`artemis status`, `artemis query`, `artemis ask`, `artemis pipeline run`) execute successfully with zero functional regressions.
- **SC-004**: 100% of automated tests pass with explicit timeouts under 60 seconds (`pytest -v --timeout=60`).
- **SC-005**: Total idle memory consumption of the refactored services and HTTP application remains under 100 MB, preserving the platform's <12 GB total constraint.

## Assumptions

- Python 3.12+ and Pydantic v2 are used across all domain models.
- The monorepo structure in `src/` can be mapped to domain packages while preserving existing Docker container orchestrations.
- Traefik continues to act as the primary TLS termination and reverse proxy router for both HTTP APIs and web dashboards.
- The existing database and storage engines (PostgreSQL, MinIO, Memgraph, Mosquitto, Redis) remain the underlying data layer.
