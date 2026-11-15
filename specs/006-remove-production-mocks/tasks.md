# Tasks: Decouple Test Mocks from Production Codebase

**Input**: Design documents from `/specs/006-remove-production-mocks/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md  
**Tests**: Included. The project constitution (Principle III) mandates strict contract and test isolation; mock doubles must support 100% test pass rate offline.  
**Organization**: Tasks are grouped by user story so each can be implemented and tested independently.  

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story (US1–US3) the task belongs to
- All paths are relative to the repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffolding for core exceptions, test fixture mock doubles, and developer tooling

- [X] T001 Create directory structure for core exceptions and test fixtures: `src/core/`, `tests/fixtures/mocks/`, and `tools/`
- [X] T002 [P] Create `tests/fixtures/mocks/__init__.py` exporting mock double symbols
- [X] T003 [P] Add exception module initialization in `src/core/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core exception hierarchy and reusable test doubles that all user stories depend on

**⚠️ CRITICAL**: No user story implementation or refactoring can begin until this phase is complete

- [X] T004 Implement `ArtemisError`, `ConfigurationError`, `ConnectionError`, and `ServiceUnavailableError` in `src/core/exceptions.py`
- [X] T005 [P] Implement `MockMemgraphClient` with in-memory graph storage (`nodes`, `edges`, cypher matcher) in `tests/fixtures/mocks/mock_memgraph.py`
- [X] T006 [P] Implement `MockQueryCache` with in-memory TTL caching and rate limiting in `tests/fixtures/mocks/mock_cache.py`
- [X] T007 [P] Implement `MockAuditLogger` with in-memory audit log list in `tests/fixtures/mocks/mock_audit.py`
- [X] T008 [P] Implement `MockDockerRunner` with isolated local subprocess execution in `tests/fixtures/mocks/mock_docker.py`
- [X] T009 Implement `MockGenAIClient` extracting dynamic loop simulation heuristics and function calling emulation into `tests/fixtures/mocks/mock_genai.py`
- [X] T010 Expose pytest fixtures (`mock_genai_client`, `mock_memgraph_client`, `mock_docker_runner`, `mock_query_cache`, `mock_audit_logger`) in `tests/conftest.py` (depends on T005, T006, T007, T008, T009)
- [X] T011 Write unit tests for exception hierarchy and mock doubles in `tests/unit/test_mock_fixtures.py` (depends on T004, T010)

**Checkpoint**: Foundation ready - user story refactoring can now proceed

---

## Phase 3: User Story 1 - Production Execution Transparency & Integrity (Priority: P1) 🎯 MVP

**Goal**: Production components execute genuine operational logic and fail fast with typed domain exceptions (`ConfigurationError`, `ConnectionError`, `ServiceUnavailableError`) instead of falling back to offline simulation heuristics or synthetic data.

**Independent Test**: Initialize components without credentials or with unreachable endpoints and verify they raise explicit domain exceptions instead of serving synthetic responses or activating `mock_mode`.

### Tests for User Story 1

- [X] T012 [P] [US1] Write contract test verifying `ConfigurationError` and `ServiceUnavailableError` on AI failures in `tests/contract/test_failure_handling.py`
- [X] T013 [P] [US1] Write contract test verifying `ConnectionError` on unreachable Memgraph, Redis, or Docker daemon in `tests/contract/test_connection_failures.py`

### Implementation for User Story 1

- [X] T014 [US1] Refactor `DynamicAgentLoop.run` in `src/domains/ai/operations/dynamic_loop.py`: remove `_run_simulated_loop`, validate API key (raising `ConfigurationError`), and raise `ServiceUnavailableError` on Gemini API failures (depends on T004)
- [X] T015 [US1] Refactor `GenAIService.ask` in `src/services/ai/genai_service.py`: remove fallback text generation, validate API key (raising `ConfigurationError`), and raise `ServiceUnavailableError` on inference errors (depends on T004)
- [X] T016 [US1] Refactor `MemgraphClient._connect` and `execute_query` in `src/services/graph/memgraph_client.py`: eliminate silent fallback to `mock_mode`, raise `ConnectionError` on connect failure, and raise `ServiceUnavailableError` on query failure (depends on T004)
- [X] T017 [US1] Refactor `DockerPipelineRunner.__init__` and `execute_script` in `src/domains/pipeline/operations/docker_runner.py`: remove fallback to mock runner, raise `ConnectionError` on daemon ping failure, and raise `ServiceUnavailableError` on container errors (depends on T004)
- [X] T018 [US1] Refactor `QueryCache._connect` in `src/services/ai/cache.py`: remove in-memory dictionary fallback and raise `ConnectionError` when Redis is unreachable (depends on T004)
- [X] T019 [US1] Refactor `AuditLogger.log_query` in `src/services/ai/audit_logger.py`: remove module-level `_in_memory_audit_logs` fallback and raise `ConnectionError` on PostgreSQL failure (depends on T004)

**Checkpoint**: User Story 1 complete. Production components fail fast with transparent domain exceptions (MVP).

---

## Phase 4: User Story 2 - Clean Separation of Production and Test Architectures (Priority: P2)

**Goal**: Purge all `mock_mode` parameters, attributes, and in-memory fake backends from all classes across `src/`; relocate generator scripts out of `src/` into `tools/`.

**Independent Test**: Audit `src/` to confirm zero occurrences of `mock_mode`, in-memory fake stores (`_mock_nodes`, `_mock_workspaces`), or simulation scripts remain in production.

### Tests for User Story 2

- [X] T020 [P] [US2] Write an automated codebase cleanliness test in `tests/unit/test_clean_architecture.py` verifying 0 occurrences of `mock_mode` or `_run_simulated_loop` across `src/`

### Implementation for User Story 2

- [X] T021 [US2] Refactor `KdgGraphStore` in `src/domains/discovery/operations/kdg_graph_store.py`: delete all `_mock_*` dictionaries (`_mock_workspaces`, `_mock_resources`, `_mock_attributes`, `_mock_entities`, `_mock_taxonomies`, `_mock_entity_links`, `_mock_lineage`) and eliminate all `if self.client.mock_mode:` branches
- [X] T022 [P] [US2] Refactor `src/domains/discovery/operations/lineage.py` and `src/domains/discovery/operations/entity_resolution.py`: remove all `mock_mode` branches and references to `graph_store._mock_*`
- [X] T023 [P] [US2] Refactor `AgentTools` in `src/domains/ai/operations/tools.py`: remove `mock_mode` parameter, attribute, and mock branching
- [X] T024 [P] [US2] Refactor `ExecutorAgent` and `MultiAgentPipelineOperation` in `src/domains/ai/operations/ai_agents.py`: remove `mock_mode` parameters and attributes
- [X] T025 [P] [US2] Refactor `AIDomainFacade` in `src/domains/ai/facade/ai.py`: remove `mock_mode` parameter and attributes from initialization and operation helpers
- [X] T026 [P] [US2] Refactor `GraphFacade` in `src/domains/graph/facade/graph.py`, `OsintImportOperation` in `src/domains/graph/operations/import_osint.py`, and `OsintImporter` in `src/services/graph/osint_importer.py`: remove `mock_mode` parameters and attributes
- [X] T027 [P] [US2] Refactor `ProjectGraphStorage` in `src/domains/project/operations/graph_storage.py`: remove `mock_mode` parameter and attribute
- [X] T028 [US2] Relocate `src/scripts/simulate_telemetry.py` to `tools/simulate_telemetry.py`, remove `_fallback_direct_buffer` synthetic disk fallback, and delete `src/scripts/simulate_telemetry.py`

**Checkpoint**: User Stories 1 and 2 complete. The `src/` codebase is completely purged of test logic, `mock_mode` flags, and simulation scripts.

---

## Phase 5: User Story 3 - Comprehensive Test Isolation and Mock Harness (Priority: P3)

**Goal**: Wire injected mock fixtures and test doubles across the test suite, verifying that all tests execute and pass cleanly offline with zero test logic remaining in production.

**Independent Test**: Execute `pytest tests/` in an isolated offline environment without Docker, Memgraph, or external network and assert that 100% of tests pass.

### Implementation for User Story 3

- [X] T029 [P] [US3] Refactor `tests/integration/test_dynamic_agent_loop.py` to inject `mock_genai_client` and `mock_memgraph_client` fixtures instead of `mock_mode=True`
- [X] T030 [P] [US3] Refactor `tests/unit/discovery/test_graph_store.py` to inject `mock_memgraph_client` instead of relying on `KdgGraphStore` mock branches
- [X] T031 [P] [US3] Refactor `tests/unit/discovery/test_lineage.py` and `tests/unit/discovery/test_entity_resolution.py` to use `mock_memgraph_client` fixture
- [X] T032 [P] [US3] Refactor `tests/unit/discovery/test_agent_tools.py` and `tests/contract/test_agent_tools.py` to use injected mock clients
- [X] T033 [P] [US3] Refactor `tests/contract/test_docker_runner_contract.py` and `tests/integration/test_docker_pipeline_runner.py` to use `mock_docker_runner` fixture
- [X] T034 [P] [US3] Refactor `tests/integration/test_ai_correlation.py` to inject `mock_genai_client` and `mock_memgraph_client` fixtures
- [X] T035 [P] [US3] Refactor `tests/contract/test_osint_import.py` and `tests/contract/test_domain_contracts.py` to use mock fixtures instead of `mock_mode=True`
- [X] T036 [P] [US3] Refactor remaining discovery unit tests (`test_enrichment.py`, `test_pattern_profiler.py`, `test_structural_indexer.py`, `test_membership.py`) to eliminate `mock_mode` arguments
- [X] T037 [US3] Update `tests/conftest.py` cleanup fixtures (`cleanup_databases_after_tests`) to check connection availability before executing detach queries, avoiding `mock_mode` attribute access

**Checkpoint**: All user stories complete. Tests run and pass 100% using test-side fixtures without production mock code.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verification against quickstart validation scenarios and final quality gates

- [X] T038 Execute quickstart Scenario 1 in `specs/006-remove-production-mocks/quickstart.md` verifying 0 `mock_mode` or `_run_simulated_loop` occurrences in `src/`
- [X] T039 [P] Execute quickstart Scenarios 2 & 3 in `specs/006-remove-production-mocks/quickstart.md` verifying explicit exception raising on failure
- [X] T040 Execute quickstart Scenario 4 in `specs/006-remove-production-mocks/quickstart.md` running full test suite `pytest tests/ -v`
- [X] T041 [P] Execute quickstart Scenario 5 in `specs/006-remove-production-mocks/quickstart.md` running `python3 tools/simulate_telemetry.py --help`
- [X] T042 [P] Update documentation links and comments across `docs/` or module docstrings removing legacy references to `mock_mode`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Phase 2 completion (exception hierarchy and mock doubles ready)
- **User Story 2 (Phase 4)**: Depends on Phase 2 and US1 completion (can run in parallel with US1 class refactoring where files do not conflict)
- **User Story 3 (Phase 5)**: Depends on US1 and US2 completion (tests are updated to match cleaned interfaces)
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Independent core logic refactoring; defines fail-fast behavior.
- **User Story 2 (P2)**: Purges `mock_mode` parameters and dead simulation code across the codebase.
- **User Story 3 (P3)**: Rewires test fixtures to align with US1 and US2 cleaned interfaces.

### Parallel Opportunities

- **Phase 1**: T002, T003 can run in parallel.
- **Phase 2**: T005, T006, T007, T008 can run in parallel (different mock files in `tests/fixtures/mocks/`).
- **Phase 3 (US1)**: T012 and T013 contract tests can run in parallel.
- **Phase 4 (US2)**: T022, T023, T024, T025, T026, T027 can run in parallel across independent domains.
- **Phase 5 (US3)**: T029, T030, T031, T032, T033, T034, T035, T036 can run in parallel across independent test files.
- **Phase 6**: T039, T041, T042 can run in parallel.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (`src/core/`, `tests/fixtures/mocks/`).
2. Complete Phase 2: Foundational (Exception classes + initial mock doubles).
3. Complete Phase 3: User Story 1 (Fail-fast exceptions in `dynamic_loop.py`, `memgraph_client.py`, `docker_runner.py`).
4. **STOP and VALIDATE**: Verify with `test_failure_handling.py` and `test_connection_failures.py`.

### Incremental Delivery

1. Phase 1 & 2 → Core exceptions and mock doubles established.
2. Phase 3 (US1) → Production components fail fast with transparent exceptions (MVP).
3. Phase 4 (US2) → All `mock_mode` parameters and dead mock stores purged from `src/`; telemetry simulator relocated to `tools/`.
4. Phase 5 (US3) → All ~30 test suites rewired to use injected fixtures; 100% offline pass rate verified.
5. Phase 6 → Full quickstart validation and documentation polish.
