# Research & Technical Decisions: Simplified Artemis

This document consolidates Phase 0 technical research, architectural evaluations, and decisions for the Simplified Artemis platform.

---

## 1. Orchestration & Language Runtime

**Decision:** Python 3.11+

**Rationale:** While data ingestion, storage, and graph operations are delegated to compiled C++/Rust/Go binaries (Mosquitto, MinIO, DuckDB, Memgraph), the management CLI, orchestration glue, and AI integration require an expressive, standard runtime. Python 3.11+ offers optimal developer velocity and low runtime overhead when confined to CLI and API wrappers.

**Alternatives Considered:**
- **Go**: High concurrency and single-binary deployment, but lacks first-class data engineering libraries (e.g. pyarrow, duckdb extensions) and native Google GenAI SDK support.
- **Rust**: High performance and low memory footprint, but slower iteration for pipeline definitions and CLI wrappers.

---

## 2. Ingestion & Streaming Buffer

**Decision:** Mosquitto (MQTT) broker backed by a local disk-buffered ingestion worker (with fallback path for NATS JetStream / Redpanda).

**Rationale:** Edge devices and tactical sensors standardly support MQTT with minimal overhead. Mosquitto consumes less than 15MB of RAM at idle and handles tens of thousands of messages per second. Ingestion bursts are buffered to local NVMe disk via an asynchronous writer before being batched into columnar Parquet files, providing backpressure without JVM heap exhaustion.

**Alternatives Considered:**
- **Apache Kafka**: The enterprise military standard, but requires massive JVM memory pre-allocation (>2-4GB minimum) and ZooKeeper/KRaft complexity that oversubscribes a single VM.
- **RabbitMQ**: Erlang runtime requires substantial baseline memory and complex clustering not needed on a single node.

---

## 3. Storage & Analytical Query Engine

**Decision:** MinIO (S3-compatible Object Storage) + DuckDB (embedded columnar query engine).

**Rationale:** 
- MinIO provides robust, multi-tenant S3-compliant object storage with a tiny Go footprint (~100-150MB).
- DuckDB operates as an in-process, vectorized analytical SQL engine that directly reads and queries Parquet files in MinIO using the `httpfs` extension with zero JVM footprint. Analytical queries on multi-gigabyte datasets execute in sub-second to low-second times directly within available host RAM.

**Alternatives Considered:**
- **Apache Spark / Trino**: Require dedicated multi-node clusters or heavy JVM worker daemons that exceed the single-VM 16-32GB budget.
- **ClickHouse**: Exceptional speed, but runs as a heavier daemon requiring continuous background memory and disk management compared to DuckDB's embedded model.

---

## 4. Graph Database & Intelligence Correlation

**Decision:** Memgraph (in-memory C++ graph database).

**Rationale:** Memgraph is written entirely in C++, supports openCypher, and is 100% compatible with Bolt drivers while using a fraction of the memory that Neo4j demands. It can run in transactional mode or in-memory snapshot mode, fitting comfortably within a 200MB–1GB footprint.

**Alternatives Considered:**
- **Neo4j**: Standard in military intelligence stacks, but JVM memory demands (heap + pagecache pre-allocations) quickly consume 4–8GB of RAM.
- **NetworkX (In-Python)**: Memory-inefficient for large graphs and lacks concurrent Cypher querying.

---

## 5. AI Inference & Correlation Integration

**Decision:** External Google AI Studio API (`google-genai` SDK) with Redis semantic caching and rate-limiting.

**Rationale:** Local LLMs (e.g. 70B models or heavy 8B quantized models) require dedicated GPU VRAM (16–48GB) or consume almost the entire 32GB system RAM if run via CPU AVX2, starving database and ingestion services. Using Google AI Studio eliminates GPU requirements and local RAM overhead entirely. Redis serves as an in-memory cache to prevent redundant queries and avoid exceeding API rate limits.

**Alternatives Considered:**
- **Local Ollama / Llama.cpp**: Viable for 3B/7B models on CPU, but severely slows down when concurrent queries occur and consumes 4–8GB of scarce RAM.
- **Self-hosted vLLM/TGI**: Mandates an NVIDIA GPU server, conflicting with single-VM commodity CPU hardware constraints.

---

## 6. Centralized Access & Reverse Proxy

**Decision:** Traefik + Authelia / Basic Auth.

**Rationale:** Traefik provides a lightweight Go-based reverse proxy that natively handles TLS termination, mutual TLS (mTLS) for edge sensors, and path routing. Authelia provides lightweight, zero-trust SSO and header-based authentication without requiring a heavy Keycloak (Java) deployment.

**Alternatives Considered:**
- **Keycloak**: Excellent feature set but requires a full Quarkus/JVM stack consuming 1-2GB of idle memory.
- **Nginx**: Fast and low footprint, but dynamic service discovery and TLS certificate management requires manual script maintenance compared to Traefik.

---

## 7. Testing Strategy

**Decision:** `pytest` with `pytest-docker` / `testcontainers-python` for integration testing.

**Rationale:** Since Simplified Artemis is an integrated composition of Docker services, traditional isolated unit tests are insufficient. Integration tests spinning up temporary containers verify the entire data lifecycle: MQTT ingest → buffer → MinIO Parquet → DuckDB SQL verification → Memgraph entity validation.
