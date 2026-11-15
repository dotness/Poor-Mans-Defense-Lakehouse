# Feature Specification: Project-Scoped Data Ingestion & Medallion Script Pipelines

**Feature Branch**: `004-project-data-pipelines`

**Created**: 2026-10-12

**Status**: Ready for Planning

**Input**: User description: "Extend the system with a capability to create projects and ingest any data to these projects (graph or parquet). I want to be able to upload my own script for processing data at ingestion or between brones/silver/gold."

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Project Creation & Scoped Data Ingestion

As a data analyst or security engineer, I need to create named projects and ingest heterogeneous data (both tabular/time-series Parquet/CSV/JSON files and graph/threat-intelligence entities/relationships) strictly isolated within my designated project boundary.

**Independent Test**: Can be fully tested by creating a project via CLI/API, ingesting a sample tabular dataset and a sample entity relationship dataset with project association, and verifying that records are stored under that project's namespace without cross-tenant bleed.

**Acceptance Scenarios**:

1. **Given** no project exists with identifier `project-alpha`, **When** the user creates a project named "Alpha Defense", **Then** the system assigns a unique project identifier `project-alpha` and initializes dedicated storage namespaces.
2. **Given** an existing project `project-alpha`, **When** the user uploads a tabular file (CSV/JSON/Parquet) to `project-alpha`, **Then** the data lands in the project's raw Bronze storage space and is immediately queryable via project-filtered analytics.
3. **Given** an existing project `project-alpha`, **When** the user ingests graph entities and relationships into `project-alpha`, **Then** all created nodes and edges are tagged with `project-alpha` and queryable only within that project's scope.
4. **Given** two distinct projects `project-alpha` and `project-beta`, **When** querying data from `project-alpha`, **Then** records and graph nodes belonging to `project-beta` are strictly excluded.

---

### User Story 2 - Shareable Pipeline Entities & Script Management

As a pipeline engineer or analyst, I need to create, update, inspect, and delete shareable "Pipeline" entities within a project containing user-uploaded transformation scripts, so that team members can reuse, version, and manage data processing pipelines.

**Independent Test**: Can be verified by creating a pipeline via `POST /api/v1/projects/{project_id}/pipelines` with a transformation script, listing project pipelines, updating the script with a new version, and deleting an obsolete pipeline.

**Acceptance Scenarios**:

1. **Given** an active project `project-alpha`, **When** a user creates a pipeline named "Cleanse Logs" with an attached Python script, **Then** the system validates Python syntax, stores the script, assigns a unique `pipeline_id`, and registers it as an active pipeline in the project.
2. **Given** an existing pipeline entity in `project-alpha`, **When** any project member lists pipelines, **Then** the system returns all configured pipelines, their associated stages (`ingestion`, `bronze_to_silver`, `silver_to_gold`, or custom), script checksums, and author metadata.
3. **Given** an existing pipeline `pipe-123`, **When** the author updates the script or deletes the pipeline via API/CLI, **Then** changes are applied atomically and historical execution runs retain audit traceability.
4. **Given** an invalid or syntactically malformed script file, **When** uploaded during pipeline creation/update, **Then** the system rejects the operation with descriptive syntax error messages and does not alter the active pipeline configuration.

---

### User Story 3 - Docker-Sandboxed Pipeline Execution with Dataset Mapping

As an intelligence operator, I need to trigger a project pipeline—supplying either direct inline data or a list of existing source datasets in the project, plus a target destination dataset—and execute the transformation inside an isolated Docker container sandbox to update Bronze, Silver, or Gold tiers securely.

**Independent Test**: Can be verified by triggering a pipeline run targeting source datasets `["bronze_network_logs"]` and destination `silver_clean_network`, confirming that the script runs inside an ephemeral Docker container, and validating that the output dataset is written to Silver.

**Acceptance Scenarios**:

1. **Given** a pipeline `cleanse-telemetry` in `project-alpha`, **When** triggered with `input_datasets: ["bronze-raw-telemetry"]` and `target_dataset: "silver-curated-telemetry"`, **Then** the system launches an ephemeral Docker container, feeds the input datasets, executes the user script, and writes the output Parquet table into Silver.
2. **Given** a pipeline configured for graph extraction, **When** triggered with tabular input data and a graph target destination, **Then** the script executes in Docker, extracts entities/relationships, and merges them into the project's Memgraph knowledge graph tagged with `project_id`.
3. **Given** a pipeline triggered with direct raw payload data, **When** executed, **Then** the system streams the payload directly to the container's input stream and records the processed result in the target dataset.
4. **Given** a script execution failure or timeout in the container, **When** an error occurs, **Then** the container is cleanly terminated, the pipeline run records a `FAILED` status with container log snippets, and the target dataset is protected from partial or corrupt writes.

---

### User Story 4 - Project-Scoped Analytical & Knowledge Graph Querying

As an analyst, I need to inspect datasets across Bronze, Silver, and Gold tiers, view pipeline run histories, and query both tabular lake tables and graph networks scoped to my active project using the CLI and REST API.

**Independent Test**: Can be verified by running `artemis project query --project project-alpha --sql "..."` and inspecting pipeline run logs via `artemis project pipeline history --project project-alpha`.

**Acceptance Scenarios**:

1. **Given** multiple pipeline runs in `project-alpha`, **When** the user requests execution history, **Then** the system returns a timestamped list of run statuses, pipeline names, input/target datasets, duration, container exit codes, and record counts.
2. **Given** Gold tier data in `project-alpha`, **When** querying analytical metrics via DuckDB or graph entities via Memgraph with `--project project-alpha`, **Then** queries execute efficiently against the project's isolated storage partitions.

---

### Edge Cases

- **Large File Ingestion**: Ingesting multi-gigabyte files must stream into Bronze storage without loading entire payloads into host memory, respecting the < 12 GB RAM system constraint.
- **Docker Container Resource Limits**: Ephemeral Docker containers running user scripts must have enforced CPU, memory limits (e.g., max 2 GB RAM per run), and execution timeouts (e.g., 300 seconds) to prevent host exhaustion.
- **Concurrent Ingestion & Pipeline Runs**: Multiple uploads and pipeline executions across different projects must run in isolated container and storage namespaces without race conditions or shared state contamination.
- **Missing or Empty Input Datasets**: If a pipeline run specifies an input dataset that contains no records or does not exist, the runner must exit gracefully with a clear informational status rather than a crash.
- **Orphaned Container Cleanup**: If a pipeline run fails or is cancelled, the system must guarantee that the ephemeral Docker container and its temporary volume mounts are purged immediately.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support creating, listing, inspecting, and deleting projects, each with a unique project slug/ID, display name, description, and creation metadata.
- **FR-002**: Each project MUST maintain an isolated data namespace separating Bronze (raw landing), Silver (cleansed/structured), and Gold (aggregated/refined) data tiers in object storage and graph storage.
- **FR-003**: The system MUST accept tabular data (Parquet, CSV, JSON Lines) targeted to a specific project and store it in that project's Bronze storage tier.
- **FR-004**: The system MUST accept graph data (nodes, edges, OSINT reports) targeted to a specific project and tag all resulting knowledge graph entities with the project identifier.
- **FR-005**: The system MUST support creating, retrieving, updating, and deleting shareable Pipeline entities within a project via REST API (`POST/GET/PUT/DELETE /api/v1/projects/{project_id}/pipelines`) and CLI (`artemis project pipeline ...`).
- **FR-006**: Each Pipeline entity MUST store a user-uploaded Python script, descriptive metadata, target stage binding (`ingestion`, `bronze_to_silver`, `silver_to_gold`, or `custom`), version number, and author info.
- **FR-007**: The system MUST validate uploaded scripts for Python syntax correctness prior to pipeline registration or update.
- **FR-008**: Custom pipeline scripts MUST execute within isolated ephemeral Docker containers, mounting project input and output data paths with configured memory/CPU limits and strict timeout enforcement.
- **FR-009**: The system MUST support triggering pipeline runs with either raw input data directly or a list of existing project source dataset identifiers, and a specified target dataset destination path/identifier in Bronze, Silver, or Gold.
- **FR-010**: Pipeline runs MUST be recorded with execution status (`PENDING`, `RUNNING`, `SUCCESS`, `FAILED`), timestamps, pipeline ID, input/output datasets, records processed, container exit code, and error logs.
- **FR-011**: All custom script container executions MUST enforce a configurable execution timeout (default: 300 seconds) and terminate runaway containers automatically.
- **FR-012**: The system MUST provide CLI commands under `artemis project` to manage projects, create/update/list pipelines, trigger pipeline runs with dataset mappings, and query project datasets.
- **FR-013**: The system MUST provide REST API endpoints for all project management, pipeline entity CRUD, dataset ingestion, and pipeline execution operations.
- **FR-014**: The system MUST execute pipeline processing steps without violating the platform's zero-JVM architecture and < 12 GB RAM idle footprint.
- **FR-015**: Graph transformations executed in pipeline containers MUST be able to emit standard openCypher or node/edge contracts that are ingested into Memgraph scoped by `project_id`.

---

### Key Entities *(include if feature involves data)*

- **Project**: Represents an isolated workspace. Attributes: `project_id` (string slug), `name` (string), `description` (string), `created_at` (datetime), `updated_at` (datetime), `status` (ACTIVE/ARCHIVED).
- **Pipeline**: Represents a shareable transformation workflow within a project. Attributes: `pipeline_id` (UUID), `project_id` (string), `name` (string), `description` (string), `stage` (INGESTION, BRONZE_TO_SILVER, SILVER_TO_GOLD, CUSTOM), `script_content` (string), `script_path` (string), `docker_image` (string, default: `artemis-pipeline-runner`), `version` (int), `created_by` (string), `created_at` (datetime), `updated_at` (datetime).
- **PipelineRun**: Represents a historical execution of a project pipeline. Attributes: `run_id` (UUID), `project_id` (string), `pipeline_id` (UUID), `input_datasets` (list of strings), `target_dataset` (string), `status` (PENDING, RUNNING, SUCCESS, FAILED), `container_id` (string), `started_at` (datetime), `completed_at` (datetime), `records_processed` (int), `logs` (string), `details` (JSON dictionary).
- **ProjectDataset**: Represents a named data asset residing in a specific project tier. Attributes: `dataset_id` (string), `project_id` (string), `tier` (BRONZE, SILVER, GOLD), `dataset_type` (PARQUET, GRAPH, JSON, CSV), `storage_uri` (S3/local path), `size_bytes` (int), `record_count` (int), `last_modified` (datetime).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can create a project and ingest an initial dataset in under 10 seconds via a single CLI command or API call.
- **SC-002**: Users can create, update, or inspect a Pipeline entity with an uploaded transformation script in under 5 seconds.
- **SC-003**: Ephemeral Docker runner container initializes, executes, and terminates a 50,000-record transformation script from Bronze to Silver in under 20 seconds.
- **SC-004**: 100% of pipeline run attempts record an auditable status entry with container exit code, execution duration, and record counts in the tracking database.
- **SC-005**: 100% of data queries and graph traversals scoped to a project return only data associated with that project ID, ensuring complete workspace isolation.
- **SC-006**: System maintains idle RAM consumption under 12 GB across all background daemons with multi-project tracking enabled.

---

## Assumptions

- Ephemeral pipeline containers run a lightweight Python 3.12 image (`artemis-pipeline-runner`) pre-loaded with native analytical libraries (DuckDB, PyArrow, Pandas, Neo4j Bolt client).
- The host system has Docker or a lightweight container runtime accessible to the Artemis backend service for launching pipeline runner containers.
- Data storage continues to leverage MinIO (S3 object paths partitioned as `s3://telemetry/projects/{project_id}/{tier}/{dataset_id}/...`) and Memgraph (entities tagged with `project_id` property).
- Pipeline workflow orchestration can execute via direct Docker task dispatch or Temporal container activity workflows.
- Administrative authentication is inherited from Artemis's existing JWT role-based security framework (`admin` / `analyst` scopes).
