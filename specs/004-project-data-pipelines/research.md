# Research & Architecture Decisions: Project-Scoped Data Ingestion & Medallion Pipelines

**Feature**: `004-project-data-pipelines` | **Date**: 2026-10-12

---

## 1. Project Metadata & Pipeline Storage

### Decision
Store `Project`, `Pipeline`, and `PipelineRun` metadata in PostgreSQL within the existing Artemis operational database (`artemis` database on port 5433). Store actual script source code both in PostgreSQL (for fast querying/diffs) and archived in MinIO under `s3://artemis-system/projects/{project_id}/pipelines/{pipeline_id}/script.py`.

### Rationale
- PostgreSQL is already part of the Artemis core infrastructure for state management, pipeline run audits, and authentication.
- Foreign keys between `projects`, `project_pipelines`, and `pipeline_runs` ensure referential integrity and transactional safety during deletions and updates.
- Storing script content in PostgreSQL allows instant inspection via CLI/API without issuing S3 GET requests, while S3 preserves immutability and large script artifacts.

### Alternatives Considered
- **SQLite Database per Project**: Creates file fragmentation, concurrency locking issues during concurrent pipeline runs, and complicates multi-tenant reporting.
- **MinIO JSON Metadata Only**: S3 lacks relational indexing, transactional consistency, and filtering capabilities needed for queries like `list runs by status`.

---

## 2. Docker Container Sandbox Execution Architecture

### Decision
Execute custom user scripts using the Docker Engine API (via Python `docker` client or direct CLI daemon invocation `docker run --rm`). Containers run using an official lightweight Artemis runner image (`artemis-pipeline-runner:latest` based on `python:3.12-slim`).
Container communication follows a clean POSIX filesystem contract:
- Host creates an ephemeral run directory `/tmp/artemis/runs/{run_id}/` with subdirectories `/input`, `/output`, and `/script`.
- Container mounts:
  - `/tmp/artemis/runs/{run_id}/input` $\rightarrow$ `/workspace/input:ro` (read-only)
  - `/tmp/artemis/runs/{run_id}/output` $\rightarrow$ `/workspace/output:rw` (read-write)
  - `/tmp/artemis/runs/{run_id}/script/main.py` $\rightarrow$ `/workspace/main.py:ro`
- Resource limits enforced: `--memory=2g`, `--cpus=2.0`, `--pids-limit=100`, `--network=none` (or restricted bridge for graph ingestion), and `--timeout=300`.

### Rationale
- Completely isolates untrusted user scripts from the host filesystem, preventing arbitrary file modification, host token theft, or accidental host corruption.
- Filesystem-based `/workspace/input` and `/workspace/output` contract is language-agnostic, predictable, and requires zero client libraries in user scripts (users can read standard CSV/JSON/Parquet files from `/workspace/input` and write to `/workspace/output`).
- Ephemeral containers (`--rm`) ensure zero residual state or disk leaks after execution completes or times out.

### Alternatives Considered
- **Python `subprocess` directly on host**: Faster startup (<100ms vs 1s), but lacks memory isolation and security boundaries against malicious user scripts (e.g. scripts attempting `os.system('rm -rf /')` or network abuse). User specifically chose Docker container sandboxing.
- **WebAssembly (WASM / WASI)**: Highly secure, but severely limits data science libraries (PyArrow, DuckDB, Pandas, NetworkX are not fully supported or optimized in standard WASM runtimes).

---

## 3. Multi-Modal Storage Isolation (MinIO & Memgraph)

### Decision
1. **Tabular & Lake Storage (MinIO / DuckDB)**:
   - Medallion tier paths partitioned by project and dataset:
     - Bronze: `s3://telemetry/projects/{project_id}/bronze/{dataset_id}/...`
     - Silver: `s3://telemetry/projects/{project_id}/silver/{dataset_id}/...`
     - Gold: `s3://telemetry/projects/{project_id}/gold/{dataset_id}/...`
   - DuckDB queries for a project target explicit S3 prefixes:
     `SELECT * FROM read_parquet('s3://telemetry/projects/alpha/silver/telemetry/**/*.parquet')`
2. **Knowledge Graph Storage (Memgraph)**:
   - All graph nodes and edges ingested under a project are enriched with a mandatory property `project_id: "{project_id}"`.
   - Node labels and unique names are namespaced (e.g. `MERGE (n:IP_ADDRESS {name: $name, project_id: $project_id})`).
   - Project-scoped queries automatically inject `WHERE n.project_id = $project_id` or `MATCH (n {project_id: $project_id})`.

### Rationale
- Preserves the single-node zero-JVM architecture without requiring multiple running database instances.
- MinIO prefix partitioning allows scalable bucket policies, selective backups, and zero cross-project directory traversal.
- Tagging graph nodes with `project_id` avoids the RAM overhead of spinning up separate Memgraph containers while maintaining strict query boundaries.

### Alternatives Considered
- **Separate MinIO Bucket per Project (`bucket: project-alpha-telemetry`)**: Leads to AWS/MinIO bucket proliferation limits, complex permission management, and inconsistent global bucket configurations.
- **Separate Memgraph Database Instances**: Each Memgraph container consumes ~200 MB RAM idle, which would quickly breach the 12 GB RAM budget when scaling to dozens of projects.

---

## 4. Pipeline Execution Contract & Dataset Mapping

### Decision
A pipeline run accepts:
```json
{
  "pipeline_id": "uuid",
  "input_data": null,
  "input_datasets": ["bronze-telemetry-raw"],
  "target_dataset": "silver-telemetry-clean",
  "target_tier": "silver",
  "parameters": {"threshold": 95.0}
}
```
Execution lifecycle:
1. **Stage Preparation**: Artemis runner collects input data files from MinIO for `input_datasets` (or writes `input_data` to a file) and stages them in `/tmp/artemis/runs/{run_id}/input/`.
2. **Container Launch**: Spawns ephemeral Docker container with resource limits, mounting input and output dirs.
3. **Execution**: Container runs user script. Script reads inputs, executes transformation, and writes resulting `.parquet`, `.csv`, `.json`, or graph Cypher/JSON files to `/workspace/output/`.
4. **Output Ingestion**:
   - If output contains Parquet/tabular files: Uploads them to `s3://telemetry/projects/{project_id}/{target_tier}/{target_dataset}/`.
   - If output contains graph entities (JSON/Cypher): Ingests them to Memgraph with `project_id` tag.
5. **Teardown & Audit**: Container is terminated/removed, run directory is deleted, and audit record is committed to PostgreSQL `pipeline_runs`.

### Rationale
- Completely decoupled: user scripts do not need S3 credentials, database passwords, or network access. They operate on standard local files inside their container.
- Artemis controls the ingestion into MinIO and Memgraph, enforcing data integrity and project isolation.
