# Poor Man's Defense Lakehouse

**Sovereign Big Data Lakehouse & AI Infostructure on a Single Linux VM**

> **Legal Disclaimer**: *This repository is an independent, non-commercial, open-source educational prototype and architectural exercise. It is not affiliated with, endorsed by, sponsored by, or connected to the French Republic, the French Ministry of Armed Forces (Ministère des Armées), the DGA, ATHEA, Thales, Atos, or any of their affiliates. "ARTEMIS.IA" and associated program names are referenced strictly for educational comparison based exclusively on publicly available sources. Reference: Emmanuel & Robin, *Revue Défense Nationale* — https://doi.org/10.3917/rdna.820.0093*

---

## 🏛️ Executive Summary

**Poor Man's Defense Lakehouse** is an ultra-lean, sovereign data platform engineered to operate autonomously on a single commodity Linux Virtual Machine (16–32 GB RAM, CPU-only). It achieves high-throughput telemetry ingestion, columnar analytics, knowledge graph correlation, and generative AI query assistance with **zero JVM overhead**.

By replacing heavyweight Java/JVM distributed frameworks (Kafka, Spark, Hadoop, OpenCTI, Neo4j) with high-efficiency native C/C++ and Go services, the platform keeps its complete idle memory footprint under **12 GB RAM**, leaving ample headroom for OS caches and operational workloads.

---

## 🏗️ Architecture & Technology Stack

```
+-------------------------------------------------------------------------+
|                    TRAEFIK REVERSE PROXY & GATEWAY                      |
|                  (Ports 80/443/8080 - HTTP Basic Auth)                  |
+-------------------------------------------------------------------------+
       |                         |                       |
       v                         v                       v
+----------------+      +------------------+    +------------------+
|   MOSQUITTO    |      |      MinIO       |    |     MEMGRAPH     |
|  (C MQTT 1883) |      | (Go S3 Storage)  |    |  (C++ Graph Bolt)|
| Ingestion Bus  |      | Columnar Parquet |    | Knowledge Graph  |
+----------------+      +------------------+    +------------------+
       |                         ^                       ^
       v                         |                       |
[Local Disk Buffer] ---> [Batch Flush Pipeline]          |
(/tmp/artemis/buffer)            |                       |
                                 v                       v
                        +------------------+    +------------------+
                        |      DUCKDB      |    | Google AI Studio |
                        | (C++ In-Memory)  |    | External API RAG |
                        | Analytics Engine |    |  (gemini-flash)  |
                        +------------------+    +------------------+
                                 |                       |
                                 +-----------+-----------+
                                             |
                                 +-----------v-----------+
                                 |  POSTGRESQL & REDIS   |
                                 |  State, Audit, Cache  |
                                 +-----------------------+
```

### Component Roster (Zero JVM)

| Tier | Technology | Language | Replaced JVM Tool | Role & Justification |
|---|---|---|---|---|
| **Ingestion Bus** | **Eclipse Mosquitto** | C | Apache Kafka | Ultra-low memory (< 20MB idle) MQTT broker handling 1,000+ evt/s. |
| **Lakehouse Storage** | **MinIO** | Go | Hadoop HDFS | S3-compatible, single-binary object storage with multi-gigabyte Parquet objects. |
| **Vectorized Analytics** | **DuckDB** | C++ | Apache Spark / Trino | Embedded columnar engine executing complex analytical queries directly on S3 Parquet in < 5s. |
| **Knowledge Graph** | **Memgraph** | C++ | Neo4j | Ultra-fast in-memory graph database with openCypher interface and Bolt protocol. |
| **Edge Router & Auth** | **Traefik v3** | Go | Keycloak / Kong | Dynamic reverse proxy with automated TLS, rate limiting, and HTTP Basic Auth. |
| **Operational State** | **PostgreSQL 16** | C | MySQL / Cassandra | Lightweight metadata store for pipeline state and AI interaction audit logs. |
| **Semantic Cache** | **Redis 7** | C | Hazelcast / Ignite | In-memory key-value store for 1-hour query caching and analyst rate limiting. |
| **Generative AI** | **Google AI Studio** | Cloud API | Local Ollama/vLLM | Offloads LLM inference to `gemini-2.5-flash` API to preserve local VM CPU and RAM. |

---

## ⚡ Getting Started

### Prerequisites

- Linux VM (Ubuntu 22.04+ recommended) with 16–32 GB RAM (CPU-only supported).
- Docker and Docker Compose (v2.20+).
- Python 3.11+ and GNU `make`.
- Google AI Studio API key (obtain from [Google AI Studio](https://aistudio.google.com/)).

### Platform Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/dotness/poor-mans-defense-lakehouse.git
   cd poor-mans-defense-lakehouse
   ```

2. **Initialize configuration:**
   ```bash
   make setup
   # Edit .env and enter your GOOGLE_AI_STUDIO_API_KEY
   ```

3. **Launch service containers:**
   ```bash
   make up
   ```

4. **Verify platform health:**
   ```bash
   make status
   # or: artemis status
   ```

---

## 💻 CLI Reference (`artemis`)

Artemis includes a unified command-line tool installed into your Python environment:

```bash
# Check service health and memory consumption
artemis status
artemis status --json

# Execute DuckDB vectorized SQL analytics over MinIO Parquet files
artemis query --sql "SELECT metric, AVG(value), COUNT(*) FROM read_parquet('s3://telemetry/*.parquet') GROUP BY metric"
artemis query --sql "SELECT * FROM read_parquet('s3://telemetry/*.parquet') LIMIT 5" --format json

# Submit natural language questions augmented with Memgraph graph context
artemis ask "What are the common IP addresses associated with recent anomalies?"
artemis ask "Show threat actors targeting c2-controller.darknet.org" --json

# Trigger batch data processing pipelines
artemis pipeline run mqtt_to_minio

# ---------------------------------------------------------
# Projects & Custom Sandboxed Data Pipelines (Feature 004)
# ---------------------------------------------------------

# Create and manage isolated multi-tier projects
artemis project create --project-id alpha-corp --name "Alpha Corporation Telemetry"
artemis project list
artemis project info alpha-corp

# Ingest heterogeneous tabular (CSV/JSON/Parquet) and graph (JSON/OSINT) data into bronze/silver/gold
artemis project ingest alpha-corp --file ./data/raw_metrics.csv --dataset system_stats --tier BRONZE
artemis project ingest-graph alpha-corp --file ./data/threat_graph.json --dataset threat_intel

# Register and version custom Python processing scripts
artemis project pipeline create alpha-corp \
  --pipeline-id clean-metrics \
  --name "Clean Bronze to Silver Metrics" \
  --script ./scripts/clean.py \
  --input-tier BRONZE \
  --output-tier SILVER

artemis project pipeline list alpha-corp

# Execute custom processing scripts in an ephemeral, resource-bounded Docker sandbox (or --mock)
artemis project pipeline run alpha-corp clean-metrics --dataset system_stats
artemis project pipeline runs alpha-corp

# Query project data partitions with DuckDB S3 prefix confinement
artemis project query alpha-corp \
  --sql "SELECT device_id, AVG(cpu_usage) FROM read_parquet('s3://telemetry/projects/alpha-corp/bronze/**/*.parquet') GROUP BY device_id"

# ---------------------------------------------------------
# Dataset & Query Data TTL Retention & Auto-Cleanup (Feature 009)
# ---------------------------------------------------------

# Configure dataset TTL policy (ingestion age or event-timestamp column granularity)
artemis project ttl set --project alpha-corp --dataset system_stats --tier bronze --ttl 30d
artemis project ttl set --project alpha-corp --dataset system_stats --tier bronze --ttl 7d --granularity TIMESTAMP_COLUMN --timestamp-column timestamp

# Inspect dataset TTL state, project summary, and configure tier/query-data defaults
artemis project ttl get --project alpha-corp --dataset system_stats --tier bronze
artemis project ttl summary --project alpha-corp
artemis project ttl set-default --project alpha-corp --scope QUERY_DATA --artifact-type MATERIALIZED_EXPORT --ttl 14d

# Place/release investigative Retention Holds and restore soft-deleted datasets during grace period
artemis project ttl hold --project alpha-corp --dataset system_stats --reason "Incident review"
artemis project ttl unhold --project alpha-corp --dataset system_stats
artemis project ttl restore --project alpha-corp --dataset system_stats --ttl 60d

# Preview (--dry-run) or execute two-stage TTL auto-cleanup and view audit history
artemis project ttl cleanup --project alpha-corp --dry-run
artemis project ttl cleanup --project alpha-corp
artemis project ttl history --project alpha-corp
```

> **Detailed Architecture & Flow**: For a detailed breakdown with sequence and data flow diagrams of `artemis ask`, see [AI RAG Scenario Deep Dive](docs/architecture/ai_rag_scenario.md).

---

## 🛠️ End-to-End Validation Scenarios

### Scenario 1: High-Frequency Telemetry Ingestion & Analytics
Simulate 10,000 edge telemetry events, flush from local disk buffer into MinIO Parquet, and run SQL analytics:

```bash
# 1. Publish 10,000 synthetic events at 1,000 evt/s
make simulate-telemetry

# 2. Flush disk buffer to partitioned MinIO Parquet
make trigger-pipeline

# 3. Query analytical aggregations with DuckDB
make query-analytics
```

### Scenario 2: Knowledge Graph Correlation & AI Analysis
Seed threat intelligence nodes into Memgraph and ask contextual intelligence questions:

```bash
# 1. Seed sample intelligence nodes and incident edges
make seed-graph

# 2. Ask natural language question (grounded in graph context)
artemis ask "What are the common IP addresses associated with recent anomalies?"
```

---

## 🧪 Automated Testing

Execute the complete test suite (contract tests, unit tests, integration tests):

```bash
make test
```

Test coverage includes:
- `tests/contract/test_mqtt_contract.py`: MQTT telemetry payload validation and schema constraints.
- `tests/contract/test_osint_import.py`: SpiderFoot OSINT export parser and node/edge extraction.
- `tests/integration/test_ingestion_pipeline.py`: Edge buffering, batch rotation, and Parquet serialization.
- `tests/integration/test_analytics_query.py`: DuckDB SQL execution and output formatters (`table`, `json`, `csv`).
- `tests/integration/test_ai_correlation.py`: Memgraph entity retrieval, Redis semantic cache, and Google GenAI RAG.

---

## 🧹 Platform Teardown & Reset

```bash
# Stop all platform containers (preserves volume data)
make down

# Clean stop: wipes all persistent volumes and local buffers for pristine reset
make clean
```

---

## 📚 Interactive Explorers & Deep-Dive Documentation

### 🌐 Interactive HTML5 Explorers
- **System & 8-Domain Architecture Command Center**: [docs/index.html](docs/index.html) – Interactive Zero-JVM topology, 8 domain facades, RAM budget calculator, and searchable catalog of all 34 REST endpoints & CLI commands.
- **Interactive End-to-End Flow Simulator**: [docs/interactive/system_flows.html](docs/interactive/system_flows.html) – Step-by-step packet and sequence animator for all 5 core operational flows (MQTT-to-Parquet, 6-tool AI agent loop, Medallion Docker sandbox, 2-phase KDG indexing, and Fail-Fast vs. Pytest mock harness).
- **Interactive KDG & Zero-Trust Confinement Sandbox**: [docs/interactive/knowledge_discovery_explorer.html](docs/interactive/knowledge_discovery_explorer.html) – Interactive KDG ontology graph, caller RBAC switcher (`alice`, `bob`, `eve`, `admin`), cross-project `SAME_AS` entity search, lineage DAG, and regex `PatternProfiler` tester.

### 📐 Markdown Architecture Guides ([docs/README.md](docs/README.md))
- **Microservice Domain Architecture**: [docs/architecture/microservice_domain_architecture.md](docs/architecture/microservice_domain_architecture.md) – Hexagonal domain-driven architecture, 9 core domain facades, 46 REST API routes, Temporal workflows, and Google ADK agent reasoning.
- **Dataset & Query Data TTL Retention Guide**: [docs/architecture/dataset_ttl_and_cleanup.md](docs/architecture/dataset_ttl_and_cleanup.md) – 4-tier TTL policy hierarchy, per-file ingestion clocks vs. `TIMESTAMP_COLUMN` row granularity, transparent SQL/Cypher read-time interception, source-aware cache invalidation, two-stage `SOFT_DELETED` grace period with single-pass Parquet compaction, reference-counted Memgraph entity pruning, and `:LineageTombstone` provenance preservation.
- **Knowledge Discovery Graph Guide**: [docs/architecture/knowledge_discovery_graph_guide.md](docs/architecture/knowledge_discovery_graph_guide.md) – Universal domain-agnostic knowledge discovery graph, membership model, automated structural indexing, and federated entity resolution.
- **Project Data Pipelines Guide**: [docs/architecture/project_data_pipelines.md](docs/architecture/project_data_pipelines.md) – Multi-tier Medallion architecture (Bronze/Silver/Gold), ephemeral Docker runner sandboxing, Python AST script validation, and scoped DuckDB partition querying.
- **Data Ingestion Guide**: [docs/architecture/data_ingestion_guide.md](docs/architecture/data_ingestion_guide.md) – Step-by-step architecture, code paths, crash recovery, and flow diagrams for MQTT telemetry buffering, SpiderFoot OSINT graph ingestion, and project-scoped ingestion.
- **AI RAG Flow Guide**: [docs/architecture/ai_rag_scenario.md](docs/architecture/ai_rag_scenario.md) – End-to-end execution breakdown of `artemis ask` with 6-tool autonomous agent loop, read-only SQL/Cypher guardrails, and Gemini 2.5 Flash synthesis.
- **Google AI Studio Integration**: [docs/architecture/google_ai_studio_integration.md](docs/architecture/google_ai_studio_integration.md) – Rationale for offloading inference, fail-fast production exceptions, and offline test doubles.
- **Clean Production Architecture & Testing Harness**: [docs/architecture/clean_architecture_and_testing.md](docs/architecture/clean_architecture_and_testing.md) – Zero-mock production core (`src/`), typed domain exceptions (`src/core/exceptions.py`), and reusable pytest fixtures (`tests/fixtures/mocks/`).

---

## 📄 License & Versioning

- **Version**: `0.2.0` (see [VERSION](VERSION))
- **Specification**: [specs/001-simplified-artemis/](specs/001-simplified-artemis/)