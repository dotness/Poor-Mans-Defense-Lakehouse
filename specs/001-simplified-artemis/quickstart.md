# Quickstart: Simplified Artemis Validation

This guide provides end-to-end validation steps to prove that the core functionality of the Simplified Artemis platform functions as specified.

## Prerequisites

- Linux host with 16–32 GB RAM (CPU-only is supported)
- Docker and Docker Compose (v2.20+)
- Python 3.11+ and `make` installed
- Google AI Studio API key (configured in environment)

## Related Design Documents

- [Data Model](data-model.md): Schema definitions for Telemetry, Graph Nodes, Pipelines, and AI Queries
- [MQTT Telemetry Contract](contracts/mqtt_telemetry.md): Edge device ingestion payload specification
- [CLI Interface Contract](contracts/cli_interface.md): Commands, arguments, outputs, and exit codes

---

## Setup

1. **Configure Environment:**
   Copy the example environment template and configure your API key:
   ```bash
   cp .env.example .env
   # Set GOOGLE_AI_STUDIO_API_KEY="your_api_key_here"
   ```

2. **Start the Platform:**
   Bring up the service stack using Docker Compose:
   ```bash
   make up
   ```
   *Expected outcome*: Mosquitto, MinIO, Memgraph, PostgreSQL, Redis, and Traefik start up healthy with idle memory < 12 GB.
   Verify with:
   ```bash
   artemis status
   ```

---

## Scenario 1: High-Frequency Telemetry Ingestion & Analytics (User Stories 1 & 2)

**Goal**: Ingest simulated high-frequency telemetry via MQTT, batch into Parquet on MinIO, and execute sub-second DuckDB analytics.

1. **Run Ingestion Simulator:**
   Publishes 1,000 events/second conforming to the [MQTT Telemetry Contract](contracts/mqtt_telemetry.md) for 10 seconds:
   ```bash
   make simulate-telemetry
   ```
   *Expected outcome*: 10,000 events published without dropped connections or socket timeouts.

2. **Trigger Batch Flush Pipeline:**
   Flushes disk-buffered MQTT events into columnar Parquet files on MinIO:
   ```bash
   artemis pipeline run mqtt_to_minio
   ```
   *Expected outcome*: Pipeline completes with exit code 0; new Parquet object created under `s3://telemetry/`.

3. **Execute Analytical Query:**
   Query analytical metrics directly over MinIO Parquet files with DuckDB:
   ```bash
   artemis query --sql "SELECT metric, AVG(value) AS avg_val, COUNT(*) AS total_samples FROM read_parquet('s3://telemetry/*.parquet') GROUP BY metric"
   ```
   *Expected outcome*: Formatted tabular output returned in under 5 seconds.

---

## Scenario 2: Intelligence Correlation & AI Query (User Story 3)

**Goal**: Verify graph query context retrieval from Memgraph and natural language correlation via Google AI Studio.

1. **Seed Graph Intelligence Nodes:**
   Seed synthetic IP addresses, domains, and incident relationships into Memgraph:
   ```bash
   make seed-graph
   ```
   *Expected outcome*: Nodes and edges created in Memgraph (verify in Memgraph Lab UI at `http://localhost:3000`).

2. **Ask the Intelligence Assistant:**
   Execute a natural language query via the CLI:
   ```bash
   artemis ask "What are the common IP addresses associated with recent anomalies?"
   ```
   *Expected outcome*:
   - Graph context is retrieved from Memgraph.
   - Grounded context is dispatched to Google AI Studio.
   - Natural language response is returned to stdout.
   - Interaction is logged to the PostgreSQL `ai_queries` audit table.

---

## Teardown

To stop all platform containers while retaining volume data:
```bash
make down
```

To wipe all data volumes for a pristine reset:
```bash
make clean
```
