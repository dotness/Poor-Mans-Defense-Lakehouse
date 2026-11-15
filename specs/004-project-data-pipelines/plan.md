# Implementation Plan: Project-Scoped Data Ingestion & Medallion Pipelines

**Branch**: `004-project-data-pipelines` | **Date**: 2026-10-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-project-data-pipelines/spec.md`

---

## Summary

Extend the Poor Man's Defense Lakehouse architecture with multi-project workspace isolation, heterogeneous data ingestion (Parquet/tabular into MinIO and graph entities into Memgraph), collaborative `Pipeline` entities supporting user-uploaded Python transformation scripts, and Docker-sandboxed execution across Bronze, Silver, and Gold medallion tiers. 

The implementation introduces a new `ProjectDomain` (`src/domains/project/`), upgrades `PipelineDomain` (`src/domains/pipeline/`) with a secure Docker runner activity, and adds unified `artemis project` CLI commands and FastAPI REST endpoints.

---

## Technical Context

**Language/Version**: Python 3.12+ (strictly typed, Pydantic v2 contracts)

**Primary Dependencies**: 
- `docker` (Python Docker SDK for container lifecycle management)
- `duckdb` (C++ vectorized in-memory query engine)
- `pyarrow` (Apache Arrow / Parquet compression)
- `minio` (S3 object storage client)
- `neo4j` (Memgraph Bolt client)
- `fastapi` & `uvicorn` (REST API layer)
- `click` & `tabulate` (UNIX CLI interface)
- `psycopg2-binary` (PostgreSQL state management)

**Storage**:
- PostgreSQL (:5433): Project metadata, pipeline entities, and execution run audit records.
- MinIO (:9000): Object lake partitioned as `s3://telemetry/projects/{project_id}/{tier}/{dataset}/`.
- Memgraph (:7687): Knowledge graph entities tagged with `project_id`.

**Testing**: `pytest`, `pytest-asyncio`, `fastapi.testclient.TestClient`, Docker mock runners for CI/CD test isolation.

**Target Platform**: Linux server / VM (x86_64), Docker engine enabled.

**Project Type**: Multi-service platform (CLI + REST API + Background Docker Activities).

**Performance Goals**:
- Project creation and dataset ingestion in < 10 seconds.
- 50,000 tabular records transformed from Bronze to Silver in < 20 seconds.
- DuckDB analytical queries over project partitions in < 2 seconds.

**Constraints**:
- Strict Zero-JVM sovereignty (< 12 GB RAM idle across all platform containers).
- Ephemeral Docker execution with 2 GB RAM limit and 300s process timeout per run.
- Zero cross-project data bleed.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / Rule | Compliance Status | Justification & Architectural Evidence |
| :--- | :--- | :--- |
| **I. Library-First & Modular Architecture** | **PASS** | `ProjectFacade` and `ProjectPipelineFacade` follow standard `DomainFacade` patterns with isolated operations and models (`contract/`, `storage/`, `operations/`). |
| **II. Unified CLI Interface** | **PASS** | Adds `artemis project` subcommands (`create`, `list`, `ingest`, `pipeline`, `query`) with standard stdout/stderr separation and `--json` support. |
| **III. Test-First & Integration Rigor** | **PASS** | Contract tests (`tests/contract/test_project_contracts.py`) and integration tests (`tests/integration/test_project_pipelines.py`) use mocked Docker runners and clean up all test resources automatically. |
| **IV. Resource Constraint & Zero-JVM** | **PASS** | No Java/JVM components. Uses native DuckDB, MinIO, Memgraph, and ephemeral C/Python Docker runner containers. Total idle RAM remains well under 12 GB. |
| **Memory Budget (< 12 GB idle)** | **PASS** | Pipeline runners are ephemeral (`--rm`) and execute only on-demand, consuming 0 GB at idle. |

---

## Project Structure

### Documentation (this feature)

```text
specs/004-project-data-pipelines/
├── spec.md              # Feature specification with user requirements
├── plan.md              # This implementation plan
├── research.md          # Architectural decisions (Postgres metadata, Docker sandbox, S3 partitioning)
├── data-model.md        # Relational ERD and Pydantic contract definitions
├── contracts/           # API and CLI interface contracts
│   ├── api_contracts.md
│   └── cli_contracts.md
├── quickstart.md        # End-to-end runnable validation guide
└── checklists/
    └── requirements.md  # Quality validation checklist
```

### Source Code Layout

```text
src/
├── config/
│   ├── postgres_init.sql                # Added tables: projects, project_pipelines, pipeline_runs
│   └── settings.py                      # Added docker_runner_image, run_timeout settings
├── domains/
│   ├── project/                         # New Domain: Project Management
│   │   ├── api/routes.py                # FastAPI routes (/api/v1/projects)
│   │   ├── facade/project.py            # ProjectFacade
│   │   ├── models/
│   │   │   └── contract/project.py      # Project Pydantic contracts
│   │   └── operations/
│   │       ├── project_manager.py       # Project CRUD operations
│   │       └── scoped_ingestion.py      # Project tabular & graph ingestion
│   └── pipeline/                        # Upgraded Domain: Pipeline Management
│       ├── api/routes.py                # Pipeline routes (/api/v1/projects/{id}/pipelines)
│       ├── facade/pipeline.py           # PipelineFacade (extended for project pipelines)
│       ├── models/
│       │   └── contract/project_pipeline.py # Pipeline & Run contracts
│       └── operations/
│           ├── pipeline_manager.py      # Pipeline entity CRUD
│           └── docker_runner.py         # Ephemeral Docker container execution runner
├── cli/
│   └── commands/
│       └── project.py                   # CLI subcommands under `artemis project`
└── api.py                               # Mounts project & pipeline routers

tests/
├── contract/
│   ├── test_project_contracts.py        # Validates Pydantic contracts and API models
│   └── test_project_pipeline_contract.py # Validates pipeline CRUD & run contracts
└── integration/
    ├── test_project_lifecycle.py        # End-to-end project creation, ingestion, isolation
    └── test_docker_pipeline_runner.py   # Tests Docker runner execution with mock container
```

---

## Complexity Tracking

> **Constitution check passes completely with zero violations.** No unbudgeted JVM dependencies, bloated frameworks, or unmanaged daemon processes are introduced.
