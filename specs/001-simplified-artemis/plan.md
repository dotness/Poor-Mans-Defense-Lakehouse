# Implementation Plan: Simplified Artemis

**Branch**: `001-simplified-artemis` | **Date**: 2026-09-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-simplified-artemis/spec.md`

---

## Summary

Simplified Artemis is a sovereign Big Data Lakehouse and AI infostructure engineered to run reliably on a single Linux Virtual Machine (16–32 GB RAM, CPU-only). It adapts the architectural vision of the French military ARTEMIS.IA program while eliminating heavy JVM-based enterprise dependencies (Kafka, Spark, Hadoop, Neo4j, OpenCTI). In their place, it deploys ultra-lightweight C++, Go, and Rust services (DuckDB, MinIO, Mosquitto, Memgraph, PostgreSQL, Redis) orchestrated via a unified Python CLI (`artemis`) and offloads large-scale generative AI reasoning to the Google AI Studio external API.

---

## Technical Context

**Language/Version**: Python 3.11+ (CLI, pipeline orchestration, ingestion buffers, Google GenAI SDK)

**Primary Dependencies**:
- Container Runtimes: Docker & Docker Compose v2
- Ingestion & Streaming: Mosquitto (MQTT 3.1.1/5.0)
- Lakehouse & Analytics: MinIO (S3-compatible Object Storage), DuckDB (v1.1+ with `httpfs` extension)
- Graph Intelligence: Memgraph (openCypher / Bolt C++ engine)
- Relational State & Cache: PostgreSQL 16, Redis 7
- Security & Gateway: Traefik v3 (reverse proxy with TLS/mTLS), Authelia
- AI SDK: `google-genai` Python client library

**Storage**:
- `s3://telemetry/`: Parquet columnar objects partitioned by year/month/day
- `/var/lib/memgraph/`: Graph snapshots and WAL
- `/var/lib/postgresql/data/`: Relational pipeline and AI query audit logs
- `/var/log/artemis/buffer/`: Ephemeral local NVMe ingestion disk buffer

**Testing**: `pytest`, `pytest-docker` / `testcontainers-python`, `pytest-asyncio`

**Target Platform**: Single Linux Virtual Machine (16–32 GB RAM, 4–8 vCPUs, NVMe storage, CPU-only)

**Project Type**: Big Data Platform (Infrastructure-as-Code, Docker Compose Services, Python Orchestration CLI)

**Performance Goals**:
- < 5s query response time on 10 GB Parquet datasets via DuckDB
- Ingest >= 10,000 events/sec via Mosquitto and disk buffer
- Idle RAM footprint <= 12 GB across all running containers

**Constraints**:
- Single commodity VM with no dedicated GPU hardware
- Acceptable in-flight event loss on sudden VM reboot to prioritize ingest throughput over distributed ACID consensus
- External API calls to Google AI Studio governed by Redis caching and rate-limiting

**Scale/Scope**: Multi-sensor edge telemetry ingestion, multi-analyst concurrent queries, unified knowledge graph, natural language intelligence RAG.

---

## Constitution Check

*GATE: Passed in Phase 0 research. Re-evaluated post-design in Phase 1.*

- **Library-First**: Platform functions are modularized into distinct, testable packages (`src/cli/`, `src/services/`, `src/pipelines/`).
- **CLI Interface**: A unified command-line tool `artemis` handles health status, DuckDB analytics, pipeline runs, and AI queries (defined in [`contracts/cli_interface.md`](contracts/cli_interface.md)).
- **Test-First**: Automated integration test suites (`tests/integration/`) are designed prior to code delivery, validating the end-to-end ingestion and query path.
- **Integration Testing**: Explicit verification across Docker container boundaries (Mosquitto → MinIO → DuckDB → Memgraph → Google AI Studio).

---

## Project Structure

### Documentation (`specs/001-simplified-artemis/`)

```text
specs/001-simplified-artemis/
├── spec.md                     # Feature specification with functional requirements
├── plan.md                     # This implementation plan
├── research.md                 # Phase 0 architectural decisions and trade-offs
├── data-model.md               # Phase 1 domain entities, schemas, and lifecycles
├── quickstart.md               # Phase 1 end-to-end validation scenarios
├── checklists/
│   └── requirements.md         # Specification quality gate checklist
└── contracts/
    ├── mqtt_telemetry.md       # Edge ingestion message contract
    └── cli_interface.md        # Artemis CLI contract
```

### Source Code (`repository root`)

```text
docker-compose.yml              # Multi-container service definitions
Makefile                        # Lifecycle and benchmark tasks
pyproject.toml                  # Python package and dependency configuration
src/
├── cli/                        # Unified 'artemis' CLI implementation
│   ├── main.py
│   └── commands/
│       ├── status.py
│       ├── query.py
│       ├── ask.py
│       └── pipeline.py
├── config/                     # Service configs (Mosquitto, Traefik, MinIO init)
│   ├── mosquitto.conf
│   ├── traefik.yml
│   ├── auth.yml
│   └── postgres_init.sql
├── services/                   # Core business logic
│   ├── ingestion/              # MQTT listener & disk buffer worker
│   ├── analytics/              # DuckDB engine wrapper with S3 httpfs
│   ├── graph/                  # Memgraph driver and Cypher query builder
│   │   ├── memgraph_client.py
│   │   └── osint_importer.py   # SpiderFoot scan export parser
│   └── ai/                     # Google AI Studio client with Redis caching
└── pipelines/                  # Batch ETL tasks (e.g. buffer to MinIO Parquet)
    └── mqtt_to_minio.py

tests/
├── conftest.py
├── contract/                   # Schema validation tests
│   ├── test_mqtt_contract.py
│   └── test_osint_import.py
├── integration/                # End-to-end multi-service tests
│   ├── test_ingestion_pipeline.py
│   ├── test_analytics_query.py
│   └── test_ai_correlation.py
└── unit/                       # Unit tests for CLI and helpers
    └── test_cli_parsing.py
```

**Structure Decision**: Single repository incorporating Infrastructure-as-Code (Docker Compose) and a modular Python CLI/service library (`src/`) with integration test harnesses (`tests/`).

---

## Complexity Tracking

| Decision | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Multi-container Docker Compose setup | Isolates memory and process lifecycle of C++, Go, and Python runtimes (Mosquitto, MinIO, Memgraph, Postgres) | Monolithic single process would require complex process supervisors and make debugging/swapping components fragile |
| Ingestion disk-buffer layer | Decouples high-frequency MQTT arrival from batch Parquet object writes | Writing individual MQTT events directly to MinIO causes millions of tiny files and saturates S3 metadata APIs |
| External Google AI Studio API | Eliminates the need for 16-48GB GPU VRAM or local CPU model execution | Hosting LLMs locally on a 16-32GB CPU VM starves memory from the lakehouse databases and drops ingestion throughput |
