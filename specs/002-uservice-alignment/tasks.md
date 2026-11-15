# Tasks: Microservice Architecture Alignment

**Feature**: [002-uservice-alignment](specs/002-uservice-alignment/spec.md)  
**Input**: [plan.md](specs/002-uservice-alignment/plan.md), [data-model.md](specs/002-uservice-alignment/data-model.md), [contracts/openapi.json](specs/002-uservice-alignment/contracts/openapi.json), [quickstart.md](specs/002-uservice-alignment/quickstart.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, dependency management, and container infrastructure setup.

- [X] T001 [P] Update dependencies in `pyproject.toml` with `fastapi`, `uvicorn`, `temporalio`, `pyjwt`, `passlib[bcrypt]`, `google-adk`, `langfuse`, and `opentelemetry-sdk`.
- [X] T002 [P] Update `docker-compose.yml` to add `temporal` container using `temporalio/auto-setup` connected to `artemis-postgres` with `temporal` database.
- [X] T003 [P] Update `src/config/settings.py` with JWT secret keys, Temporal host/port, and optional Langfuse tracing credentials.
- [X] T004 [P] Create domain directory scaffolding under `src/domains/` (`auth`, `ingestion`, `analytics`, `graph`, `ai`, `pipeline`) with `api/`, `facade/`, `models/`, and `operations/`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core architectural infrastructure that MUST be complete before any user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 [P] Implement `DomainFacade` base class in `src/base/facade.py` providing session management and user context.
- [X] T006 [P] Implement `BaseOperation` and `BaseStep` abstract base classes in `src/base/operations.py`.
- [X] T007 [P] Implement shared async SQLAlchemy engine and base mixins in `src/database/engine.py` and `src/database/base.py`.
- [X] T008 [P] Implement JWT encode/decode, signature verification, and password hashing (`bcrypt`) in `src/security/jwt.py`.
- [X] T009 [P] Implement `authenticate_user` FastAPI dependency and `ContextVar` user context propagation in `src/security/middleware.py`.
- [X] T010 [P] Implement master FastAPI application with lifespan (database initialization, Temporal client, pluggable Langfuse) in `src/api.py`.

**Checkpoint**: Foundation ready - domain facades and user story implementations can begin.

---

## Phase 3: User Story 1 - Domain-Driven Facade & Contract Boundary Enforcement (Priority: P1) 🎯 MVP

**Goal**: Every Python domain in Artemis has strict layer boundaries with coarse-grained Domain Facades and Pydantic Contract models, isolating business logic and guaranteeing data contracts.

**Independent Test**: Instantiate any domain facade directly in tests with Contract DTOs; verify business logic executes and returns Contract models without leaking ORM or transport internals.

### Tests for User Story 1
- [X] T011 [P] [US1] Contract tests for all Pydantic Contract models in `tests/contract/test_domain_contracts.py`.
- [X] T012 [P] [US1] Integration tests for all Domain Facades in `tests/integration/test_domain_facades.py`.

### Implementation for User Story 1
- [X] T013 [P] [US1] Implement Auth domain models and `AuthFacade` in `src/domains/auth/models/contract/user.py` and `src/domains/auth/facade/auth.py`.
- [X] T014 [P] [US1] Implement Ingestion domain models and `IngestionFacade` in `src/domains/ingestion/models/contract/telemetry.py` and `src/domains/ingestion/facade/ingestion.py`.
- [X] T015 [P] [US1] Implement Analytics domain models and `AnalyticsFacade` in `src/domains/analytics/models/contract/query.py` and `src/domains/analytics/facade/analytics.py`.
- [X] T016 [P] [US1] Implement Graph domain models and `GraphFacade` in `src/domains/graph/models/contract/graph.py` and `src/domains/graph/facade/graph.py`.
- [X] T017 [P] [US1] Implement AI domain models and `AIFacade` in `src/domains/ai/models/contract/ai.py` and `src/domains/ai/facade/ai.py` (communicating strictly with `GraphFacade`).
- [X] T018 [US1] Implement Pipeline domain models and `PipelineFacade` in `src/domains/pipeline/models/contract/pipeline.py` and `src/domains/pipeline/facade/pipeline.py`.

**Checkpoint**: MVP Complete - All 6 domains are accessible via Domain Facades with strict contract boundaries.

---

## Phase 4: User Story 2 - Unified FastAPI Endpoints & Transport Decoupling (Priority: P1)

**Goal**: Each domain exposes standardized FastAPI HTTP routes while maintaining full compatibility with the existing `artemis` CLI, with `artemis login` managing cached JWT credentials in `~/.artemis/token`.

**Independent Test**: Submit HTTP requests to domain endpoints and run CLI commands (`artemis login`, `artemis query`, `artemis ask`); verify both return identical results backed by Domain Facades.

### Tests for User Story 2
- [X] T019 [P] [US2] Contract tests for FastAPI endpoints in `tests/contract/test_api_endpoints.py`.
- [X] T020 [P] [US2] Integration test for CLI execution with JWT authentication in `tests/integration/test_cli_auth.py`.

### Implementation for User Story 2
- [X] T021 [P] [US2] Implement Auth FastAPI router in `src/domains/auth/api/router.py` (`POST /api/v1/auth/token`).
- [X] T022 [P] [US2] Implement Analytics FastAPI router in `src/domains/analytics/api/router.py` (`POST /api/v1/analytics/query`).
- [X] T023 [P] [US2] Implement AI FastAPI router in `src/domains/ai/api/router.py` (`POST /api/v1/ai/ask`).
- [X] T024 [P] [US2] Implement Ingestion FastAPI router in `src/domains/ingestion/api/router.py` (`POST /api/v1/ingestion/flush`).
- [X] T025 [P] [US2] Implement Graph FastAPI router in `src/domains/graph/api/router.py` (`POST /api/v1/graph/import-osint`).
- [X] T026 [P] [US2] Implement Pipeline FastAPI router in `src/domains/pipeline/api/router.py` (`POST /api/v1/pipeline/run`).
- [X] T027 [US2] Register all domain routers in `src/api.py`.
- [X] T028 [US2] Implement `artemis login` command in `src/cli/commands/login.py` (saving token to `~/.artemis/token`).
- [X] T029 [US2] Refactor existing CLI commands (`src/cli/commands/status.py`, `src/cli/commands/query.py`, `src/cli/commands/ask.py`, `src/cli/commands/pipeline.py`) to authenticate via `~/.artemis/token` and delegate to Domain Facades.

**Checkpoint**: User Stories 1 and 2 complete - both REST API and CLI operate through Domain Facades with JWT security.

---

## Phase 5: User Story 3 - Structured Operations & Lifecycle Steps (Priority: P2)

**Goal**: Multi-step workflows (buffer flush to MinIO, OSINT import, AI correlation) are executed as Temporal Workflows with reusable activity steps and targeted Google ADK 2.0 agentic reasoning.

**Independent Test**: Trigger `FlushBufferWorkflow` and `OsintImportWorkflow`; verify step-by-step Temporal execution history and error compensation.

### Tests for User Story 3
- [X] T030 [P] [US3] Integration test for Temporal workflows and activities in `tests/integration/test_temporal_workflows.py`.

### Implementation for User Story 3
- [X] T031 [P] [US3] Implement Temporal client connection helper in `src/base/temporal.py`.
- [X] T032 [P] [US3] Implement `FlushBufferWorkflow` and activity steps (`RotateBufferStep`, `ConvertToParquetStep`, `UploadToMinioStep`) in `src/domains/ingestion/operations/flush.py`.
- [X] T033 [P] [US3] Implement `OsintImportWorkflow` and activity steps (`ParseSpiderfootStep`, `ImportToMemgraphStep`) in `src/domains/graph/operations/import_osint.py`.
- [X] T034 [P] [US3] Implement Google ADK 2.0 multi-agent pipeline (`Planner`, `GuardianCritic`, `Executor`) in `src/domains/ai/operations/ai_agents.py`.
- [X] T035 [US3] Wire Temporal workflows into `IngestionFacade`, `GraphFacade`, and `AIFacade`.

**Checkpoint**: User Story 3 complete - durable workflows and agentic pipelines fully operational.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple domains, observability, and validation.

- [X] T036 [P] Configure pluggable Langfuse OpenTelemetry instrumentation in `src/api.py` lifespan.
- [X] T037 [P] Update Makefile with `make up` (including Temporal container) and `make test`.
- [X] T038 [P] Update architecture documentation in `docs/architecture/` with the new domain architecture.
- [X] T039 Execute full developer verification via `specs/002-uservice-alignment/quickstart.md`.
- [X] T040 Validate complete test suite execution with strict 60-second timeouts (`pytest -v --timeout=60 tests/`).

---

## Dependencies & Execution Order

### Phase Dependencies
- **Phase 1 (Setup)**: No dependencies - starts immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 - BLOCKS all user stories.
- **Phase 3 (User Story 1 - P1)**: Depends on Phase 2 - delivers core Facades & Contract boundaries (MVP).
- **Phase 4 (User Story 2 - P1)**: Depends on Phase 3 - adds FastAPI endpoints and CLI JWT authentication.
- **Phase 5 (User Story 3 - P2)**: Depends on Phase 3 and Phase 4 - adds Temporal workflows and ADK agents.
- **Phase 6 (Polish)**: Depends on all user stories being complete.

---

## Parallel Opportunities

- **Phase 1**: T001, T002, T003, T004 can all run in parallel.
- **Phase 2**: T005, T006, T007, T008, T009, T010 can run in parallel.
- **Phase 3**: Tests T011 and T012 can run in parallel; domain models/facades T013 through T017 can run in parallel across separate files.
- **Phase 4**: FastAPI routers T021 through T026 can run in parallel.
- **Phase 5**: Temporal activity steps T032, T033, and T034 can run in parallel.
