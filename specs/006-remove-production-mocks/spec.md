# Feature Specification: Decouple Test Mocks from Production Codebase

**Feature Branch**: `006-remove-production-mocks`

**Created**: 2026-10-20

**Status**: Draft

**Input**: User description: "Remove all business logic and code used for testing that is part of production code. The testing code should be mocked from tests , not reside in production code as a fallback or backup in case of testing. Methods like _run_simulated_loop in dynamic_loop.py are example of such behavior. Refactor the code by moving the code from production codebase to tests and wire in as mocks during needed tests."

## Clarifications

### Session 2026-10-20

- Q: How should production components behave when external dependencies (Gemini API, Memgraph, Docker) fail or are unavailable? → A: Raise explicit domain exceptions: Fail fast with typed exceptions (e.g., ServiceUnavailableError, ConfigurationError) so callers handle failures without masked state.
- Q: Should generator and load simulation scripts under src/scripts/ (e.g. simulate_telemetry.py) be retained or moved? → A: Relocate all simulation/generator scripts out of src/ entirely into tests/ or tools/.
- Q: How should the relocated test mocks and simulators be organized within the test architecture? → A: Reusable mock classes in tests/fixtures/: Provide dedicated test doubles (e.g. MockGenAIClient, MockMemgraphClient, MockDockerRunner) exposed via pytest fixtures.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Production Execution Transparency & Integrity (Priority: P1)

As an analyst and system operator, I need production service operations and dynamic reasoning loops to execute only genuine operational logic and communicate transparently with live components, so that system errors, network failures, and service unavailability are accurately detected and reported rather than disguised by embedded simulation or synthetic fallbacks.

**Why this priority**: Core platform reliability and operational trust depend on transparent failure modes; silent fallbacks into simulation during outages create misleading intelligence and hinder production incident diagnosis.

**Independent Test**: Can be tested independently by running operational workflows without external dependencies and verifying that operations fail explicitly with clear diagnostic notifications rather than returning synthetic simulated results.

**Acceptance Scenarios**:

1. **Given** an operational environment with configured external services, **When** an analyst executes an inquiry, **Then** the operation processes through live services and returns real intelligence results.
2. **Given** an operational environment where external services are disconnected or fail, **When** an analyst executes an inquiry, **Then** the system provides an explicit operational error response and does not emit synthetic simulation data or heuristic fallback answers.

---

### User Story 2 - Clean Separation of Production and Test Architectures (Priority: P2)

As a platform developer and maintainer, I need production classes, facades, and operational clients to have interfaces dedicated purely to business needs without test-only operational modes or embedded fake data stores, so that the codebase is maintainable, clean, and adheres strictly to modular separation of concerns.

**Why this priority**: Embedding test harnesses, simulation scripts, and fake backends inside production modules creates technical debt, bloats the production artifact, and violates the single-responsibility principle.

**Independent Test**: Can be tested independently by auditing production module signatures and logic to verify that zero test-specific execution branches, mock modes, or simulation scripts exist in `src/`.

**Acceptance Scenarios**:

1. **Given** production service interfaces and class initializers, **When** inspected by developers or integration harnesses, **Then** all constructors and methods contain only parameters relevant to production operation, with no mock-specific toggles or fallback branches.
2. **Given** production execution of storage, graph, or container execution operations, **When** dependencies are unreachable, **Then** the operations signal clear connectivity or execution exceptions instead of initializing local in-memory fake repositories.
3. **Given** utility and event simulation scripts (such as `simulate_telemetry.py`), **When** auditing `src/`, **Then** all such simulation and synthetic generation scripts have been relocated out of `src/` to `tests/` or dedicated tool directories.

---

### User Story 3 - Comprehensive Test Isolation and Mock Harness (Priority: P3)

As a quality engineer, I need automated test suites to mock external boundaries and simulate complex interactions entirely from within the test framework, so that tests remain fast, reproducible, and offline-capable without polluting production code.

**Why this priority**: Preserving comprehensive test coverage and rapid developer feedback loops is essential when decoupling test logic from production code.

**Independent Test**: Can be tested independently by executing the entire automated test suite offline and verifying that all tests pass using test-side mocks and fixtures.

**Acceptance Scenarios**:

1. **Given** test suites simulating external boundaries (AI models, graph databases, container runtimes), **When** tests execute, **Then** test-side reusable mock doubles in `tests/fixtures/` and pytest fixtures provide the necessary responses without any test logic residing in the production package.
2. **Given** complex behavioral scenarios previously reliant on production simulation loops, **When** evaluated in tests, **Then** the scenarios pass with complete parity using test-side doubles and injected mock fixtures.

---

### Edge Cases

- **Service Disconnection during Live Operation**: When an external upstream dependency (e.g. Gemini AI, Memgraph, Docker daemon) becomes unavailable or fails during an ongoing operation, the system must fail fast by raising a typed domain exception (such as `ServiceUnavailableError`) instead of catching the error and falling back to offline simulation heuristics.
- **Missing Configuration / Credentials**: When essential credentials or configuration settings are missing in production (e.g. missing API key), the application must immediately raise a `ConfigurationError` during initialization rather than silently switching into an offline simulation state.
- **Offline Test Execution**: When automated unit test suites are run in an isolated environment without network or container access, all mock behaviors must be supplied by reusable mock classes in `tests/fixtures/` via standard pytest fixtures.
- **Load Generation and Benchmarking**: Developers executing telemetry generation or stress tests must run relocated scripts from `tests/` or `tools/` with real broker connectivity; no fake disk-buffer shortcuts should exist in production.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Production operational components MUST NOT contain heuristic simulation engines, synthetic response generators, or offline test fallbacks.
- **FR-002**: Production service classes and constructors MUST NOT accept test-specific execution flags (such as mock-mode parameters) or initialize internal mock data structures.
- **FR-003**: Production service components MUST raise explicit, typed domain exceptions (e.g., `ServiceUnavailableError`, `ConfigurationError`) when required configurations, external connections, or operational dependencies fail, rather than silently catching exceptions or falling back to simulated operation.
- **FR-004**: All test simulation algorithms, offline response patterns, and mock database doubles MUST be isolated within reusable test mock classes under `tests/fixtures/` (e.g., `MockGenAIClient`, `MockMemgraphClient`, `MockDockerRunner`).
- **FR-005**: Automated test suites MUST supply mock doubles via standard pytest fixtures and dependency injection, eliminating ad-hoc mock branching in production.
- **FR-006**: The platform MUST preserve all existing functional test assertions and coverage across all test suites after the removal of production mock code.
- **FR-007**: Production components MUST support standard dependency injection patterns to allow test harnesses to supply external doubles cleanly without altering production contracts.
- **FR-008**: Utility and data generator scripts containing simulation or synthetic event generation (e.g., `simulate_telemetry.py`) MUST be relocated out of the `src/` production codebase entirely into `tests/` or dedicated tooling directories.

### Key Entities *(include if feature involves data)*

- **Service Operation**: Represents an operational task executed within the system, defining input parameters, execution lifecycle, external dependency interactions, and explicit error states.
- **Test Mock Adapter / Double**: Represents a test-side class located in `tests/fixtures/` that implements or intercepts service interfaces during automated testing to simulate external interactions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of production files in `src/` are free of test-specific execution parameters, in-memory fake stores, and offline simulation fallback routines.
- **SC-002**: 100% of existing automated unit and integration tests pass successfully using test-side mock adapters and fixtures.
- **SC-003**: 0 instances of silent simulation fallback occur when external services encounter operational errors in production environments.
- **SC-004**: Automated test suites execute completely and deterministically in offline environments without modifying production binaries or configurations.
- **SC-005**: 0 simulation or synthetic generator scripts remain under `src/`.

## Assumptions

- The automated testing framework supports standard dependency injection, monkey-patching, and test double fixtures.
- Production environments provide valid configurations and connectivity for all required external services; absence of connectivity constitutes a system fault.
- Test scenarios requiring simulated multi-turn tool loops or offline database responses can be fully fulfilled by reusable test double classes under `tests/fixtures/`.
