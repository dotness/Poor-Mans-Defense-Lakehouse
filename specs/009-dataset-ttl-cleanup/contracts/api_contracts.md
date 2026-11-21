# REST API Contracts: Dataset & Query Data TTL Management and Automated Cleanup

**Feature**: `009-dataset-ttl-cleanup`  
**Base URL**: `/api/v1`  
**Authentication**: Standard Artemis JWT / Basic Auth middleware (`authenticate_user`). Project-level endpoints enforce project membership (`is_member`) for read/dry-run operations and project ownership/admin (`is_owner`) for mutations (`FR-014`).

---

## 1. Set or Update Dataset TTL Policy

**Endpoint**: `PUT /api/v1/projects/{project_id}/datasets/{dataset_id}/ttl`  
**Permissions**: Project Owner or Admin

### Request Payload (`DatasetTTLSetRequestContract`)
```json
{
  "tier": "BRONZE",
  "ttl_expression": "30d",
  "granularity": "TIMESTAMP_COLUMN",
  "timestamp_column": "event_timestamp",
  "grace_period_expression": "24h"
}
```
- `tier` (optional, default `"BRONZE"`): `"BRONZE"`, `"SILVER"`, or `"GOLD"`.
- `ttl_expression` (required): Human-readable duration (`"30d"`, `"24h"`, `"7d"`, `"1h"`, `"never"`). Rejects `<= 0` or malformed strings with HTTP `400`.
- `granularity` (optional, default `"INGESTION_AGE"`): `"INGESTION_AGE"` or `"TIMESTAMP_COLUMN"`.
- `timestamp_column` (optional, required if `granularity == "TIMESTAMP_COLUMN"`): Column name for row-level TTL evaluation.
- `grace_period_expression` (optional, default `"24h"`): Soft-delete recovery window (`"24h"`, `"0h"` for immediate purge).

### Response `200 OK` (`DatasetRetentionStateContract`)
```json
{
  "project_id": "alpha-corp",
  "dataset_id": "system_stats",
  "tier": "BRONZE",
  "policy_source": "DATASET_EXPLICIT",
  "effective_ttl_expression": "30d",
  "effective_ttl_seconds": 2592000,
  "granularity": "TIMESTAMP_COLUMN",
  "timestamp_column": "event_timestamp",
  "grace_period_expression": "24h",
  "grace_period_seconds": 86400,
  "reference_timestamp": "2026-11-21T10:00:00Z",
  "expires_at": "2026-12-21T10:00:00Z",
  "soft_deleted_at": null,
  "purge_after": null,
  "retention_hold": false,
  "hold_reason": null,
  "lifecycle_status": "ACTIVE",
  "auto_restored": false
}
```
> **Note on Implicit Restoration (`FR-006`)**: If the target dataset was in `SOFT_DELETED` state within its grace period and the new `ttl_expression` results in a future `expires_at` (or `"never"`), the dataset automatically transitions back to `ACTIVE` and `auto_restored` is returned as `true`.

---

## 2. Inspect Dataset TTL & Lifecycle Status

**Endpoint**: `GET /api/v1/projects/{project_id}/datasets/{dataset_id}/ttl?tier=BRONZE`  
**Permissions**: Project Member, Owner, or Admin

### Response `200 OK` (`DatasetRetentionStateContract`)
Returns the current `DatasetRetentionStateContract` (including remaining seconds until expiration and partition count).

---

## 3. Clear Dataset TTL Override (Revert to Tier/Project Default)

**Endpoint**: `DELETE /api/v1/projects/{project_id}/datasets/{dataset_id}/ttl?tier=BRONZE`  
**Permissions**: Project Owner or Admin

### Response `200 OK` (`DatasetRetentionStateContract`)
Removes the dataset-explicit override and returns the recalculated `DatasetRetentionStateContract` using the inherited `TIER_DEFAULT` or `PROJECT_DEFAULT` policy.

---

## 4. Configure Project, Tier, or Query Data Default TTL Policies

**Endpoint**: `PUT /api/v1/projects/{project_id}/ttl/defaults`  
**Permissions**: Project Owner or Admin

### Request Payload (`ProjectTTLDefaultsRequestContract`)
```json
{
  "target_scope": "QUERY_DATA",
  "tier": null,
  "query_artifact_type": "MATERIALIZED_EXPORT",
  "ttl_expression": "14d",
  "grace_period_expression": "24h"
}
```
- `target_scope`: `"PROJECT"`, `"TIER"`, or `"QUERY_DATA"`.
- `tier`: Required when `target_scope == "TIER"` (`"BRONZE"`, `"SILVER"`, `"GOLD"`).
- `query_artifact_type`: Required when `target_scope == "QUERY_DATA"` (`"SQL_RESULT_CACHE"`, `"AI_RAG_CACHE"`, `"MATERIALIZED_EXPORT"`, `"QUERY_HISTORY_LOG"`).

### Response `200 OK` (`TTLPolicyContract`)
Returns the persisted default `TTLPolicyContract`.

---

## 5. Toggle Dataset or Project Retention Hold (Legal/Investigative Hold)

**Endpoint**: `PUT /api/v1/projects/{project_id}/datasets/{dataset_id}/hold`  
**Project-Wide Endpoint**: `PUT /api/v1/projects/{project_id}/ttl/hold`  
**Permissions**: Project Owner or Admin

### Request Payload (`RetentionHoldRequestContract`)
```json
{
  "tier": "BRONZE",
  "retention_hold": true,
  "reason": "Active incident investigation INC-2026-991"
}
```

### Response `200 OK` (`DatasetRetentionStateContract`)
- When `retention_hold: true`: sets `retention_hold = true`, transitions `lifecycle_status` to `"HELD"`, and if the dataset was `"SOFT_DELETED"`, implicitly restores it to active queryability (`auto_restored = true`).
- When `retention_hold: false`: releases the hold and recalculates `lifecycle_status` (`"ACTIVE"`, `"EXPIRING_SOON"`, or eligible for next cleanup cycle).

---

## 6. Explicitly Restore a Soft-Deleted Dataset or Query Artifact

**Endpoint**: `POST /api/v1/projects/{project_id}/datasets/{dataset_id}/ttl/restore`  
**Permissions**: Project Owner or Admin

### Request Payload (`DatasetRestoreRequestContract`)
```json
{
  "tier": "BRONZE",
  "ttl_expression": "60d",
  "retention_hold": false,
  "reason": "Restoring accidentally expired telemetry dataset"
}
```
- Requires at least one of a non-expired `ttl_expression` or `retention_hold: true` so the restored item does not immediately re-expire on the next cleanup tick (`FR-006`).
- Returns HTTP `409 Conflict` if the item has already been permanently `PURGED` or if neither a valid TTL extension nor a hold is supplied.

### Response `200 OK` (`DatasetRetentionStateContract`)
Returns the restored dataset state with `lifecycle_status: "ACTIVE"` (or `"HELD"`).

---

## 7. Project Retention Summary & Expiring-Soon Dashboard

**Endpoint**: `GET /api/v1/projects/{project_id}/ttl/summary`  
**Permissions**: Project Member, Owner, or Admin

### Response `200 OK` (`ProjectRetentionSummaryContract`)
```json
{
  "project_id": "alpha-corp",
  "default_policies": {
    "BRONZE": "30d",
    "SILVER": "90d",
    "GOLD": "365d",
    "SQL_RESULT_CACHE": "1h",
    "AI_RAG_CACHE": "1h",
    "MATERIALIZED_EXPORT": "7d",
    "QUERY_HISTORY_LOG": "30d"
  },
  "counts": {
    "active": 12,
    "expiring_within_24h": 2,
    "held": 1,
    "soft_deleted": 1,
    "purged_tombstones": 3
  },
  "datasets": [
    {
      "dataset_id": "system_stats",
      "tier": "BRONZE",
      "effective_ttl_expression": "30d",
      "granularity": "INGESTION_AGE",
      "age_seconds": 2510000,
      "remaining_seconds": 82000,
      "expires_at": "2026-11-22T09:46:40Z",
      "retention_hold": false,
      "lifecycle_status": "EXPIRING_SOON"
    }
  ],
  "query_artifacts_summary": {
    "active_caches": 18,
    "materialized_exports": 4,
    "query_history_logs": 140,
    "total_size_bytes": 15728640
  }
}
```

---

## 8. Trigger On-Demand Auto-Cleanup or Dry-Run Preview

**Project Endpoint**: `POST /api/v1/projects/{project_id}/ttl/cleanup`  
**Global Admin Endpoint**: `POST /api/v1/retention/cleanup`  
**Permissions**:
- `dry_run: true`: Any Project Member (for project endpoint) or Admin.
- `dry_run: false`: Project Owner (for project endpoint) or Admin.

### Request Payload (`CleanupTriggerRequestContract`)
```json
{
  "dry_run": true,
  "include_query_artifacts": true
}
```

### Response `200 OK` (`CleanupJobRunContract`)
```json
{
  "run_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
  "trigger_type": "DRY_RUN",
  "project_id": "alpha-corp",
  "initiated_by": "alice",
  "status": "SUCCESS",
  "datasets_evaluated": 16,
  "datasets_soft_deleted": 1,
  "datasets_purged": 2,
  "partitions_compacted": 1,
  "rows_pruned": 14500,
  "query_artifacts_purged": 5,
  "graph_elements_pruned": 48,
  "tombstones_created": 1,
  "bytes_reclaimed": 52428800,
  "skipped_held_count": 1,
  "skipped_locked_count": 0,
  "candidate_items": [
    {
      "item_type": "DATASET",
      "project_id": "alpha-corp",
      "dataset_id": "raw_edge_logs",
      "tier": "BRONZE",
      "action": "PURGE",
      "bytes_reclaimed": 41943040,
      "reason": "Grace period elapsed (TTL 30d + 24h grace)"
    }
  ],
  "errors": [],
  "started_at": "2026-11-21T11:05:00Z",
  "completed_at": "2026-11-21T11:05:01Z",
  "duration_ms": 840
}
```

---

## 9. List Cleanup Audit History

**Endpoint**: `GET /api/v1/projects/{project_id}/ttl/cleanup/runs?limit=20`  
**Global Admin Endpoint**: `GET /api/v1/retention/cleanup/runs?limit=50`  
**Permissions**: Project Member (project scope) or Admin (global scope)

### Response `200 OK` (`List[CleanupJobRunContract]`)
Returns chronological list of `CleanupJobRunContract` audit records.

---

## 10. Query Execution with Explicit Query Data TTL & Export

**Modified Endpoints**:
- `POST /api/v1/projects/{project_id}/query`
- `POST /api/v1/analytics/query`

### Extended Request Fields (`ProjectQueryRequestContract` / `QueryRequestContract`)
```json
{
  "sql": "SELECT device_id, AVG(cpu_usage) FROM read_parquet('s3://telemetry/projects/alpha-corp/bronze/**/*.parquet') GROUP BY device_id",
  "cache_ttl": "2h",
  "export_dataset": "avg_cpu_report",
  "export_ttl": "7d"
}
```
- `cache_ttl` (optional): Custom TTL for the cached result entry (bounded by project max retention).
- `export_dataset` (optional): Materializes the query output as a governed `MATERIALIZED_EXPORT` query data artifact in the project.
- `export_ttl` (optional, default `"7d"`): Explicit TTL for the materialized query export (`FR-004`).
