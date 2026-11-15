# Technology Stack: Simplified Artemis.IA

## Goal: Fully functional sovereign Big Data Lakehouse and AI infostructure on a single VM

This document defines the unified technology stack for the Simplified Artemis.IA local deployment. It discards the multi-domain enterprise segments (Arcadia, SIRCID, Escrim) and focuses entirely on the practical reality of running a sovereign AI and Data Lakehouse on a single Virtual Machine (16-32GB RAM). 

To achieve this, the architecture strictly eliminates JVM-based enterprise systems in favor of highly optimized C++, Go, and Rust tooling.

---

## 🏗️ Unified Technology Stack

### 1. Data Ingestion & Streaming
*   **Redpanda**: High-performance, C++ based message broker (replaces Apache Kafka).
*   **NATS JetStream**: Ultra-lightweight streaming and pub/sub.
*   **Telegraf & Mosquitto (MQTT)**: IoT telemetry ingestion.

### 2. Data Storage & Lakehouse Compute
*   **MinIO**: High-performance S3-compatible object storage. Tuned for Host NVMe and configured with `URL_STYLE 'path'` to avoid Docker DNS issues.
*   **DuckDB & Polars**: In-memory analytical SQL and Rust-based DataFrames operating directly on Parquet files via `httpfs` (replaces Apache Spark and Hadoop).
*   **PostgreSQL & PgBouncer**: Core relational state and connection pooling.
*   **Redis**: In-memory key-value store for caching and session state.
*   **InfluxDB**: Time-series database for telemetry and hardware metrics.

### 3. AI, Graph & Intelligence Correlation
*   **Google AI Studio (External API)**: Offloaded LLM inference and RAG via `google-genai` SDK with Redis semantic caching, eliminating GPU hardware requirements and local RAM starvation on commodity CPU VMs.
*   **Memgraph**: In-memory C++ graph database for intelligence correlation (replaces Neo4j).
*   **SpiderFoot (Standalone)**: Python-based automated OSINT collection and footprinting (replaces OpenCTI) with manual import/export integration to Memgraph.

### 4. Orchestration, Security & Networking
*   **Kestra / Dagster**: Modern data orchestration pipelines (replaces Apache Airflow).
*   **Traefik & Basic Auth / Authelia**: Reverse proxy with TLS/mTLS and lightweight authentication middleware, eliminating heavy Java/Quarkus Identity Providers (e.g. Keycloak).
*   **NetBird & Coturn (STUN/TURN)**: Decentralized WireGuard VPN mesh for secure edge connectivity (optional extension).

---

## 🚫 Eliminated Technologies (False Cones)
The following technologies were explicitly rejected from the stack to protect the 16-32GB memory budget of the single VM:

*   **Neo4j (JVM Server)**: The industry standard for graph DBs, but requires massive JVM memory pre-allocation. Replaced by Memgraph.
*   **OpenCTI (Enterprise CTI)**: Mandates a massive underlying stack (OpenSearch, RabbitMQ, Redis) that consumes 16GB of RAM at idle. Replaced by standalone SpiderFoot.
*   **Apache Ecosystem (Hadoop/Spark/Kafka/Airflow)**: The JVM overhead for scheduling and garbage collection is lethal to a single VM. Replaced by DuckDB, Polars, Redpanda, and Kestra.
