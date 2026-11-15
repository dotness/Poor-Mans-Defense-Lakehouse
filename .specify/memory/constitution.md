# Poor Man's Defense Lakehouse Constitution

## Core Principles

### I. Library-First & Modular Architecture
Every platform capability (ingestion, analytics, graph correlation, AI interaction) MUST start as a self-contained, modular service or Python package with clear interface contracts. No monolithic coupling that impedes testing or independent container lifecycle management.

### II. Unified CLI Interface
Every platform service MUST expose management, inspection, and execution capabilities via the unified `artemis` CLI. The CLI MUST follow standard UNIX text in/out conventions: stdout for formatted results, stderr for errors, and support `--json` flags for automation and machine consumption.

### III. Test-First & Integration Rigor
Integration and contract testing are NON-NEGOTIABLE. Before code delivery, interface contracts (e.g. MQTT payload schemas, CLI specifications) MUST have contract tests written. Integration tests (`tests/integration/`) MUST verify end-to-end data flow across container boundaries (Mosquitto → MinIO → DuckDB → Memgraph → Google AI Studio).

### IV. Resource Constraint & Zero-JVM Sovereignty
The platform MUST run on a single Linux Virtual Machine (16–32 GB RAM, CPU-only). To prevent out-of-memory exhaustion and unpredictable latency, enterprise JVM-based engines (Apache Spark, Kafka, Hadoop, Neo4j, OpenCTI, Keycloak) are strictly eliminated. All core data engines MUST be compiled C++, Rust, or Go binaries (DuckDB, MinIO, Mosquitto, Memgraph). Large-scale generative AI reasoning is offloaded externally to the Google AI Studio API with local Redis caching.

---

## Operating Constraints & Performance Standards

- **Memory Budget**: Total idle memory across all platform services MUST remain under 12 GB.
- **Ingestion Throughput**: Must sustain >= 10,000 events/sec via MQTT without event loss.
- **Analytical Latency**: DuckDB analytical queries over 10 GB Parquet datasets on MinIO MUST return in < 5 seconds.
- **Security & Networking**: All analyst and edge traffic MUST traverse a secure reverse proxy (Traefik) enforcing HTTPS/mTLS and lightweight authentication middleware.

---

## Development Workflow & Quality Gates

1. **Specification Before Code**: Requirements must be captured in `spec.md`, evaluated via `/speckit-plan`, and decomposed into `/speckit-tasks` prior to implementation.
2. **Quality Gates**: All automated tests must pass (`make test`), and quickstart scenarios (`quickstart.md`) must execute cleanly without manual workarounds.
3. **Traceability**: Every task and commit must trace back to a prioritized user story or setup phase.

---

## Governance

This Constitution supersedes all informal practices and serves as the non-negotiable benchmark for all PRs and architectural additions. Any violation of these principles (e.g., introducing JVM daemons or unbudgeted GPU dependencies) is automatically considered CRITICAL and will be rejected.

**Version**: 1.0.0 | **Ratified**: 2026-09-04 | **Last Amended**: 2026-09-04
