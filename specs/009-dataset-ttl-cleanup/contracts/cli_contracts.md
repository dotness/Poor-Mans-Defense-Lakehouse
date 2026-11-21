# CLI Contracts: Dataset & Query Data TTL Management and Automated Cleanup

**Feature**: `009-dataset-ttl-cleanup`  
**Binary**: `artemis`  
**Global Flags**: All commands support `--json` (machine-readable JSON on `stdout`, errors on `stderr`) and standard human-readable tabular/summary formatting on `stdout` (Constitution Principle II, `FR-013`).

---

## 1. `artemis project ttl` Command Group

### 1.1 Set or Update Dataset TTL Policy
```bash
artemis project ttl set \
  --project <project_id> \
  --dataset <dataset_id> \
  [--tier BRONZE|SILVER|GOLD] \
  --ttl <duration|never> \
  [--granularity INGESTION_AGE|TIMESTAMP_COLUMN] \
  [--timestamp-column <col_name>] \
  [--grace-period <duration>] \
  [--json]
```
- **Behavior**: Sets or updates the TTL policy for `<dataset_id>`. If the dataset is currently `SOFT_DELETED` and the new `--ttl` extends expiration into the future (or `never`), it automatically restores the dataset to `ACTIVE` (`FR-006`).
- **Exit Codes**:
  - `0`: Policy applied (and restored if applicable).
  - `1`: Validation error (invalid TTL expression, negative/zero duration, missing `--timestamp-column` when granularity is `TIMESTAMP_COLUMN`, project/dataset not found, or permission denied).

---

### 1.2 Inspect Dataset TTL & Retention State
```bash
artemis project ttl get \
  --project <project_id> \
  --dataset <dataset_id> \
  [--tier BRONZE|SILVER|GOLD] \
  [--json]
```
- **Behavior**: Displays effective TTL, policy source (`DATASET_EXPLICIT`, `TIER_DEFAULT`, `PROJECT_DEFAULT`, `PLATFORM_DEFAULT`), granularity, reference timestamp, expiration boundary, hold status, and partition breakdown.

---

### 1.3 Clear Dataset TTL Override
```bash
artemis project ttl clear \
  --project <project_id> \
  --dataset <dataset_id> \
  [--tier BRONZE|SILVER|GOLD] \
  [--json]
```
- **Behavior**: Removes explicit dataset TTL override and reverts to the tier/project default policy.

---

### 1.4 Set Project, Tier, or Query Data Default TTL
```bash
artemis project ttl set-default \
  --project <project_id> \
  --scope PROJECT|TIER|QUERY_DATA \
  [--tier BRONZE|SILVER|GOLD] \
  [--artifact-type SQL_RESULT_CACHE|AI_RAG_CACHE|MATERIALIZED_EXPORT|QUERY_HISTORY_LOG] \
  --ttl <duration|never> \
  [--grace-period <duration>] \
  [--json]
```
- **Behavior**: Updates default retention rules for a project, a specific Medallion tier in that project, or a query data artifact category (`FR-002`, `FR-003`).

---

### 1.5 Place or Release a Retention Hold
```bash
# Place hold on a dataset (or entire project if --dataset is omitted)
artemis project ttl hold \
  --project <project_id> \
  [--dataset <dataset_id>] \
  [--tier BRONZE|SILVER|GOLD] \
  [--reason "Active incident investigation"] \
  [--json]

# Release hold
artemis project ttl unhold \
  --project <project_id> \
  [--dataset <dataset_id>] \
  [--tier BRONZE|SILVER|GOLD] \
  [--json]
```
- **Behavior**: Suspends or resumes TTL expiration and auto-cleanup (`FR-010`). Placing a hold on a `SOFT_DELETED` dataset implicitly restores it to active queryability (`FR-006`).

---

### 1.6 Restore a Soft-Deleted Dataset or Query Artifact
```bash
artemis project ttl restore \
  --project <project_id> \
  --dataset <dataset_id> \
  [--tier BRONZE|SILVER|GOLD] \
  [--ttl <new_duration|never>] \
  [--hold] \
  [--reason "Restoring dataset"] \
  [--json]
```
- **Behavior**: Explicitly restores a `SOFT_DELETED` dataset (or virtual soft-deleted rows) back to `ACTIVE` during the grace period (`FR-006`). Must provide either `--ttl` (extending expiration) or `--hold` so the restored dataset does not immediately re-expire.

---

### 1.7 View Project Retention Summary
```bash
artemis project ttl summary \
  --project <project_id> \
  [--json]
```
- **Behavior**: Displays a project-wide table of all datasets, effective TTL rules, age, time remaining, hold flags, soft-deleted items in grace period, datasets expiring within 24 hours, lineage tombstones, and query artifact counts (`User Story 4`).

---

### 1.8 Run On-Demand Cleanup or Dry-Run Preview
```bash
artemis project ttl cleanup \
  [--project <project_id>] \
  [--dry-run] \
  [--json]
```
- **Behavior**:
  - With `--dry-run`: Evaluates all datasets, partitions, and query artifacts in `<project_id>` (or across all projects if `--project` is omitted by an admin) and outputs a deterministic impact report (datasets to soft-delete, datasets to purge, `timestamp_column` files to compact, graph nodes to prune, query artifacts to purge, and reclaimable bytes) without modifying any data (`FR-007`, `SC-005`).
  - Without `--dry-run`: Executes the two-stage cleanup lifecycle and prints the resulting `CleanupJobRun` audit summary (`FR-006`, `FR-008`, `FR-012`).

---

### 1.9 Inspect Cleanup Audit History
```bash
artemis project ttl history \
  [--project <project_id>] \
  [--limit 20] \
  [--json]
```
- **Behavior**: Lists historical `CleanupJobRun` records with timestamps, trigger type (`SCHEDULED`, `MANUAL`, `DRY_RUN`), items purged, bytes reclaimed, skipped items (held/locked), and status (`FR-012`).

---

## 2. Extensions to Existing CLI Commands

### 2.1 Ingestion Commands (`--ttl`, `--timestamp-column`)
```bash
artemis project ingest \
  --project <project_id> \
  --dataset <dataset_name> \
  --tier bronze \
  --file <path> \
  [--ttl <duration|never>] \
  [--timestamp-column <col_name>] \
  [--overwrite] \
  [--json]
```
- Optional `--ttl` and `--timestamp-column` allow configuring dataset retention at ingestion time (`User Story 1`).
- Optional `--overwrite` replaces existing dataset partitions and resets the ingestion TTL clock (`FR-002`); omitting `--overwrite` appends a new batch partition with its own per-file `ingested_at` timestamp.

### 2.2 Query & Ask Commands (`--cache-ttl`, `--export-dataset`, `--export-ttl`)
```bash
artemis project query \
  --project <project_id> \
  --sql "<sql>" \
  [--cache-ttl <duration>] \
  [--export-dataset <export_id>] \
  [--export-ttl <duration>] \
  [--json]

artemis ask "<prompt>" \
  [--cache-ttl <duration>] \
  [--json]
```
- Allows analysts to override the cache TTL or materialize query outputs with an explicit query-data TTL (`FR-003`, `FR-004`).
- Read-time TTL filtering is enforced automatically on all executed queries (`FR-005`).
