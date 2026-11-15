# Implementation Tasks: Dynamic Multi-Database Agent Tool Loop

**Feature**: [003-dynamic-agent-tools](specs/003-dynamic-agent-tools/spec.md)  
**Date**: 2026-10-11  
**Spec**: [spec.md](specs/003-dynamic-agent-tools/spec.md) | **Plan**: [plan.md](specs/003-dynamic-agent-tools/plan.md)

---

## Phase 1: Setup (Contract & Schema Extensions)

**Purpose**: Establish data contracts for tool records and audit traces.

- [X] T001 [P] Extend `AIQueryResponseContract` with `ToolCallRecord` and `databases_consulted` in `src/domains/ai/models/contract/ai.py`.
- [X] T002 [P] Export new tool contract models in `src/domains/ai/models/contract/__init__.py`.

---

## Phase 2: Foundational (Safety Guardrails & Tool Interfaces)

**Purpose**: Core tools and read-only query guardrails that all agent loops depend on.

**⚠️ CRITICAL**: Must be completed before autonomous tool execution can begin.

- [X] T003 Implement read-only SQL and Cypher query validator in `src/domains/ai/operations/guardrails.py`.
- [X] T004 [P] Create safety guardrail unit tests in `tests/contract/test_query_guardrails.py`.
- [X] T005 Implement `query_analytics`, `query_graph`, and `get_schema_info` in `src/domains/ai/operations/tools.py`.
- [X] T006 [P] Create tool definition and contract tests in `tests/contract/test_agent_tools.py`.

**Checkpoint**: Foundational tools and guardrails ready and tested.

---

## Phase 3: User Story 1 & 2 - Dynamic Tool Loop (Priority: P1) 🎯 MVP

**Goal**: Enable the agent to autonomously decide what data to fetch across DuckDB and Memgraph to answer user inquiries.

**Independent Test**: Run `tests/integration/test_dynamic_agent_loop.py` to verify the agent calls both databases and returns a grounded response.

### Tests for User Story 1 & 2
- [X] T007 [P] [US1] Create integration test `tests/integration/test_dynamic_agent_loop.py` covering single-database and cross-database queries.

### Implementation for User Story 1 & 2
- [X] T008 [US1] Implement `DynamicAgentLoop` in `src/domains/ai/operations/dynamic_loop.py` supporting `google-genai` function calling with multi-turn loop and deterministic offline simulator.
- [X] T009 [US1] Refactor `ExecutorAgent` in `src/domains/ai/operations/ai_agents.py` to delegate to `DynamicAgentLoop`.
- [X] T010 [US1] Update `AIFacade.ask` in `src/domains/ai/facade/ai.py` to return the complete tool execution trace.
- [X] T011 [US1] Verify MVP by running `tests/integration/test_dynamic_agent_loop.py`.

**Checkpoint**: User Stories 1 & 2 fully functional and testable independently (MVP ready).

---

## Phase 4: User Story 3 & 4 - Safety Enforcement & Transparent Audit Trace (Priority: P2)

**Goal**: Guard against mutating database statements and provide a transparent audit trace of tool executions.

**Independent Test**: Submit mutating prompts to verify rejection, and verify `artemis ask --json` outputs `tool_calls`.

### Tests for User Story 3 & 4
- [X] T012 [P] [US3] Create safety guardrail integration test `tests/integration/test_agent_safety_guardrails.py` verifying mutating queries are rejected during agent execution.

### Implementation for User Story 3 & 4
- [X] T013 [US3] Enforce strict 5-second per-tool timeout and error feedback loop in `src/domains/ai/operations/tools.py`.
- [X] T014 [US4] Update `src/domains/ai/api/router.py` to include `tool_calls` and `databases_consulted` in FastAPI responses.
- [X] T015 [US4] Update CLI command in `src/cli/commands/ask.py` to format consulted databases in standard text and expose `tool_calls` in `--json` mode.

**Checkpoint**: Safety bounds enforced and audit trace fully exposed via CLI and REST.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Validation, documentation, and regression testing across the entire suite.

- [X] T016 [P] Update architecture documentation in `docs/architecture/microservice_domain_architecture.md` with dynamic tool loop diagrams.
- [X] T017 Execute developer verification scenarios via `specs/003-dynamic-agent-tools/quickstart.md`.
- [X] T018 Validate complete test suite execution with strict 60-second timeouts (`pytest -v --timeout=60 tests/`).

---

## Dependencies & Execution Order

### Phase Dependencies
- **Phase 1 (Setup)**: Starts immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 - BLOCKS User Story implementation.
- **Phase 3 (User Story 1 & 2 - P1 MVP)**: Depends on Phase 2.
- **Phase 4 (User Story 3 & 4 - P2)**: Depends on Phase 3.
- **Phase 5 (Polish)**: Depends on all user stories being complete.

---

## Implementation Strategy

### MVP First (Phases 1, 2, and 3)
1. Complete Setup (`T001`–`T002`) and Foundational (`T003`–`T006`).
2. Implement Dynamic Agent Tool Loop (`T007`–`T011`).
3. **STOP and VALIDATE**: Test User Story 1 independently with `tests/integration/test_dynamic_agent_loop.py`.
4. Implement Safety & Audit features (`T012`–`T015`).
5. Execute full quickstart and pytest verification (`T016`–`T018`).
