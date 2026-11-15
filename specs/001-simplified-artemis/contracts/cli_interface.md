# Artemis CLI Interface Contract

This contract defines the command-line interface for the `artemis` platform management and analytics CLI.

## Global Options

- `--config PATH`: Path to platform configuration file (default: `/etc/artemis/config.yaml` or `./src/config/config.yaml`).
- `--json`: Output results formatted as JSON for machine consumption / scripting.
- `--verbose`: Enable debug-level logging to stderr.

---

## Commands

### 1. `artemis status`

Checks health and operational status of all platform services.

- **Synopsis**: `artemis status [--json]`
- **Output (Human-readable)**:
  ```text
  Service            Status    Uptime    Memory Usage
  ---------------------------------------------------
  traefik            HEALTHY   1h 12m    28MB
  mosquitto          HEALTHY   1h 12m    12MB
  minio              HEALTHY   1h 12m    124MB
  memgraph           HEALTHY   1h 12m    180MB
  postgres           HEALTHY   1h 12m    85MB
  redis              HEALTHY   1h 12m    18MB
  ---------------------------------------------------
  Total VM Memory Consumption: ~447MB (Idle Budget: < 12GB)
  ```
- **Output (JSON)**:
  ```json
  {
    "status": "HEALTHY",
    "services": {
      "mosquitto": {"status": "HEALTHY", "memory_mb": 12},
      "minio": {"status": "HEALTHY", "memory_mb": 124},
      "memgraph": {"status": "HEALTHY", "memory_mb": 180},
      "postgres": {"status": "HEALTHY", "memory_mb": 85}
    }
  }
  ```

---

### 2. `artemis query`

Executes analytical SQL queries via embedded DuckDB against Parquet files in MinIO.

- **Synopsis**: `artemis query --sql "<SQL_QUERY>" [--format table|json|csv]`
- **Arguments**:
  - `--sql` (String, Required): Valid DuckDB SQL query string.
  - `--format` (String, Optional, Default: `table`): Output format.
- **Example**:
  ```bash
  artemis query --sql "SELECT metric, AVG(value) FROM read_parquet('s3://telemetry/*.parquet') GROUP BY metric"
  ```
- **Exit Codes**:
  - `0`: Query successful.
  - `1`: Invalid query syntax or file access error.
  - `2`: Connection/S3 authentication error.

---

### 3. `artemis ask`

Submits a natural language intelligence question to Google AI Studio, grounded with knowledge graph context from Memgraph.

- **Synopsis**: `artemis ask "<NATURAL_LANGUAGE_PROMPT>"`
- **Arguments**:
  - `prompt` (Positional String, Required): Intelligence question.
- **Behavior**:
  1. Queries Memgraph for matching entities and relationships related to tokens in the prompt.
  2. Synthesizes a structured RAG prompt with graph context and system constraints.
  3. Sends request to Google AI Studio external API.
  4. Records the query and response in PostgreSQL `ai_queries` audit log.
- **Example**:
  ```bash
  artemis ask "What are the common IP addresses associated with recent anomalies?"
  ```
- **Exit Codes**:
  - `0`: Successful AI inference response.
  - `1`: External API rate limit or quota error.
  - `2`: Graph database context retrieval failure.

---

### 4. `artemis pipeline`

Manages and triggers batch ETL and processing pipelines (e.g. MQTT buffer flush to MinIO Parquet).

- **Synopsis**: `artemis pipeline run <PIPELINE_NAME>`
- **Example**:
  ```bash
  artemis pipeline run mqtt_to_minio
  ```
