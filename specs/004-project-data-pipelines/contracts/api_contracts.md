# REST API Contracts: Project Data Pipelines

**Feature**: `004-project-data-pipelines` | **Date**: 2026-10-12

---

## 1. Project Management Endpoints

### 1.1 Create Project
- **Method & Path**: `POST /api/v1/projects`
- **Auth**: Bearer JWT (`admin` role)
- **Request Body**:
  ```json
  {
    "project_id": "cyber-defense",
    "name": "Cyber Defense Operations",
    "description": "Perimeter network analysis and OSINT correlation"
  }
  ```
- **Responses**:
  - `201 Created`: Project created.
    ```json
    {
      "project_id": "cyber-defense",
      "name": "Cyber Defense Operations",
      "description": "Perimeter network analysis and OSINT correlation",
      "status": "ACTIVE",
      "created_at": "2026-10-12T14:00:00Z",
      "updated_at": "2026-10-12T14:00:00Z"
    }
    ```
  - `400 Bad Request`: Invalid project ID format or already exists.

### 1.2 List Projects
- **Method & Path**: `GET /api/v1/projects`
- **Auth**: Bearer JWT (`admin` or `analyst`)
- **Response**:
  - `200 OK`: `List[ProjectResponseContract]`

### 1.3 Get Project
- **Method & Path**: `GET /api/v1/projects/{project_id}`
- **Response**: `200 OK` or `404 Not Found`

### 1.4 Delete Project
- **Method & Path**: `DELETE /api/v1/projects/{project_id}`
- **Auth**: Bearer JWT (`admin` role)
- **Response**: `200 OK` `{"status": "DELETED", "project_id": "cyber-defense"}`

---

## 2. Project Ingestion Endpoints

### 2.1 Ingest Tabular Dataset to Bronze
- **Method & Path**: `POST /api/v1/projects/{project_id}/ingest/tabular`
- **Content-Type**: `multipart/form-data` or `application/json`
- **Parameters**: `dataset_name: str` (e.g. `raw_firewall_logs`), `file: UploadFile` (CSV, JSONL, Parquet)
- **Response**:
  ```json
  {
    "status": "SUCCESS",
    "project_id": "cyber-defense",
    "tier": "BRONZE",
    "dataset_name": "raw_firewall_logs",
    "records_ingested": 10500,
    "storage_uri": "s3://telemetry/projects/cyber-defense/bronze/raw_firewall_logs/..."
  }
  ```

### 2.2 Ingest Graph Entities to Project
- **Method & Path**: `POST /api/v1/projects/{project_id}/ingest/graph`
- **Request Body**:
  ```json
  {
    "nodes": [
      {"name": "198.51.100.24", "label": "IP_ADDRESS", "properties": {"asn": "AS64496"}}
    ],
    "edges": [
      {"source": "c2.darknet.org", "target": "198.51.100.24", "relationship": "RESOLVES_TO"}
    ]
  }
  ```
- **Response**:
  ```json
  {
    "status": "SUCCESS",
    "project_id": "cyber-defense",
    "nodes_imported": 1,
    "edges_imported": 1
  }
  ```

---

## 3. Shareable Pipeline Entity CRUD Endpoints

### 3.1 Create Pipeline with Script
- **Method & Path**: `POST /api/v1/projects/{project_id}/pipelines`
- **Request Body**:
  ```json
  {
    "name": "Normalize Network Logs",
    "description": "Parses raw syslog into normalized schema with geoIP lookup",
    "stage": "BRONZE_TO_SILVER",
    "script_content": "import sys\nimport pyarrow as pa\n# Transformation logic...\n",
    "docker_image": "artemis-pipeline-runner:latest"
  }
  ```
- **Response**: `201 Created` with `PipelineResponseContract`.

### 3.2 List Project Pipelines
- **Method & Path**: `GET /api/v1/projects/{project_id}/pipelines`
- **Response**: `200 OK` `List[PipelineResponseContract]`

### 3.3 Update Pipeline
- **Method & Path**: `PUT /api/v1/projects/{project_id}/pipelines/{pipeline_id}`
- **Request Body**: `PipelineUpdateContract`
- **Response**: `200 OK` (increments version number)

### 3.4 Delete Pipeline
- **Method & Path**: `DELETE /api/v1/projects/{project_id}/pipelines/{pipeline_id}`
- **Response**: `200 OK`

---

## 4. Pipeline Execution & Audit Endpoints

### 4.1 Trigger Pipeline Run
- **Method & Path**: `POST /api/v1/projects/{project_id}/pipelines/{pipeline_id}/run`
- **Request Body**:
  ```json
  {
    "input_datasets": ["raw_firewall_logs"],
    "target_dataset": "clean_firewall_events",
    "target_tier": "SILVER",
    "parameters": {"drop_null_ips": true},
    "timeout_seconds": 300
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "run_id": "run-4f81c9a1",
    "project_id": "cyber-defense",
    "pipeline_id": "pipe-912a",
    "status": "SUCCESS",
    "stage": "BRONZE_TO_SILVER",
    "target_tier": "SILVER",
    "target_dataset": "clean_firewall_events",
    "records_processed": 10500,
    "duration_ms": 1420,
    "exit_code": 0,
    "started_at": "2026-10-12T14:05:00Z",
    "completed_at": "2026-10-12T14:05:01Z"
  }
  ```

### 4.2 List Pipeline Runs History
- **Method & Path**: `GET /api/v1/projects/{project_id}/pipelines/{pipeline_id}/runs`
- **Response**: `200 OK` `List[PipelineRunResponseContract]`
