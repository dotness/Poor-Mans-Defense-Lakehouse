# Comprehensive Repository Review: Specification, Documentation, and Implementation Analysis

**Project**: Poor Man's Defense Lakehouse (Sovereign Big Data Lakehouse & AI Infostructure)
**Date**: October 2026
**Reviewer**: Jules (Senior Platform & Software Architect)

---

## Executive Summary

This document presents a comprehensive review of the **Poor Man's Defense Lakehouse** codebase. It compares the high-level French military domain features, the four feature specifications (`001` to `004`), the architecture documentation (`docs/architecture/`), and the actual Python implementation (`src/`).

### Overall Health Assessment
- **Implementation Quality**: High. The core domain facades (`IngestionFacade`, `AnalyticsFacade`, `GraphFacade`, `AIFacade`, `ProjectFacade`, `PipelineFacade`) and Pydantic contract models provide clean domain-driven boundaries adhering closely to `uservice-template`.
- **Primary Gaps**: OpenAPI spec drift, missing Temporal worker process orchestration, minor CLI vs. REST API discrepancies, and unaddressed gaps between full French military ARTEMIS.IA capabilities and the single-VM "Poor-Man's" prototype scope.

---

## 1. Specification & Contract vs. Implementation Gaps

### 1.1 OpenAPI Specification Drift (`specs/002-uservice-alignment/contracts/openapi.json`)
- **Issue**: The `openapi.json` contract file in `specs/002-uservice-alignment/` defines only 4 routes (`/api/v1/auth/token`, `/api/v1/analytics/query`, `/api/v1/ai/ask`, `/api/v1/ingestion/flush`).
- **Actual Code**: The actual FastAPI gateway (`src/api.py`) exposes **26 routes** across Auth, Analytics, Ingestion, AI, Graph, Pipeline, and Project domains.
- **Impact**: API clients relying on `specs/002/.../openapi.json` will miss graph ingestion, project management, dataset queries, and sandboxed pipeline execution endpoints.
- **Recommendation**: Regenerate and commit `specs/002-uservice-alignment/contracts/openapi.json` directly from `app.openapi()` in FastAPI.

### 1.2 CLI Command Alignment vs. Specifications
- **Issue in CLI Auth**: `specs/002-uservice-alignment` (FR-011) mandates `artemis login` caching a JWT token in `~/.artemis/token` for both HTTP and CLI invocations.
  - **Implementation**: While `artemis login` exists (`src/cli/commands/login.py`) and writes `~/.artemis/token`, CLI commands (e.g., `artemis ask`, `artemis query`) invoke domain facades directly in-process without reading or validating `~/.artemis/token`. Token verification is enforced only when accessing the FastAPI REST layer via HTTP middleware (`src/security/middleware.py`).
- **Issue in Project Pipeline Triggering**: `specs/004` contract specifies `artemis project pipeline run <project-id> <pipeline-id>` with `--input-datasets` / `--target-dataset`.
  - **Implementation**: `src/cli/commands/project.py` supports `--dataset` / `--target-dataset`, but `--input-datasets` multi-dataset parameter mapping in CLI parses slightly differently than `POST /api/v1/projects/{project_id}/pipelines/{pipeline_id}/run`.

---

## 2. Architectural Inconsistencies & Self-Contradictions

### 2.1 Temporal Workflow Orchestration vs. In-Process Execution
- **Specification vs. Code**: `specs/002` (FR-010) and `docker-compose.yml` specify Temporal Server (`artemis-temporal`) for durable workflow and activity execution. `src/base/temporal.py` provides client initialization.
- **Implementation Reality**:
  - Domain operations (e.g., `FlushBufferOperation` in `src/domains/ingestion/operations/flush.py` and `DockerPipelineRunner` in `src/domains/pipeline/operations/docker_runner.py`) execute sequentially in-memory or via direct thread pools.
  - There is no active Temporal worker process running `Worker(client, task_queue=...)` listening for tasks in Docker Compose or `src/base/`.
- **Impact**: If the application crashes during a multi-step operation or long-running Docker pipeline run, Temporal cannot perform state recovery or activity retries because operations bypass Temporal workers.

### 2.2 Replaced JVM Components in Documentation vs. Compose Stack
- **Documentation**: `README.md` and `docs/architecture/` explicitly state:
  > *"By replacing heavyweight Java/JVM distributed frameworks (Kafka, Spark, Hadoop, OpenCTI, Neo4j) with high-efficiency native C/C++ and Go services, Artemis.IA keeps its complete idle memory footprint under 12 GB RAM."*
- **Database Choice**: Neo4j (JVM-based) is replaced by Memgraph (C++). Apache Kafka is replaced by Mosquitto (C MQTT broker). Spark/Trino is replaced by DuckDB (C++).
- **Contradiction**: `specs/001-simplified-artemis/spec.md` mentions buffering in "Redpanda/NATS JetStream", while the codebase exclusively uses a local file buffer (`/tmp/artemis/buffer` or `DATA_DIR/buffer`) and Mosquitto MQTT broker.
- **Clarification Needed**: The spec mentions Redpanda/NATS in early draft notes, but the final implementation correctly uses disk buffering to minimize memory footprint.

---

## 3. Dynamic Agent Tool Loop (`003-dynamic-agent-tools`) Review

### 3.1 Implementation Fidelity
- **Location**: `src/domains/ai/operations/dynamic_agent_loop.py`
- **Strengths**:
  - Implements multi-turn tool calling with Gemini (`gemini-2.5-flash-lite`).
  - Supports DuckDB (`query_analytics`), Memgraph (`query_graph`), and schema inspection (`get_schema_info`).
  - Enforces read-only AST/keyword guardrails blocking mutating operations (`DROP`, `DELETE`, `UPDATE`, `CREATE`, `SET`, `MERGE`).
  - Implements a deterministic offline fallback mode when `GOOGLE_AI_STUDIO_API_KEY` is not provided.

### 3.2 Inconsistencies & Gaps
- **Fallback Discrepancy**: In offline/mock mode, the fallback tool loop generates mock Cypher or SQL results. However, if the query mentions project-scoped datasets (Feature 004), the offline agent fallback context does not dynamically adjust to DuckDB project S3 paths.
- **Trace Contract**: `specs/003` (FR-006) requires `tool_calls` in `--json` output containing `execution_time_ms` and tool arguments. The CLI (`src/cli/commands/ask.py`) formats output well, but the API response model (`AskResponseContract`) in `src/domains/ai/models/contract.py` returns `sources_consulted` as a list of strings rather than structured `ToolCallStep` DTO objects.

---

## 4. Project Data Pipelines (`004-project-data-pipelines`) Review

### 4.1 Implementation Fidelity
- **Location**: `src/domains/project/` and `src/domains/pipeline/`
- **Strengths**:
  - Multi-tier Medallion architecture (BRONZE, SILVER, GOLD) with object storage (MinIO S3 prefixes) and graph tagging (`project_id`).
  - Script AST security validation (`src/domains/pipeline/operations/script_validator.py`) blocking unsafe Python modules (`os.system`, `subprocess`, `eval`, `importlib`).
  - Containerized execution via `DockerPipelineRunner` with resource bounds (CPU, memory, 300s timeout).

### 4.2 Inconsistencies & Gaps
- **Docker Image Dependency**: `DockerPipelineRunner` attempts to run `artemis-pipeline-runner:latest`. If this Docker image is not pre-built on the host VM, pipeline execution fails unless fallback mock execution is enabled or Docker is bypassed in test mode.
- **Database Engine Dual Connection**: `ProjectManager` (`src/domains/project/operations/project_manager.py`) connects directly using `psycopg2` on port `5433`, while `src/database/engine.py` uses SQLAlchemy async engine (`asyncpg`). This creates dual connection handling and requires PostgreSQL on port 5433 during unit tests.

---

## 5. French Military Domain Vision vs. "Poor-Man's" VM Implementation

The repository contains domain briefs under `features/` detailing the full Ministry of Armed Forces ARTEMIS.IA vision. The table below compares the high-level French military features with what is implemented in the single-VM prototype.

| Domain Feature (`features/`) | Military ARTEMIS.IA Vision | Poor-Man's VM Prototype Implementation | Gap / Status |
|---|---|---|---|
| **Escrim** (`escrim.md`) | Centralized Joint Intelligence, automated OSINT/SIGINT/IMINT/HUMINT ingestion, satellite imagery pattern recognition. | `OsintImporter` parses SpiderFoot JSON exports into Memgraph graph nodes (`Entity`, `Indicator`). | **Partial**: SpiderFoot OSINT ingestion supported; satellite IMINT / SIGINT ML pipelines not implemented. |
| **SIRCID** (`sircid.md`) | Counter-interference & threat detection (TESSCo), security clearance processing, weak signal correlation. | Cypher queries against Memgraph for shared IP/location entities and threat actor nodes. | **Partial**: Knowledge graph supports entity correlation; automated clearance processing omitted. |
| **Sovereign LLMs** (`sovereign_llms.md`) | On-premise Defense LLM (Berthier-Mistral-Military 24B) handling classified doctrines and military acronyms. | External Google AI Studio API (`gemini-2.5-flash-lite`). | **Architectural Choice**: Offloaded to Gemini cloud API to adhere to the <12-32GB RAM CPU-only VM constraint. |
| **Predictive Maintenance** (`predictive_maintenance.md`) | Operational Condition Maintenance (MCO) for SCORPION vehicles, aircraft, IoMT telemetry. | MQTT telemetry ingestion pipeline (`mqtt_listener.py` -> disk buffer -> DuckDB Parquet). | **Functional Core**: Ingestion & analytics engine implemented; specific predictive ML algorithms absent. |
| **Arcadia** (`arcadia.md`) | Decoupled C2 platform, mesh networks, resilient command posts. | Traefik reverse proxy with HTTPS/mTLS for edge communication. | **Framework Only**: Network entry point supported via Traefik. |
| **Maritime Surveillance** (`maritime_surveillance.md`) | AIS ship positioning, radar satellite imagery cross-referencing, anomaly detection. | DuckDB SQL analytics over Parquet datasets (`artemis query`). | **Data Model Ready**: Can query AIS Parquet files; domain-specific AIS algorithms not pre-packaged. |

---

## 6. Summary of Recommendations

1. **Update Contracts & OpenAPI Spec**:
   - Re-export `specs/002-uservice-alignment/contracts/openapi.json` from the live FastAPI app.
   - Enhance `AskResponseContract` to include full `tool_calls` trace details as specified in Feature 003.
2. **Harmonize Database Connections**:
   - Refactor `ProjectManager` to use the centralized database engine (`src/database/engine.py`) rather than raw `psycopg2` connections to prevent connection pool exhaustion and test failures when PostgreSQL is offline.
3. **Provision Temporal Workers**:
   - Add a dedicated `temporal_worker.py` daemon or container service to register activities and workflows for ingestion and pipeline runs, realizing the specification's durable execution guarantee.
4. **Standardize CLI Token Authentication**:
   - Update CLI command decorators to pass cached tokens from `~/.artemis/token` in HTTP headers when querying remote API gateways, or document that CLI direct-mode bypasses network auth intentionally for local management.

---
*End of Repository Review Report*
