# Research: Decouple Test Mocks from Production Codebase

**Feature**: `006-remove-production-mocks`  
**Date**: 2026-10-20  
**Status**: Completed  

---

## Unknowns & Research Questions

### 1. External Dependency Failure Strategy
- **Context**: In `DynamicAgentLoop`, `GenAIService`, `MemgraphClient`, and `DockerPipelineRunner`, external connection or inference failures currently catch `Exception` and default to in-memory fake engines (`_run_simulated_loop`, `_mock_nodes`, subprocess fallback).
- **Decision**: Production components will raise explicit, typed domain exceptions (`ServiceUnavailableError`, `ConfigurationError`, `ConnectionError`) rather than catching errors or falling back to offline simulation heuristics.
- **Rationale**: Eliminates hidden failure states and phantom success where systems claim operational status while serving synthetic data. Operators and caller services receive immediate, actionable diagnostics.
- **Alternatives Considered**:
  - *Silent Simulation Fallback (Status Quo)*: Rejected because it masks network failures, authentication revocations, and configuration errors.
  - *Structured Error Dictionaries (without exceptions)*: Rejected because unhandled operational failures should disrupt execution and be caught by designated error-handling middleware rather than propagating pseudo-success payloads.

### 2. Location and Structure of Simulator & Generator Scripts
- **Context**: `src/scripts/simulate_telemetry.py` currently contains a telemetry simulator that falls back to writing synthetic records directly to `/tmp/artemis/buffer` if MQTT is unreachable.
- **Decision**: Relocate all simulation and event generator scripts out of `src/` entirely into `tools/` (or `tests/utils/`), and remove synthetic disk-buffer fallbacks so that tools interact exclusively with real services.
- **Rationale**: Keeps `src/` dedicated purely to production deployable modules. Development tools and load generators remain available under `tools/` for operators without polluting the production runtime package.
- **Alternatives Considered**:
  - *Retain in `src/scripts/`*: Rejected per user clarification decision.
  - *Relocate to `tests/` only*: Rejected because benchmark scripts are also used by operators for performance testing outside the pytest runner. Placing them in `tools/` preserves both CLI utility and test integration.

### 3. Architecture of Test Doubles and Mocks
- **Context**: Existing unit and integration tests rely on deterministic simulation heuristics (e.g. keyword-based Cypher and DuckDB dispatching, in-memory graph nodes, local Docker subprocess runner).
- **Decision**: Extract and encapsulate all mock logic into reusable test double classes under `tests/fixtures/mocks/`:
  - `MockGenAIClient`: Simulates Gemini client responses and multi-turn function calling based on the extracted heuristic loop.
  - `MockMemgraphClient`: Provides in-memory dictionary-backed node/edge storage and cypher query emulation.
  - `MockDockerRunner`: Provides safe local execution or stubbed container outputs.
  - `MockQueryCache` & `MockAuditLogger`: Provide in-memory storage for AI query caching and audit logging.
  These doubles are exposed via pytest fixtures in `tests/conftest.py`.
- **Rationale**: Maintains 100% test pass rate and offline capability while decoupling production code from test scaffolding. Centralized fixtures prevent duplication across test modules.
- **Alternatives Considered**:
  - *Ad-hoc monkeypatching in each test*: Rejected as fragile and highly repetitive across ~30 test files.
  - *Full Docker Compose for all tests*: Rejected because unit and contract tests must remain fast (<5s) and capable of running in lightweight CI without full container stacks.

### 4. Dependency Injection & Removal of `mock_mode` Parameters
- **Context**: 16 production files currently take `mock_mode: bool = False` in their constructors.
- **Decision**: Remove all `mock_mode` parameters and attributes from `src/`. Classes will accept interface-compatible dependencies (e.g. `client: Optional[MemgraphClient] = None`, `tools: Optional[AgentTools] = None`). In production, omitted dependencies default to real production instances. In tests, pytest fixtures pass the mock doubles into constructors.
- **Rationale**: Clean, idiomatic Python dependency injection conforming to Constitution Principle I (Library-First & Modular Architecture).
- **Alternatives Considered**:
  - *Keep `mock_mode=False` as a deprecated parameter*: Rejected because removing test flags from production code is the primary objective of this feature.
