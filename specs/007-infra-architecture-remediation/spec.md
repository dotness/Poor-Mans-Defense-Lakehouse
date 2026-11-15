# Feature Specification: Infrastructure and Architecture Technical Debt Remediation

**Feature Branch**: `007-infra-architecture-remediation`

**Created**: 2026-10-24

**Status**: Draft

**Input**: User description: "Architectural / Infrastructure Gaps Active Technical Debt Missing Temporal worker daemon, OpenAPI contract drift, synchronous psycopg2 vs async DB engine, and broken .venv symlink."

## Clarifications

### Session 2026-10-24

- Q: How should the new Temporal background worker process be orchestrated and deployed across platform environments? → A: Dedicated container service in `docker-compose.yml` running an `artemis worker run` CLI command (Option A).
- Q: What strategy should be used to refactor synchronous `psycopg2` calls in `ProjectManager` to use the platform's asynchronous database architecture? → A: Full declarative SQLAlchemy ORM models (`Project`, `Dataset`, `Pipeline`) mapping all tables integrated with `src/database/engine.py` (Option B).
- Q: How should OpenAPI contract synchronization and drift detection be enforced across development and CI workflows? → A: Automated test gate in `tests/contract/` asserting zero drift, paired with a `make sync-openapi` generator command (Option A).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resilient Asynchronous Workflow Execution (Priority: P1)

As a platform operator and data engineer, I need background ingestion flushes, OSINT graph data ingestion, and metadata enrichment workflows to be processed reliably by an active background worker daemon deployed as a dedicated container (`artemis worker run`), so that operations execute durably, recover from transient failures, and do not fall back to synchronous in-process blocking threads.

**Why this priority**: Durable background processing is a core architectural requirement for platform resilience. Without an active worker daemon, workflows timeout or fail silently to fallback paths, undermining the platform's reliability under load.

**Independent Test**: Trigger a buffer flush or OSINT graph import with external workflow engine enabled; verify that the operation is picked up, executed, and completed by the background worker container process without falling back to direct synchronous execution.

**Acceptance Scenarios**:

1. **Given** the platform infrastructure is running with the worker container active, **When** a data ingestion flush or OSINT import workflow is dispatched, **Then** the dedicated worker daemon picks up and completes the workflow tasks within the expected queue timeout.
2. **Given** a transient network disconnection occurs during workflow execution, **When** the workflow engine retries the activity according to retry policies, **Then** the worker resumes the task without losing processing state or duplicating data.
3. **Given** the worker daemon is running, **When** operator inspects service health status via `artemis status` or `docker compose ps`, **Then** the worker process reports active health and task queue polling.

---

### User Story 2 - Unified Asynchronous Database Access with Declarative ORM (Priority: P2)

As an engineer and system administrator, I need all domain modules—including project management, data pipelines, and metadata indexing—to interact with relational storage using declarative SQLAlchemy ORM models (`Project`, `Dataset`, `Pipeline`) and unified asynchronous connection pooling, so that database operations do not cause connection pool exhaustion, port conflicts, or blocking event loops.

**Why this priority**: Mixed database connection models (synchronous direct drivers vs. asynchronous pooled engines) create architectural drift, cause connection leaks during high concurrent load, and break automated testing isolation. Declarative ORM models establish type-safe, maintainable domain abstractions.

**Independent Test**: Execute concurrent project creation, dataset registration, and pipeline triggering requests under load, and verify that all operations query and persist data through declarative ORM models and the shared asynchronous connection pool without opening unmanaged synchronous connections.

**Acceptance Scenarios**:

1. **Given** multiple concurrent project and pipeline management requests, **When** database queries execute, **Then** all queries utilize declarative ORM models via the shared asynchronous engine and connection pool without exhausting database connection limits.
2. **Given** an automated integration test execution without external PostgreSQL available, **When** test database mocks or fixtures are injected, **Then** project management operations respect the centralized engine and ORM session abstraction without failing on unhandled driver-specific socket calls.

---

### User Story 3 - Authoritative and Synchronized API Contract (Priority: P3)

As a frontend developer, external partner, or API consumer, I need the published OpenAPI specification to accurately represent all operational endpoints across all domains (Auth, Analytics, AI, Ingestion, Graph, Pipeline, Project, Discovery), so that client SDK generation and integration contracts remain trustworthy.

**Why this priority**: Significant drift between live REST routes and the published API contract prevents automated client generation, breaks third-party integration, and misrepresents platform capabilities.

**Independent Test**: Compare the published specification file against the runtime gateway schema export; verify that all registered routes, request schemas, response codes, and security requirements match with zero undocumented paths, enforced via an automated test in `tests/contract/test_api_endpoints.py`.

**Acceptance Scenarios**:

1. **Given** the operational API gateway, **When** `make sync-openapi` is triggered, **Then** the contract file is generated containing all active routes across all 9 domain routers.
2. **Given** an automated contract verification check in `tests/contract/test_api_endpoints.py`, **When** schema drift is detected between code and the committed OpenAPI file, **Then** the test fails with specific diff diagnostics indicating missing or altered endpoints.

---

### User Story 4 - Reproducible Development and Execution Environment (Priority: P4)

As a developer or automated test runner, I need the local Python virtual environment, package dependencies, and container runner images to initialize consistently across host environments, so that test suites (`make test`) and containerized data pipelines run out-of-the-box without manual interpreter fixes.

**Why this priority**: Developer productivity and CI reliability require zero-friction environment initialization. Broken interpreter symlinks and unbuilt container images impede local development and test execution.

**Independent Test**: Run the environment setup and verification command on a clean workspace, and verify that the virtual environment interpreter resolves correctly, dependencies load, and all unit/contract tests execute cleanly.

**Acceptance Scenarios**:

1. **Given** a development machine with standard Python available, **When** the environment setup command is executed, **Then** the local virtual environment is created with a valid executable interpreter and required dependencies installed.
2. **Given** a freshly configured platform workspace, **When** an automated test suite or container runner execution is triggered, **Then** the pipeline runner image is built or validated without manual container build steps.

---

### Edge Cases

- **Workflow Engine Unavailability**: When the workflow orchestration engine is unavailable at startup, the worker daemon must log clear retry diagnostics and attempt exponential backoff reconnection without terminating abruptly.
- **Connection Starvation Under Spike**: When incoming database requests exceed available pool size, requests must queue cleanly with bounded timeouts rather than dropping client connections abruptly.
- **Schema Evolution in Contracts**: When a domain model introduces optional or deprecated fields, the generated API contract must reflect these backward-compatible annotations without breaking existing client contracts.
- **Python Version Mismatch**: When the host system provides Python 3.12 vs 3.14, the setup toolchain must detect and link against the compatible runtime version while respecting binary extension compatibility.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST provide a dedicated workflow worker process started via `artemis worker run` capable of executing registered activities and workflows (including ingestion buffer flushing, OSINT graph import, and knowledge enrichment).
- **FR-002**: The workflow worker MUST be declared as a managed container service (`worker`) in `docker-compose.yml` with healthcheck reporting and automatic restart policies.
- **FR-003**: Domain operations MUST log transparent diagnostic warnings and route through durable workflows when the workflow engine is healthy, eliminating silent fallback masks during operational runs.
- **FR-004**: All relational database operations across project, pipeline, and discovery domains MUST use declarative SQLAlchemy ORM models (`Project`, `Dataset`, `Pipeline`) mapped to `src/database/base.py` and execute through asynchronous sessions from `src/database/engine.py`.
- **FR-005**: The project management domain MUST eliminate direct unmanaged synchronous `psycopg2` database connections and raw dictionary cursors in favor of declarative ORM models and asynchronous sessions.
- **FR-006**: The published OpenAPI specification contract (`specs/002-uservice-alignment/contracts/openapi.json`) MUST be synchronized with the runtime FastAPI gateway via a dedicated `make sync-openapi` command covering all 9 active domain routers.
- **FR-007**: A contract validation test in `tests/contract/test_api_endpoints.py` MUST be provided to assert zero drift between the live FastAPI schema and the committed OpenAPI specification.
- **FR-008**: The platform development environment setup toolchain MUST create and maintain a working Python virtual environment with valid interpreter symlinks matching the host Python runtime.
- **FR-009**: The execution automation suite (`Makefile`) MUST provide reliable targets to initialize dependencies, configure the environment, and execute tests without broken interpreter references.
- **FR-010**: The containerized analytical pipeline runner image (`artemis-pipeline-runner:latest`) MUST have an automated build and verification target accessible through standard setup commands.
- **FR-011**: Any remaining legacy test or utility scripts residing in `src/scripts/` (such as `seed_graph.py`) MUST be relocated to the appropriate tools directory to maintain production codebase purity.

### Key Entities

- **WorkflowWorkerDefinition**: Represents the background execution process, its listening task queues, registered workflows, and worker concurrency limits.
- **ProjectOrmModel**: Declarative SQLAlchemy ORM entity representing project workspaces, memberships, metadata, and timestamps.
- **DatasetOrmModel**: Declarative SQLAlchemy ORM entity representing registered datasets, storage tiers (BRONZE/SILVER/GOLD), schemas, and S3 paths.
- **PipelineOrmModel**: Declarative SQLAlchemy ORM entity representing Python transformation pipelines, schedules, and container execution metadata.
- **DatabaseConnectionConfiguration**: Represents the centralized connection pool, authentication credentials, async dialect settings, and session lifecycle.
- **ApiContractSpecification**: The complete OpenAPI 3.x schema definition capturing all domain routes, path parameters, request bodies, and response models.
- **EnvironmentRuntimeProfile**: The configuration state capturing local virtual environment interpreter paths, package requirements, and container runtime image tags.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of dispatched durable background workflows (ingestion flush, graph ingestion) are executed by the worker daemon when the workflow engine is active, with zero silent fallbacks to direct thread execution.
- **SC-002**: All relational database operations utilize declarative SQLAlchemy ORM models and the unified asynchronous connection pool, eliminating 100% of unmanaged synchronous driver connections.
- **SC-003**: The published OpenAPI specification covers 100% of active REST routes exposed by the API gateway (expanding coverage from 4 routes to all 26+ routes) with automated zero-drift CI enforcement.
- **SC-004**: Platform automated test suite (`make test`) and setup commands run to completion with zero interpreter or path configuration errors on supported host environments.
- **SC-005**: All utility and development scripts are 100% decoupled from the production source directory `src/`.

## Assumptions

- The host environment provides a supported 64-bit Linux distribution with Docker and a compatible Python installation (Python 3.12 or 3.14).
- The workflow orchestration engine (Temporal) service remains part of the local Docker Compose deployment stack as defined in the platform architecture.
- PostgreSQL database credentials and connection parameters defined in platform settings are sufficient for all domains sharing the unified asynchronous database engine.
- Offloading heavy JVM dependencies remains a core architectural constraint; the workflow worker and database drivers must remain lightweight compiled or Python runtimes adhering to the platform's memory budget.
