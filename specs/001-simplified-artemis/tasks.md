# Tasks: Simplified Artemis

**Branch**: `001-simplified-artemis` | **Date**: 2026-09-04 | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

This document contains the actionable, dependency-ordered task breakdown for implementing the Simplified Artemis platform on a single Linux Virtual Machine.

---

## User Stories Summary

- **User Story 1 (Priority: P1) 🎯 MVP**: Secure Telemetry and Data Ingestion — Ingest high-frequency edge events via MQTT, buffer to disk, and batch flush to MinIO Parquet.
- **User Story 2 (Priority: P1)**: High-Performance Analytics and Querying — Vectorized in-memory SQL queries via embedded DuckDB directly over MinIO Parquet files in < 5s.
- **User Story 3 (Priority: P2)**: AI-Powered Intelligence Correlation — Correlate entities in Memgraph, ingest OSINT scans, and execute natural language RAG intelligence queries via Google AI Studio API with Redis caching.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project scaffolding, dependency definitions, and development environment setup.

- [X] T001 Initialize repository directory structure per implementation plan (`src/cli/`, `src/config/`, `src/services/`, `src/pipelines/`, `src/scripts/`, `tests/`)
- [X] T002 [P] Configure Python project dependencies and packaging in pyproject.toml
- [X] T003 [P] Create environment configuration template in .env.example
- [X] T004 [P] Create top-level Makefile for platform lifecycle management (`up`, `down`, `clean`, `test`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core container infrastructure, authentication, and shared database services that MUST be healthy before user story implementation.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 Create multi-container Docker Compose configuration in docker-compose.yml (Mosquitto, MinIO, PostgreSQL, Redis, Memgraph, Traefik, SpiderFoot)
- [X] T006 [P] Create Mosquitto broker configuration with persistence and listener rules in src/config/mosquitto.conf
- [X] T007 [P] Create Traefik reverse proxy configuration with TLS/mTLS and service routing in src/config/traefik.yml
- [X] T008 [P] Configure Traefik authentication middleware (HTTP Basic Auth / Authelia forward-auth) in src/config/auth.yml
- [X] T009 [P] Create PostgreSQL database initialization script for relational schemas in src/config/postgres_init.sql
- [X] T010 [P] Implement central platform settings and environment loader in src/config/settings.py
- [X] T011 Implement unified CLI entry point and service health check command (`artemis status`) in src/cli/main.py and src/cli/commands/status.py

**Checkpoint**: Foundation ready — all core containers start healthy under 12GB idle RAM; `artemis status` reports service availability.

---

## Phase 3: User Story 1 - Secure Telemetry and Data Ingestion (Priority: P1) 🎯 MVP

**Goal**: Ingest high-frequency telemetry events from edge devices via MQTT, write to local NVMe buffer, and flush into columnar Parquet objects in MinIO.

**Independent Test**: Run `make simulate-telemetry` to publish 10,000 events, trigger `artemis pipeline run mqtt_to_minio`, and assert Parquet objects exist in `s3://telemetry/`.

### Tests for User Story 1 ⚠️

- [X] T012 [P] [US1] Contract test for MQTT telemetry JSON payload validation in tests/contract/test_mqtt_contract.py
- [X] T013 [P] [US1] Integration test for MQTT listener buffering and MinIO Parquet batch write in tests/integration/test_ingestion_pipeline.py

### Implementation for User Story 1

- [X] T014 [P] [US1] Implement TelemetryEvent domain model and payload validation in src/services/ingestion/models.py
- [X] T015 [US1] Implement MQTT subscriber and local disk buffer writer in src/services/ingestion/mqtt_listener.py
- [X] T016 [P] [US1] Implement MinIO S3 bucket initializer and Parquet batch writer in src/services/ingestion/minio_writer.py
- [X] T017 [US1] Implement batch flush pipeline logic in src/pipelines/mqtt_to_minio.py (depends on T015, T016)
- [X] T018 [US1] Implement pipeline management CLI command (`artemis pipeline`) in src/cli/commands/pipeline.py
- [X] T019 [P] [US1] Create edge telemetry ingestion simulator script in src/scripts/simulate_telemetry.py

**Checkpoint**: User Story 1 complete — edge telemetry streams into Mosquitto without loss and lands partitioned in MinIO Parquet storage.

---

## Phase 4: User Story 2 - High-Performance Analytics and Querying (Priority: P1)

**Goal**: Execute complex analytical SQL queries over MinIO Parquet datasets using embedded DuckDB in under 5 seconds.

**Independent Test**: Execute `artemis query --sql "SELECT metric, AVG(value) FROM read_parquet('s3://telemetry/*.parquet') GROUP BY metric"` and verify sub-second execution.

### Tests for User Story 2 ⚠️

- [X] T020 [P] [US2] Integration test for DuckDB SQL querying over MinIO S3 Parquet in tests/integration/test_analytics_query.py

### Implementation for User Story 2

- [X] T021 [P] [US2] Implement DuckDB client wrapper with MinIO S3 httpfs credentials in src/services/analytics/duckdb_client.py
- [X] T022 [US2] Implement query execution service with table, JSON, and CSV formatters in src/services/analytics/query_service.py (depends on T021)
- [X] T023 [US2] Implement analytical query CLI command (`artemis query`) in src/cli/commands/query.py (depends on T022)
- [X] T024 [P] [US2] Add analytical benchmarking target (`query-analytics`) in Makefile

**Checkpoint**: User Story 2 complete — analysts can query multi-gigabyte telemetry datasets via DuckDB directly from the CLI.

---

## Phase 5: User Story 3 - AI-Powered Intelligence Correlation (Priority: P2)

**Goal**: Maintain an intelligence knowledge graph in Memgraph, import OSINT collection scans, and answer natural language analyst queries via Google AI Studio API with Redis caching.

**Independent Test**: Run `make seed-graph`, execute `artemis ask "What are the common IP addresses associated with recent anomalies?"`, and verify natural language answer grounded in Memgraph data.

### Tests for User Story 3 ⚠️

- [X] T025 [P] [US3] Integration test for Memgraph entity retrieval and Google GenAI RAG flow in tests/integration/test_ai_correlation.py
- [X] T026 [P] [US3] Contract test for SpiderFoot OSINT export parsing in tests/contract/test_osint_import.py

### Implementation for User Story 3

- [X] T027 [P] [US3] Implement Memgraph Bolt client and Cypher query builder in src/services/graph/memgraph_client.py
- [X] T028 [P] [US3] Implement OSINT import service to ingest SpiderFoot scan exports into Memgraph in src/services/graph/osint_importer.py
- [X] T029 [P] [US3] Implement Redis semantic query cache and rate limiter in src/services/ai/cache.py
- [X] T030 [US3] Implement Google AI Studio client with graph context augmentation in src/services/ai/genai_service.py (depends on T027, T029)
- [X] T031 [US3] Implement PostgreSQL audit logger for AI interactions in src/services/ai/audit_logger.py
- [X] T032 [US3] Implement natural language question CLI command (`artemis ask`) in src/cli/commands/ask.py (depends on T030, T031)
- [X] T033 [P] [US3] Create synthetic intelligence graph seeding script in src/scripts/seed_graph.py

**Checkpoint**: User Story 3 complete — intelligence nodes and OSINT data are correlated in Memgraph and queryable via natural language through Google AI Studio.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: System hardening, configuration cleanup, documentation, and repository standard alignment.

- [X] T034 [P] Create repository VERSION file with initial release 0.1.0 in VERSION
- [X] T035 [P] Normalize SQLite database path in .agents/skills/ltv-cone-manager/scripts/manage_cone.py and clean redundant root db
- [X] T036 Execute full validation sequence defined in specs/001-simplified-artemis/quickstart.md
- [X] T037 [P] Update platform deployment and operations documentation in README.md

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1: Setup ──► Phase 2: Foundational ──┬──► Phase 3: User Story 1 (P1 - MVP)
                                           ├──► Phase 4: User Story 2 (P1)
                                           └──► Phase 5: User Story 3 (P2)
                                                         │
                                                         ▼
                                           Phase 6: Polish & Cross-Cutting
```

- **Setup (Phase 1)**: No dependencies — executes immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion.
- **User Story 2 (Phase 4)**: Depends on Foundational completion; operates on Parquet files produced by US1 (or seeded test data).
- **User Story 3 (Phase 5)**: Depends on Foundational completion; operates independently with Memgraph + Google AI Studio.
- **Polish (Phase 6)**: Runs after desired user stories are verified.

---

## Parallel Opportunities

- **Phase 1 (Setup)**: Tasks `T002`, `T003`, `T004` can run in parallel once `T001` completes.
- **Phase 2 (Foundational)**: Configuration tasks `T006`, `T007`, `T008`, `T009`, `T010` can proceed in parallel once `T005` is drafted.
- **Phase 3 (User Story 1)**: Tests `T012`, `T013`, models `T014`, `T016`, and simulator `T019` can be developed in parallel.
- **Phase 4 (User Story 2)**: Test `T020`, client `T021`, and Makefile target `T024` can proceed in parallel.
- **Phase 5 (User Story 3)**: Tests `T025`, `T026`, Memgraph client `T027`, OSINT importer `T028`, Redis cache `T029`, and seed script `T033` can proceed in parallel.
- **Phase 6 (Polish)**: Tasks `T034`, `T035`, `T037` can run in parallel.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup: directory layout, dependencies, Makefile).
2. Complete Phase 2 (Foundational: Docker Compose stack, auth configs, database init, `artemis status`).
3. Complete Phase 3 (User Story 1: MQTT ingestion, buffer writer, MinIO Parquet flush).
4. **VALIDATE MVP**: Run `make simulate-telemetry` followed by `artemis pipeline run mqtt_to_minio`.

### Incremental Delivery

1. **Sprint 1 (MVP)**: Setup + Foundational + User Story 1 (Data Ingestion & Storage).
2. **Sprint 2 (Analytics)**: User Story 2 (DuckDB SQL analytics directly on MinIO Parquet).
3. **Sprint 3 (Intelligence & OSINT)**: User Story 3 (Memgraph knowledge graph + OSINT import + Google AI Studio RAG).
4. **Sprint 4 (Harden)**: Phase 6 (End-to-end quickstart validation, VERSION tag, documentation).
