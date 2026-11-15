# Implementation Plan: Decouple Test Mocks from Production Codebase

**Branch**: `006-remove-production-mocks` | **Date**: 2026-10-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-remove-production-mocks/spec.md`

## Summary

Decouple all testing logic, heuristic simulation loops, and mock fallbacks from the production codebase (`src/`). Production service clients (`DynamicAgentLoop`, `GenAIService`, `MemgraphClient`, `DockerPipelineRunner`, `QueryCache`, `AuditLogger`) will have all `mock_mode` flags, `self._mock_*` in-memory structures, and simulation heuristics (such as `_run_simulated_loop`) removed. In production, missing credentials or unreachable upstream services will fail fast by raising explicit, typed domain exceptions (`ConfigurationError`, `ConnectionError`, `ServiceUnavailableError`) defined in `src/core/exceptions.py`. All simulation and mock double logic is extracted into reusable test fixtures under `tests/fixtures/mocks/` and wired into test suites via standard pytest fixtures in `tests/conftest.py`. Standalone load simulation scripts (`simulate_telemetry.py`) are relocated from `src/scripts/` to `tools/`.

## Technical Context

**Language/Version**: Python 3.12+ (strictly typed, Pydantic v2 schemas where applicable)

**Primary Dependencies**: existing `google-genai`, `neo4j`, `docker`, `redis`, `duckdb`, `psycopg2-binary`, `pytest`, `pytest-asyncio`, `pytest-mock`

**Storage**:
- MinIO / DuckDB: Real telemetry analytical querying in production.
- Memgraph: Real Cypher graph storage in production; mock in-memory double in `tests/fixtures/mocks/mock_memgraph.py`.
- Redis: Real semantic cache in production; mock in-memory double in `tests/fixtures/mocks/mock_cache.py`.
- PostgreSQL: Real audit logger in production; mock in-memory double in `tests/fixtures/mocks/mock_audit.py`.

**Testing**: `pytest`, `pytest-asyncio`, pytest fixtures; 100% offline capability for unit and contract tests via test-side doubles.

**Target Platform**: Linux server (x86_64), containerized Docker Compose stack.

**Project Type**: Python service platform and CLI tool suite.

**Performance Goals**: Zero latency overhead in production; instantaneous (<10ms) fail-fast exception raising on missing dependencies.

**Constraints**: Idle memory budget unchanged (<12 GB); zero JVM dependencies; 0 instances of `mock_mode` or embedded simulation in `src/`.

**Scale/Scope**: Refactoring across 16 production modules in `src/domains/` and `src/services/`, 1 relocated script to `tools/`, creation of 5 reusable mock doubles in `tests/fixtures/mocks/`, and updating ~30 test files to use injected fixtures.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
| :--- | :---: | :--- |
| **I. Library-First & Modular Architecture** | **PASS** | Completely eliminates monolithic coupling of test harnesses and fake backends inside production libraries. |
| **II. Unified CLI Interface** | **PASS** | CLI commands and error exits continue to follow UNIX standard output and `--json` conventions. |
| **III. Test-First & Integration Rigor** | **PASS** | Rigorously enforces true contract and integration testing by isolating mock logic within `tests/` and eliminating fake production fallbacks. |
| **IV. Resource Constraint & Zero-JVM Sovereignty** | **PASS** | Zero JVM components; eliminates memory leaks caused by module-level `_in_memory_audit_logs` and in-memory mock dictionaries in production. |
| **Memory Budget (<12 GB)** | **PASS** | Production memory footprint is reduced by eliminating redundant mock engines. |
| **Security & Operational Governance** | **PASS** | Eliminates dangerous silent fallback where offline simulation might disguise network drops or credential revocations. |

**Post-design re-check**: PASS (no violations; Complexity Tracking empty).

## Project Structure

### Documentation (this feature)

```text
specs/006-remove-production-mocks/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── exceptions.md
│   ├── cleaned_interfaces.md
│   └── test_fixtures.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── core/
│   └── exceptions.py                                # NEW: ArtemisError, ConfigurationError, ConnectionError, ServiceUnavailableError
├── domains/
│   ├── ai/
│   │   ├── facade/ai.py                             # MODIFIED: remove mock_mode, pass client/dependencies
│   │   ├── operations/
│   │   │   ├── dynamic_loop.py                      # MODIFIED: remove _run_simulated_loop, mock_mode; fail-fast exceptions
│   │   │   ├── ai_agents.py                         # MODIFIED: remove mock_mode
│   │   │   └── tools.py                             # MODIFIED: remove mock_mode
│   ├── graph/
│   │   ├── facade/graph.py                          # MODIFIED: remove mock_mode
│   │   └── operations/import_osint.py               # MODIFIED: remove mock_mode
│   ├── discovery/
│   │   └── operations/
│   │       ├── kdg_graph_store.py                   # MODIFIED: remove all _mock_* dicts and mock_mode branches
│   │       ├── lineage.py                           # MODIFIED: remove mock_mode checks
│   │       └── entity_resolution.py                 # MODIFIED: remove mock_mode checks
│   ├── pipeline/
│   │   └── operations/docker_runner.py              # MODIFIED: remove mock_mode and subprocess fake runner
│   └── project/
│       └── operations/graph_storage.py              # MODIFIED: remove mock_mode
├── services/
│   ├── ai/
│   │   ├── genai_service.py                         # MODIFIED: remove mock_mode and heuristic text fallback
│   │   ├── cache.py                                 # MODIFIED: remove mock_mode and in-memory cache fallback
│   │   └── audit_logger.py                          # MODIFIED: remove mock_mode and module-level in-memory log list
│   └── graph/
│       ├── memgraph_client.py                       # MODIFIED: remove mock_mode, _mock_nodes, _mock_edges, cypher simulator
│       └── osint_importer.py                        # MODIFIED: remove mock_mode
└── scripts/
    └── simulate_telemetry.py                        # REMOVED (relocated to tools/)

tools/
└── simulate_telemetry.py                            # NEW LOCATION: Standalone load generator without synthetic disk buffer fallback

tests/
├── fixtures/
│   └── mocks/
│       ├── __init__.py                              # Exports all test doubles
│       ├── mock_genai.py                            # Extracted MockGenAIClient & dynamic loop simulator
│       ├── mock_memgraph.py                         # Extracted MockMemgraphClient with in-memory graph
│       ├── mock_docker.py                           # Extracted MockDockerRunner with isolated local execution
│       ├── mock_cache.py                            # Extracted in-memory MockQueryCache
│       └── mock_audit.py                            # Extracted in-memory MockAuditLogger
├── conftest.py                                      # MODIFIED: Expose mock fixtures (mock_genai_client, mock_memgraph_client, etc.)
├── contract/                                        # MODIFIED: Wire injected fixtures instead of mock_mode=True
├── integration/                                     # MODIFIED: Wire injected fixtures instead of mock_mode=True
└── unit/                                            # MODIFIED: Wire injected fixtures instead of mock_mode=True
```

**Structure Decision**:
Single project repository layout conforming to the existing modular hexagonal architecture. Production code under `src/` is strictly purged of test-only flags and fake backends. Reusable test doubles are encapsulated in `tests/fixtures/mocks/` and provided via `tests/conftest.py`. Developer load-generation scripts are housed in `tools/`.

## Complexity Tracking

> *No constitutional violations. Complexity tracking is empty.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
| :--- | :--- | :--- |
| *None* | *None* | *None* |
