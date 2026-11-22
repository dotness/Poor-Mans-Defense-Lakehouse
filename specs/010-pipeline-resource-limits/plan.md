# Implementation Plan: Customizable CPU and Memory Limits for Pipeline Runs

**Branch**: `010-pipeline-resource-limits` | **Date**: 2026-11-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/010-pipeline-resource-limits/spec.md`

## Summary

Add end-to-end support for customizable CPU and memory limits on Docker-sandboxed pipeline executions, governed by administrator-defined system defaults (`2.0` CPU cores / `2g` memory) and hard maximum caps (`4.0` CPU cores / `4g` memory) configured via environment variables (`src/config/settings.py`).

Key technical capabilities:
1. **Hierarchical Resource Resolution (`Run Override → Pipeline Default → System Default`)**: Allows pipeline authors to optionally store `default_cpu_limit` and `default_memory_limit` on saved `Pipeline` definitions and operators to pass per-run `cpu_limit` and `memory_limit` overrides when triggering runs via CLI or REST API.
2. **Unit Normalization & Cap Validation Engine (`resource_validator.py`)**: Normalizes human-readable memory strings (`b`, `k`/`kb`, `m`/`mb`, `g`/`gb`, case-insensitive) into exact base-1024 byte counts, enforces minimum operational floors (`>= 0.1` CPU cores, `>= 64m` memory), and validates against administrator hard caps using a configurable overflow policy (`reject` by default, or `clamp`), while always clamping fallback defaults if an admin lowers a hard cap below a saved/system default (`FR-008`).
3. **Container Cgroup Enforcement & OOM (`exit_code: 137`) Diagnostics**: Passes resolved `nano_cpus` and `mem_limit` to `DockerPipelineRunner.execute_script(...)`, detects Out-of-Memory container kills (`exit_code == 137` or Docker `State.OOMKilled`), retains `status = "FAILED"` with `exit_code = 137`, and records an explicit OOM diagnostic message referencing the applied memory limit (`FR-011`).
4. **Full Audit Visibility**: Persists and surfaces `effective_cpu_limit`, `effective_memory_limit`, `requested_cpu_limit`, `requested_memory_limit`, and `resource_clamped` across PostgreSQL run metadata, REST API responses, and `artemis project pipeline` CLI output (`stdout` tables and `--json`).

## Technical Context

**Language/Version**: Python 3.12+ (strictly typed, Pydantic v2 contracts)

**Primary Dependencies**: Existing `docker` (Docker SDK for Python), `fastapi`, `pydantic`, `psycopg2-binary`, `click`, `tabulate`. Zero new third-party packages required.

**Storage**:
- **PostgreSQL**: `project_pipelines` (extended with nullable `default_cpu_limit DOUBLE PRECISION` and `default_memory_limit VARCHAR(32)`) and `project_pipeline_runs` (`details JSONB` stores resolved resource allocation metadata and OOM flags, hydrated onto `PipelineRunResponseContract`).

**Testing**: `pytest`, `pytest-asyncio`, contract tests (`tests/contract/test_project_pipeline_contract.py`), unit tests (`tests/unit/test_pipeline_resource_validator.py`), and integration tests (`tests/integration/test_docker_pipeline_runner.py`, `tests/integration/test_pipeline_management.py`).

**Target Platform**: Linux VM (x86_64, 16–32 GB RAM, CPU-only), Docker Engine for ephemeral pipeline container sandboxes.

**Project Type**: Multi-service data lakehouse platform (Unified `artemis` CLI + FastAPI REST Gateway + Docker container runner).

**Performance Goals**:
- Resource parsing and cap validation latency: `< 1ms` per request (`SC-003` requires rejection in `< 1s` prior to container launch).
- 100% enforcement parity between resolved CPU/memory limits and Docker container `nano_cpus`/`mem_limit` runtime parameters (`SC-002`).

**Constraints**: Total platform idle memory `< 12 GB RAM`; default per-run limit `2.0` CPU / `2g` RAM and hard maximum cap `4.0` CPU / `4g` RAM protect host stability; strictly Zero-JVM (`Principle IV`).

**Scale/Scope**: Applies to all project pipeline definitions and ephemeral Docker pipeline executions triggered via REST API or `artemis project pipeline` CLI.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Library-First & Modular Architecture** | **PASS** | Resource parsing, normalization, and policy validation are encapsulated in a self-contained module `src/domains/pipeline/operations/resource_validator.py` consumed cleanly by `PipelineManager`, `PipelineExecutor`, and `DockerPipelineRunner`. |
| **II. Unified CLI Interface (`--json`)** | **PASS** | `artemis project pipeline create/update/get/run/runs` expose `--default-cpu`, `--default-memory`, `--cpu`, and `--memory` flags, emit human-readable summaries to `stdout`, validation/OOM errors to `stderr`, and support `--json`. |
| **III. Test-First & Integration Rigor** | **PASS** | Contract tests for Pydantic models/API/CLI, unit tests for unit normalization and `reject`/`clamp` policies, and integration tests for Docker runner enforcement and `exit_code: 137` OOM diagnostics are planned first. |
| **IV. Resource Constraint & Zero-JVM Sovereignty** | **PASS** | Directly strengthens Principle IV by enforcing administrator hard maximum CPU (`4.0` cores) and memory (`4g`) caps on ephemeral pipeline containers so user scripts cannot exhaust the single-VM memory budget. |
| **Operating Constraints (RAM < 12 GB, Security)** | **PASS** | Strict input regex allow-listing on memory size strings, parameterized SQL queries for `project_pipelines` and `project_pipeline_runs`, and fail-closed validation on malformed/out-of-bounds inputs. |

*Post-Design Gate Evaluation*: **PASS** (Zero constitution violations).

## Project Structure

### Documentation (this feature)

```text
specs/010-pipeline-resource-limits/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── api_contracts.md
│   └── cli_contracts.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── config/
│   ├── settings.py                                        # MODIFIED: add max/min CPU & memory caps and overflow policy settings
│   └── postgres_init.sql                                  # MODIFIED: add default_cpu_limit & default_memory_limit to project_pipelines
├── domains/
│   └── pipeline/
│       ├── models/
│       │   └── contract/
│       │       └── project_pipeline.py                    # MODIFIED: add default_cpu/memory_limit and run cpu/memory_limit + effective fields
│       ├── operations/
│       │   ├── resource_validator.py                      # NEW: memory unit parser, floor/cap validator, hierarchical resource resolver
│       │   ├── docker_runner.py                           # MODIFIED: accept custom cpu_limit/memory_limit and detect OOM (exit_code 137)
│       │   ├── pipeline_manager.py                        # MODIFIED: persist pipeline default limits and hydrate run resource fields
│       │   └── pipeline_executor.py                       # MODIFIED: resolve run -> pipeline -> system limits, pass to runner, format OOM details
│       └── api/
│           └── routes.py                                  # MODIFIED: return 400 Bad Request on resource cap/floor validation errors
└── cli/
    └── commands/
        └── project.py                                     # MODIFIED: add --default-cpu, --default-memory, --cpu, --memory flags & display columns

tests/
├── contract/
│   └── test_project_pipeline_contract.py                  # MODIFIED: verify resource fields & validation contracts on pipeline CRUD and run trigger
├── unit/
│   └── test_pipeline_resource_validator.py                # NEW: unit tests for memory unit parsing, floors, reject/clamp policies, fallback clamping
└── integration/
    ├── test_docker_pipeline_runner.py                     # MODIFIED: verify custom CPU/memory pass-through and OOM exit code 137 handling
    └── test_pipeline_management.py                        # MODIFIED: verify end-to-end pipeline default + per-run override resolution & API/CLI errors
```

**Structure Decision**: Extends the existing `src/domains/pipeline/` domain and `src/cli/commands/project.py` CLI command group in-place, adding a focused `resource_validator.py` operation module without introducing any new top-level services or external dependencies.

## Complexity Tracking

No constitution violations; section intentionally empty.

## Verification Plan

### Functional & Integration Verification

1. **Unit Tests (`tests/unit/test_pipeline_resource_validator.py`)**:
   - Verify case-insensitive memory unit normalization (`b`, `k`/`kb`, `m`/`mb`, `g`/`gb`), confirming `2048m == 2g == 2147483648` bytes.
   - Verify rejection of values below minimum floors (`< 0.1` CPU cores, `< 64m` memory), zero/negative numbers, `NaN`/`inf`, and malformed unit strings under both `reject` and `clamp` modes.
   - Verify `reject` vs. `clamp` policy behavior when explicit requests exceed `DOCKER_RUNNER_MAX_CPU_LIMIT` or `DOCKER_RUNNER_MAX_MEMORY_LIMIT`.
   - Verify hierarchical precedence (`run_override → pipeline_default → system_default`) and automatic fallback clamping when an admin lowers a hard cap below a saved pipeline or system default (`FR-008`).
2. **Contract & Integration Tests (`tests/contract/test_project_pipeline_contract.py`, `tests/integration/test_docker_pipeline_runner.py`, `tests/integration/test_pipeline_management.py`)**:
   - Verify `PipelineCreateContract`, `PipelineUpdateContract`, `PipelineResponseContract`, `PipelineRunTriggerContract`, and `PipelineRunResponseContract` serialization and API error status codes (`400 Bad Request`).
   - Verify `DockerPipelineRunner.execute_script` translates resolved limits to `nano_cpus` and `mem_limit` and translates OOM kills (`exit_code == 137` / `State.OOMKilled`) into `FAILED` run records with explicit OOM diagnostic messages.

### Security Verification (`mandatory-secure-web-skills`)

- **Input Validation & Allow-Listing**: All memory limit strings are validated against a strict regex allow-list (`^\s*(\d+(?:\.\d+)?)\s*([bkmg]b?)?\s*$`) and finite numeric bounds before any arithmetic or Docker API invocation, preventing command/argument injection or integer overflow DoS.
- **Database Parameterization**: All SQL queries in `PipelineManager` (`create_pipeline`, `update_pipeline`, `create_run_record`, `complete_run_record`, `list_runs`) strictly use `psycopg2` parameterized placeholders (`%s`) and `Json(...)` adapters—never string concatenation of user inputs.
- **Resource Exhaustion (DoS) Protection & Fail-Closed Design**: Enforcing minimum floors (`0.1` CPU, `64m` RAM) and administrator hard maximum caps (`4.0` CPU, `4g` RAM) with fail-closed validation prevents single-request container exhaustion attacks against the host VM; containers continue running with `network_mode="none"` and read-only input bind mounts.
- **Test Server Binding & Error Hygiene**: All test fixtures bind strictly to `127.0.0.1` / `localhost` (never `0.0.0.0`), and API validation errors return sanitized `400 Bad Request` messages without exposing internal stack traces or database credentials.

### Automated Security Check

- **Security Scanner**: Run a scan on all newly created files to identify common vulnerabilities (e.g., XSS, SQL injection). If findings are detected, auto-apply the fix and document the results.
- **Security Audit**: Audit the new code for design-level security issues (input validation, secrets handling, auth checks). Document findings and remediations in the `walkthrough.md` artifact using the `generate_security_audit_report` skill.
