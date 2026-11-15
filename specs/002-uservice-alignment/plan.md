# Implementation Plan: Microservice Architecture Alignment

**Branch**: `[002-uservice-alignment]` | **Date**: 2026-10-11 | **Spec**: [specs/002-uservice-alignment/spec.md](specs/002-uservice-alignment/spec.md)

**Input**: Feature specification from `specs/002-uservice-alignment/spec.md`

---

## Summary

Refactor the Artemis Python services into modular Domain-Driven Design (DDD) domain packages (`ingestion`, `analytics`, `graph`, `ai`, `pipeline`, `auth`) aligned with `github.com/dotness/uservice-template`. Each domain implements coarse-grained `DomainFacade` classes, Pydantic Contract DTO boundaries, and thin FastAPI routers, backed by Temporal workflows for durable multi-step operations and a full JWT/OAuth2 security layer.

---

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**:
- `fastapi>=0.100`, `uvicorn>=0.20` (HTTP API Gateway)
- `temporalio>=1.0` (Durable workflow & activity orchestration)
- `pydantic>=2.0`, `pydantic-settings>=2.0` (Contract models & configuration)
- `sqlalchemy>=2.0`, `asyncpg>=0.28`, `alembic>=1.12` (Database persistence)
- `pyjwt>=2.6`, `passlib[bcrypt]>=1.7` (JWT & security stack)
- `google-adk>=2.0.0b1`, `google-genai` (Targeted agentic workflows for AI & OSINT)
- `langfuse>=3.0.0`, `opentelemetry-sdk>=1.20.0` (Pluggable distributed tracing)

**Storage Engines**:
- PostgreSQL 16 (Operational metadata, Temporal database, User/Audit records)
- MinIO S3 (Parquet lakehouse)
- Memgraph 2.x (In-memory Knowledge Graph via openCypher Bolt)
- Mosquitto 2.x (MQTT Ingestion Bus)
- Redis 7 (Semantic caching, rate limiting)

**Testing**: `pytest -v --timeout=60` (Contract, Unit, and Integration test suites)  
**Target Platform**: Linux Server (single-node VM with 16–32 GB RAM, 0 GPU)  
**Project Type**: Modular Domain Service with unified CLI and FastAPI Gateway  
**Performance Goals**: Sub-second API responses (<1s p95 for analytics/queries, sub-15ms DuckDB queries)  
**Constraints**: Total idle memory consumption across all platform containers and Python services strictly under 12 GB RAM  
**Scale/Scope**: 5 business domains (`ingestion`, `analytics`, `graph`, `ai`, `pipeline`) + 1 security domain (`auth`)

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle / Constraint | Status | Notes |
| :--- | :--- | :--- |
| **I. Library-First & Modular Architecture** | **PASS** | Every domain is isolated with explicit Facades and Contract DTOs; zero monolithic coupling. |
| **II. Unified CLI Interface** | **PASS** | All existing `artemis` CLI commands preserved; `artemis login` added for JWT credential management. |
| **III. Test-First Rigor** | **PASS** | Strict contract and integration test requirements with explicit 60-second timeouts. |
| **IV. Resource Constraint (<12GB RAM)** | **PASS** | FastAPI (~40 MB) + Temporal Server (~300 MB) adds ~340 MB total, preserving >8 GB headroom on 16GB VM. |

---

## Project Structure

### Documentation (this feature)

```text
specs/002-uservice-alignment/
├── spec.md              # Feature specification with clarifications
├── plan.md              # Implementation plan (this file)
├── research.md          # Phase 0 technical research & design choices
├── data-model.md        # Phase 1 data models & contracts
├── quickstart.md        # Phase 1 developer verification guide
├── contracts/           # Phase 1 API schema definitions
│   └── openapi.json     # OpenAPI 3.1 gateway contract
├── checklists/
│   └── requirements.md  # Specification quality checklist
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code Layout

```text
src/
├── api.py                     # Master FastAPI application aggregating domain routers
├── config/
│   └── settings.py            # Pydantic Settings
├── database/                  # Shared SQLAlchemy async engine & mixins
│   ├── engine.py
│   └── base.py
├── security/                  # JWT token verification & ContextVar user context
│   ├── jwt.py
│   └── middleware.py
├── base/                      # Common base classes
│   ├── facade.py              # DomainFacade base class
│   └── operations.py          # BaseOperation & step classes
├── domains/
│   ├── auth/                  # Authentication & user management domain
│   │   ├── api/               # /api/v1/auth router
│   │   ├── facade/            # AuthFacade
│   │   └── models/            # Token & User contracts
│   ├── ingestion/             # Telemetry & buffering domain
│   │   ├── api/               # /api/v1/ingestion router
│   │   ├── facade/            # IngestionFacade
│   │   ├── models/            # Telemetry contracts
│   │   └── operations/        # FlushBufferOperation (Temporal workflow)
│   ├── analytics/             # DuckDB analytical query domain
│   │   ├── api/               # /api/v1/analytics router
│   │   ├── facade/            # AnalyticsFacade
│   │   └── models/            # Query contracts
│   ├── graph/                 # Memgraph & OSINT domain
│   │   ├── api/               # /api/v1/graph router
│   │   ├── facade/            # GraphFacade
│   │   ├── models/            # Entity & Edge contracts
│   │   └── operations/        # OsintImportOperation (Temporal workflow + ADK)
│   ├── ai/                    # GenAI RAG & correlation domain
│   │   ├── api/               # /api/v1/ai router
│   │   ├── facade/            # AIFacade
│   │   ├── models/            # AIQuery contracts
│   │   └── operations/        # ADK Planner/Critic/Executor agent pipeline
│   └── pipeline/              # Batch pipeline orchestration domain
│       ├── api/               # /api/v1/pipeline router
│       ├── facade/            # PipelineFacade
│       └── models/            # Pipeline run contracts
└── cli/                       # Artemis CLI (invoking Domain Facades directly)
    ├── main.py
    └── commands/
        ├── login.py
        ├── status.py
        ├── query.py
        ├── ask.py
        └── pipeline.py

tests/
├── contract/                  # Pydantic contract model tests
├── integration/               # Cross-domain Facade & Temporal integration tests
└── unit/                      # Unit tests for domain logic
```

**Structure Decision**: Selected modular domain architecture (`src/domains/`) within the Artemis repository, adopting the full 4-subpackage pattern (`api/`, `facade/`, `models/`, `operations/`) from `uservice-template` and fronting it with a unified FastAPI application and the `artemis` CLI.

---

## Complexity Tracking

| Mechanism | Why Needed | Simpler Alternative Rejected Because |
| :--- | :--- | :--- |
| **Temporal Workflow Engine** | Required for durable, replayable multi-step execution with compensation logic as mandated by `uservice-template`. | Simple procedural scripts (`mqtt_to_minio.py`) lack distributed state tracking, workflow retries, and unified task queue orchestration. |
| **JWT / OAuth2 Security Stack** | Provides uniform authorization across HTTP REST APIs and CLI invocations (`artemis login`). | Basic HTTP auth lacks fine-grained permission scopes, token expiry lifecycle, and standard bearer token interoperability. |
| **Google ADK 2.0 Multi-Agent Pipeline** | Enhances complex RAG queries with Planner and Guardian Critic safety checks before LLM execution. | Single-pass prompt generation lacks prompt-injection defense and multi-step graph exploration planning. |
