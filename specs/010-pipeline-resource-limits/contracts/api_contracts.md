# REST API Contracts: Customizable CPU and Memory Limits for Pipeline Runs

**Feature**: `010-pipeline-resource-limits` | **Date**: 2026-11-21 | **Spec**: [spec.md](../spec.md)

Base Prefix: `/api/v1/projects/{project_id}/pipelines`

---

## 1. Create Pipeline (`POST /api/v1/projects/{project_id}/pipelines`)

Accepts optional `default_cpu_limit` and `default_memory_limit` fields for pipeline-level fallback defaults (`FR-003`).

### Request Body (`PipelineCreateContract`)

```json
{
  "name": "cleanse_network_telemetry",
  "description": "Cleanses raw network flow logs into Silver Parquet",
  "stage": "BRONZE_TO_SILVER",
  "script_content": "import pandas as pd\nprint('Running pipeline')\n",
  "docker_image": "artemis-pipeline-runner:latest",
  "default_cpu_limit": 1.5,
  "default_memory_limit": "1g"
}
```

### Success Response (`201 Created` — `PipelineResponseContract`)

```json
{
  "pipeline_id": "550e8400-e29b-41d4-a716-446655440000",
  "project_id": "alpha-ops",
  "name": "cleanse_network_telemetry",
  "description": "Cleanses raw network flow logs into Silver Parquet",
  "stage": "BRONZE_TO_SILVER",
  "docker_image": "artemis-pipeline-runner:latest",
  "default_cpu_limit": 1.5,
  "default_memory_limit": "1g",
  "version": 1,
  "created_by": "admin",
  "created_at": "2026-11-21T19:00:00Z",
  "updated_at": "2026-11-21T19:00:00Z"
}
```

### Error Response (`400 Bad Request`)

Returned when `default_cpu_limit` or `default_memory_limit` is below the minimum operational floor (`< 0.1` cores or `< 64m`), malformed, or exceeds the administrator hard maximum cap under `reject` policy:

```json
{
  "detail": "Requested CPU limit 8.0 cores exceeds administrator hard maximum cap of 4.0 cores."
}
```

---

## 2. Update Pipeline (`PUT /api/v1/projects/{project_id}/pipelines/{pipeline_id}`)

Allows updating `default_cpu_limit` and/or `default_memory_limit` on an existing pipeline (`FR-003`).

### Request Body (`PipelineUpdateContract`)

```json
{
  "default_cpu_limit": 2.5,
  "default_memory_limit": "2048m"
}
```

### Success Response (`200 OK` — `PipelineResponseContract`)

```json
{
  "pipeline_id": "550e8400-e29b-41d4-a716-446655440000",
  "project_id": "alpha-ops",
  "name": "cleanse_network_telemetry",
  "description": "Cleanses raw network flow logs into Silver Parquet",
  "stage": "BRONZE_TO_SILVER",
  "docker_image": "artemis-pipeline-runner:latest",
  "default_cpu_limit": 2.5,
  "default_memory_limit": "2048m",
  "version": 1,
  "created_by": "admin",
  "created_at": "2026-11-21T19:00:00Z",
  "updated_at": "2026-11-21T19:05:00Z"
}
```

---

## 3. Trigger Pipeline Run (`POST /api/v1/projects/{project_id}/pipelines/{pipeline_id}/run`)

Accepts optional per-run `cpu_limit` (float cores) and `memory_limit` (unit-suffixed size string) (`FR-003`, `FR-004`).

### Request Body (`PipelineRunTriggerContract`)

```json
{
  "input_datasets": ["raw_network_logs"],
  "target_dataset": "clean_network_logs",
  "target_tier": "SILVER",
  "timeout_seconds": 300,
  "cpu_limit": 3.0,
  "memory_limit": "3g"
}
```

### Success Response (`200 OK` — `PipelineRunResponseContract`)

```json
{
  "run_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "project_id": "alpha-ops",
  "pipeline_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "SUCCESS",
  "stage": "BRONZE_TO_SILVER",
  "target_tier": "SILVER",
  "target_dataset": "clean_network_logs",
  "records_processed": 1500,
  "duration_ms": 1420,
  "exit_code": 0,
  "logs": "Processed 1500 records.\n",
  "effective_cpu_limit": 3.0,
  "effective_memory_limit": "3g",
  "requested_cpu_limit": 3.0,
  "requested_memory_limit": "3g",
  "resource_clamped": false,
  "details": {
    "storage_uri": "s3://telemetry/projects/alpha-ops/silver/clean_network_logs/...",
    "size_bytes": 98304,
    "container_id": "c7f8a9b01234",
    "effective_cpu_limit": 3.0,
    "effective_memory_limit": "3g",
    "requested_cpu_limit": 3.0,
    "requested_memory_limit": "3g",
    "cpu_source": "run_override",
    "memory_source": "run_override",
    "resource_clamped": false,
    "oom_killed": false
  },
  "started_at": "2026-11-21T19:10:00Z",
  "completed_at": "2026-11-21T19:10:01Z"
}
```

### OOM Termination Response (`200 OK` — Run Completed with `status: "FAILED"` and `exit_code: 137`)

When the container exceeds its effective memory limit at runtime (`FR-011`):

```json
{
  "run_id": "1c2deb4d-3b7d-4bad-9bdd-2b0d7b3dcb7e",
  "project_id": "alpha-ops",
  "pipeline_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "FAILED",
  "stage": "BRONZE_TO_SILVER",
  "target_tier": "SILVER",
  "target_dataset": "clean_network_logs",
  "records_processed": 0,
  "duration_ms": 890,
  "exit_code": 137,
  "logs": "Out of Memory (OOM): Container killed (exit code 137) after exceeding effective memory limit of 128m.",
  "effective_cpu_limit": 1.5,
  "effective_memory_limit": "128m",
  "requested_cpu_limit": null,
  "requested_memory_limit": "128m",
  "resource_clamped": false,
  "details": {
    "error": "Out of Memory (OOM): Container killed (exit code 137) after exceeding effective memory limit of 128m.",
    "effective_cpu_limit": 1.5,
    "effective_memory_limit": "128m",
    "requested_cpu_limit": null,
    "requested_memory_limit": "128m",
    "cpu_source": "pipeline_default",
    "memory_source": "run_override",
    "resource_clamped": false,
    "oom_killed": true
  },
  "started_at": "2026-11-21T19:12:00Z",
  "completed_at": "2026-11-21T19:12:01Z"
}
```

### Error Response (`400 Bad Request`)

Returned when requested CPU or memory is invalid, below minimum floor, or exceeds the administrator hard maximum cap under `DOCKER_RUNNER_RESOURCE_OVERFLOW_POLICY=reject`:

```json
{
  "detail": "Requested memory limit '8g' (8589934592 bytes) exceeds administrator hard maximum cap of '4g' (4294967296 bytes)."
}
```

---

## 4. List Pipeline Runs (`GET /api/v1/projects/{project_id}/pipelines/{pipeline_id}/runs`)

Returns a list of `PipelineRunResponseContract` objects hydrated with `effective_cpu_limit`, `effective_memory_limit`, `requested_cpu_limit`, `requested_memory_limit`, `resource_clamped`, and `details` (`FR-010`).
