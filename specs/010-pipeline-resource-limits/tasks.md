---
description: "Task list for Customizable CPU and Memory Limits for Pipeline Runs"
---

# Tasks: Customizable CPU and Memory Limits for Pipeline Runs

**Input**: Design documents from `/specs/010-pipeline-resource-limits/`

**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required for user stories), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Included per Constitution Principle III (Test-First & Integration Rigor: contract, unit, and integration tests are mandatory).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., `[US1]`, `[US2]`, `[US3]`)
- Exact file paths are included in every task description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Database schema evolution and environment configuration settings for default limits, minimum floors, administrator hard maximum caps, and overflow policy.

- [X] T001 Add nullable `default_cpu_limit DOUBLE PRECISION` and `default_memory_limit VARCHAR(32)` columns (with idempotent `ALTER TABLE project_pipelines ADD COLUMN IF NOT EXISTS`) to `project_pipelines` in src/config/postgres_init.sql
- [X] T002 [P] Configure system default, minimum floor, administrator hard maximum cap, and overflow policy settings (`docker_runner_cpu_limit`, `docker_runner_memory_limit`, `docker_runner_max_cpu_limit`, `docker_runner_max_memory_limit`, `docker_runner_min_cpu_limit`, `docker_runner_min_memory_limit`, `docker_runner_resource_overflow_policy`) in src/config/settings.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core Pydantic contracts and the deterministic resource parsing, unit normalization, cap validation, and hierarchical resolution engine that all user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Extend `PipelineCreateContract`, `PipelineUpdateContract`, `PipelineResponseContract`, `PipelineRunTriggerContract`, and `PipelineRunResponseContract` with optional pipeline default and per-run CPU/memory limit fields (`default_cpu_limit`, `default_memory_limit`, `cpu_limit`, `memory_limit`, `effective_cpu_limit`, `effective_memory_limit`, `requested_cpu_limit`, `requested_memory_limit`, `resource_clamped`, `details`) in src/domains/pipeline/models/contract/project_pipeline.py
- [X] T004 [P] Implement `ResolvedResourceAllocation`, case-insensitive memory size parser (`parse_memory_bytes`, `format_memory_limit`), operational floor validator, hard cap overflow policy evaluator (`reject` vs `clamp`), and hierarchical resolver (`validate_pipeline_default_resources`, `resolve_run_resources`) in src/domains/pipeline/operations/resource_validator.py
- [X] T005 [P] Create unit test suite covering memory unit normalization (`b`, `k`/`kb`, `m`/`mb`, `g`/`gb`), minimum operational floors (`0.1` CPU, `64m` RAM), `reject` vs `clamp` overflow policies, and lowered-cap fallback clamping in tests/unit/test_pipeline_resource_validator.py

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - Per-Pipeline Default and Per-Run Custom CPU & Memory Requests (Priority: P1) 🎯 MVP

**Goal**: Allow users to optionally configure default CPU and memory limits on a saved Pipeline definition and optionally request custom CPU and memory allocations per pipeline run trigger, resolving effective limits in the order `run request → pipeline default → system default` and enforcing them on the Docker execution container.

**Independent Test**: Create a pipeline with `default_cpu_limit=1.5` and `default_memory_limit="1g"`, trigger one run without overrides (verifying `1.5` CPU / `1g` memory are passed to the container), trigger a second run with `cpu_limit=2.5` and `memory_limit="2048m"` (verifying `2.5` CPU / `2048m` memory are passed), and trigger a third run on a pipeline without defaults (verifying system defaults `2.0` CPU / `2g` memory are passed).

### Tests for User Story 1 ⚠️

- [X] T006 [P] [US1] Add contract tests for `default_cpu_limit`/`default_memory_limit` on pipeline create/update/get and `cpu_limit`/`memory_limit` on pipeline run trigger in tests/contract/test_project_pipeline_contract.py
- [X] T007 [P] [US1] Add integration tests verifying `run override → pipeline default → system default` resolution and Docker container `nano_cpus` and `mem_limit` enforcement in tests/integration/test_docker_pipeline_runner.py

### Implementation for User Story 1

- [X] T008 [US1] Update `PipelineManager` (`_ensure_resource_columns`, `create_pipeline`, `get_pipeline`, `list_pipelines`, `update_pipeline`) to persist and retrieve `default_cpu_limit` and `default_memory_limit` in src/domains/pipeline/operations/pipeline_manager.py
- [X] T009 [P] [US1] Update `DockerPipelineRunner.execute_script` to accept optional `cpu_limit` and `memory_limit` arguments and apply resolved `nano_cpus` and `mem_limit` to `self._client.containers.run` in src/domains/pipeline/operations/docker_runner.py
- [X] T010 [US1] Update `PipelineExecutor.trigger_run` to resolve effective CPU and memory allocations via `resolve_run_resources` (`run request → pipeline default → system default`) and pass them to `self.docker_runner.execute_script` in src/domains/pipeline/operations/pipeline_executor.py
- [X] T011 [US1] Add `--default-cpu` and `--default-memory` CLI options to `artemis project pipeline create` and `update`, and `--cpu` and `--memory` CLI options to `artemis project pipeline run` in src/cli/commands/project.py

**Checkpoint**: User Story 1 is fully functional and independently testable.

---

## Phase 4: User Story 2 - Administrator Hard Maximum Caps & Validation Enforcement (Priority: P1)

**Goal**: Enforce administrator-configured hard maximum CPU (`4.0` cores default) and memory (`4g` default) caps and minimum operational floors (`0.1` cores, `64m` memory) across pipeline definitions and run requests, rejecting out-of-bounds values by default (`reject`) or clamping to the hard cap when `clamp` mode is enabled, and automatically clamping fallback defaults if a hard cap is lowered below a saved or system default.

**Independent Test**: Configure hard maximum caps (`4.0` CPU, `4g` RAM), submit a run request and a pipeline creation request with `cpu_limit=8.0` or `memory_limit="8g"` under `reject` mode (verifying immediate `400 Bad Request` / CLI exit code 1 before container creation), repeat under `clamp` mode (verifying execution is clamped to `4.0` CPU / `4g` RAM with `resource_clamped=True`), and verify below-floor inputs (`0.05` CPU or `16m` RAM) are always rejected.

### Tests for User Story 2 ⚠️

- [X] T012 [P] [US2] Add contract tests for out-of-bounds CPU/memory rejection (`400 Bad Request`), below-floor rejection (`< 0.1` CPU, `< 64m` memory), and `clamp` overflow policy behavior in tests/contract/test_project_pipeline_contract.py
- [X] T013 [P] [US2] Add integration tests for administrator hard cap enforcement (`reject` vs `clamp`) and lowered hard-cap fallback clamping across pipeline CRUD and run execution in tests/integration/test_pipeline_management.py

### Implementation for User Story 2

- [X] T014 [US2] Enforce `validate_pipeline_default_resources` in `PipelineManager.create_pipeline` and `PipelineManager.update_pipeline` before SQL execution in src/domains/pipeline/operations/pipeline_manager.py
- [X] T015 [US2] Enforce pre-execution resource validation (`resolve_run_resources`) at the start of `PipelineExecutor.trigger_run` prior to creating a run record or staging input datasets in src/domains/pipeline/operations/pipeline_executor.py
- [X] T016 [US2] Ensure FastAPI pipeline routes (`create_pipeline`, `update_pipeline`, `trigger_pipeline_run`) return `400 Bad Request` with actionable cap/floor validation messages on `ValueError` in src/domains/pipeline/api/routes.py

**Checkpoint**: User Stories 1 and 2 are both functional and enforce administrator hard caps.

---

## Phase 5: User Story 3 - Resource Allocation & OOM Visibility in Run Status & History (Priority: P2)

**Goal**: Persist and expose effective and requested CPU/memory limits, clamping status, and explicit Out-of-Memory (`exit_code: 137` / `OOMKilled`) diagnostics on pipeline run records and history across the REST API and CLI.

**Independent Test**: Execute pipeline runs with default, custom, and clamped limits plus a run that terminates with OOM (`exit_code: 137`), then inspect run responses and `artemis project pipeline runs` (both human-readable table and `--json`) to confirm `effective_cpu_limit`, `effective_memory_limit`, `resource_clamped`, and the OOM diagnostic message citing the enforced memory limit are accurately reported.

### Tests for User Story 3 ⚠️

- [X] T017 [P] [US3] Add integration tests verifying persisted run resource metadata (`effective_cpu_limit`, `effective_memory_limit`, `requested_cpu_limit`, `requested_memory_limit`, `resource_clamped`) and OOM termination (`exit_code: 137`, `status: FAILED`, OOM error message) in tests/integration/test_docker_pipeline_runner.py

### Implementation for User Story 3

- [X] T018 [P] [US3] Update `DockerRunnerResult` and `DockerPipelineRunner.execute_script` to detect container OOM termination (`exit_code == 137` or container `State.OOMKilled == True`) and populate `oom_killed: bool` in src/domains/pipeline/operations/docker_runner.py
- [X] T019 [US3] Update `PipelineManager.create_run_record`, `complete_run_record`, and `list_runs` to persist resource allocation metadata in `project_pipeline_runs.details` and hydrate `effective_cpu_limit`, `effective_memory_limit`, `requested_cpu_limit`, `requested_memory_limit`, `resource_clamped`, and `details` on `PipelineRunResponseContract` in src/domains/pipeline/operations/pipeline_manager.py
- [X] T020 [US3] Update `PipelineExecutor.trigger_run` to pass resolved resource metadata into run records and populate `status="FAILED"`, `exit_code=137`, and an explicit OOM diagnostic message referencing `effective_memory_limit` when an OOM kill is detected in src/domains/pipeline/operations/pipeline_executor.py
- [X] T021 [US3] Update `artemis project pipeline get`, `run`, and `runs` CLI commands to display pipeline default resources, applied run CPU/memory limits, clamping notices, and OOM diagnostic messages in formatted stdout/stderr and `--json` mode in src/cli/commands/project.py

**Checkpoint**: All user stories (US1, US2, US3) are complete and independently verifiable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end test suite verification and quickstart walkthrough validation.

- [X] T022 [P] Execute unit, contract, and integration test suites (`pytest tests/unit/test_pipeline_resource_validator.py tests/contract/test_project_pipeline_contract.py tests/integration/test_docker_pipeline_runner.py tests/integration/test_pipeline_management.py`) to verify 100% pass rate
- [X] T023 Validate CLI and REST API contract outputs against the scenarios in specs/010-pipeline-resource-limits/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1: Setup**: No dependencies — can start immediately.
- **Phase 2: Foundational**: Depends on Phase 1 completion — BLOCKS all user stories.
- **Phase 3: User Story 1 (P1)**: Depends on Phase 2 completion.
- **Phase 4: User Story 2 (P1)**: Depends on Phase 2 completion and integrates with Phase 3 pipeline manager/executor flows.
- **Phase 5: User Story 3 (P2)**: Depends on Phase 2 and Phase 3 completion.
- **Phase 6: Polish**: Depends on Phases 3–5 completion.

### User Story Dependencies

- **User Story 1 (P1)**: Starts immediately after Phase 2 (Foundational). Delivers MVP custom per-run and per-pipeline CPU/memory allocation support.
- **User Story 2 (P1)**: Enforces administrator hard caps and overflow policy (`reject` / `clamp`) across the pipeline CRUD and run trigger paths established in Phase 2/3.
- **User Story 3 (P2)**: Extends run records, Docker OOM detection (`exit_code: 137`), and CLI/API history reporting on top of the resolved resource allocations.

### Parallel Opportunities

- `T001` (`src/config/postgres_init.sql`) and `T002` (`src/config/settings.py`) can run in parallel.
- `T003` (`project_pipeline.py`), `T004` (`resource_validator.py`), and `T005` (`test_pipeline_resource_validator.py`) touch distinct files and can be developed in parallel.
- Within each User Story phase, contract tests (`T006`, `T012`) and integration tests (`T007`, `T013`, `T017`) can run in parallel with `DockerPipelineRunner` updates (`T009`, `T018`).

---

## Parallel Example: Foundational & User Story 1

```bash
# Foundational parallel tasks:
Task: "T003 Extend Pydantic contracts in src/domains/pipeline/models/contract/project_pipeline.py"
Task: "T004 [P] Implement resource_validator.py in src/domains/pipeline/operations/resource_validator.py"
Task: "T005 [P] Create unit test suite in tests/unit/test_pipeline_resource_validator.py"

# User Story 1 parallel tasks:
Task: "T006 [P] [US1] Add contract tests in tests/contract/test_project_pipeline_contract.py"
Task: "T007 [P] [US1] Add integration tests in tests/integration/test_docker_pipeline_runner.py"
Task: "T009 [P] [US1] Update DockerPipelineRunner.execute_script in src/domains/pipeline/operations/docker_runner.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1 & 2)

1. Complete **Phase 1: Setup** (`T001`–`T002`)
2. Complete **Phase 2: Foundational** (`T003`–`T005`)
3. Complete **Phase 3: User Story 1** (`T006`–`T011`) and **Phase 4: User Story 2** (`T012`–`T016`)
4. **STOP and VALIDATE**: Verify custom CPU/memory requests, pipeline defaults, system defaults, and hard cap enforcement (`reject` and `clamp`)
5. Complete **Phase 5: User Story 3** (`T017`–`T021`) for run history observability and OOM (`exit_code: 137`) diagnostics
6. Complete **Phase 6: Polish** (`T022`–`T023`)
