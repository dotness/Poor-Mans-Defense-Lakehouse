# Research & Architectural Decisions: Dataset & Query Data TTL Management and Automated Cleanup

**Feature**: `009-dataset-ttl-cleanup`  
**Date**: 2026-11-21  
**Spec**: [spec.md](./spec.md)

---

## 1. Domain Placement & Hexagonal Architecture

- **Decision**: Introduce a dedicated `RetentionDomain` (`src/domains/retention/`) following the established hexagonal layout (`facade/`, `operations/`, `models/contract/`, `models/storage/`, `api/`), and hook its policy resolver and query interceptor into `ProjectDomain`, `AnalyticsDomain`, `GraphDomain`, `DiscoveryDomain`, and `AIDomain`.
- **Rationale**: Retention lifecycle governance spans all existing storage engines (PostgreSQL catalog, MinIO object storage, Memgraph knowledge & discovery graphs, and Redis query caches). Isolating policy calculation, read-time SQL/Cypher query interception, soft-delete state machines, reference-counted graph pruning, and background compaction in `src/domains/retention/` satisfies Principle I (Library-First & Modular Architecture) without bloating `project` or `analytics` domains.
- **Alternatives Considered**:
  - *Embedding TTL logic directly inside `ProjectManager`*: Rejected because query data artifacts (`QueryCache`, `ai_queries`, global `artemis query`), transparent DuckDB/Cypher interception, and cross-store cleanup scheduling cut across multiple domains beyond project CRUD.

---

## 2. TTL Duration Parsing & Hierarchical Policy Resolution

- **Decision**: Implement a deterministic duration parser (`ttl_parser.py`) supporting human-readable expressions (`<int>m`, `<int>h`, `<int>d`, `<int>w`, `<int>mo`, `<int>y`, plus `never` / `infinite` and `0h` for grace periods), normalized to integer seconds (`NULL` for `never`). Policy resolution follows a strict 3-level hierarchy:
  1. **Dataset-explicit policy** (`ttl_policies` with `scope = 'DATASET'`)
  2. **Project-tier default policy** (`ttl_policies` with `scope = 'TIER'`, e.g., project-specific `BRONZE`, `SILVER`, `GOLD` overrides)
  3. **Project or Platform default policy** (`ttl_policies` with `scope = 'PROJECT'` or platform defaults: Bronze = `30d`, Silver = `90d`, Gold = `365d`, Query Cache = `1h`, Materialized Query Export = `7d`, Query Audit History = `30d`, Soft-Delete Grace Period = `24h`).
- **Rationale**: Matches industry-standard Medallion data lakehouse lifecycle governance (short retention on raw Bronze landing, medium on cleansed Silver, long/permanent on curated Gold) while allowing zero-configuration ingestion and granular per-dataset overrides (`FR-001`, `FR-002`).
- **Alternatives Considered**:
  - *ISO-8601 duration strings only (`P30D`, `PT24H`)*: Supported as an alias, but concise tokens (`30d`, `24h`, `7d`, `never`) are primary for CLI ergonomics.

---

## 3. Per-Partition Ingestion Clock vs. Event-Timestamp (`timestamp_column`) Granularity

- **Decision**:
  - Track individual uploaded batch files/partitions in a new PostgreSQL table `dataset_partitions` (`partition_id`, `project_id`, `dataset_id`, `tier`, `object_key`, `storage_uri`, `size_bytes`, `record_count`, `ingested_at`, `min_event_ts`, `max_event_ts`, `lifecycle_status`, `soft_deleted_at`).
  - When a dataset is **overwritten**, old partition entries are replaced and `ingested_at` resets to `NOW()`. When new files are **appended** to an existing dataset, each file gets its own `dataset_partitions` row with its own `ingested_at` clock so older batch files expire independently without deleting newly appended files (`FR-002`).
  - When `timestamp_column` is configured on a dataset, ingestion/compaction records `min_event_ts` and `max_event_ts` per Parquet file using PyArrow column statistics.
- **Rationale**: Tracking per-file metadata in PostgreSQL avoids expensive `LIST` + Parquet footer reads on MinIO during every query or `--dry-run` preview, enabling `< 5s` dry-run previews across 1,000+ datasets (`SC-005`) and exact partition-level pruning.
- **Alternatives Considered**:
  - *Relying purely on MinIO S3 object `last_modified` metadata*: Rejected because S3 object modification times cannot track `min_event_ts`/`max_event_ts` for row-level TTL, cannot store `SOFT_DELETED` state transitions without moving S3 objects, and are slower to scan across thousands of prefixes.

---

## 4. Transparent Query-Layer Interception (DuckDB SQL & Memgraph Cypher)

- **Decision**: Build a `QueryTTLInterceptor` (`src/domains/retention/operations/query_interceptor.py`) invoked by `QueryService.execute()`, `ProjectQueryExecutor.execute_scoped_query()`, and `AgentTools`:
  1. **Whole-Dataset / Partition Interception**: When a SQL query references `read_parquet('s3://telemetry/projects/<project_id>/...')` (including wildcards), the interceptor resolves active, non-expired, non-`SOFT_DELETED` partition URIs from `dataset_partitions`.
     - If all matching datasets/partitions are expired or `SOFT_DELETED`, the interceptor short-circuits and returns an empty result set (`0 rows`) immediately (`SC-002`).
     - If a subset of partition files in a wildcard glob is expired/`SOFT_DELETED`, the interceptor rewrites the `read_parquet(...)` argument to the list of active partition S3 URIs.
  2. **Row-Level (`timestamp_column`) Interception**: When an active dataset in the query has `timestamp_column` configured, the interceptor wraps the `read_parquet(...)` call in a subquery predicate:
     ```sql
     (SELECT * FROM read_parquet([...]) WHERE TRY_CAST("<timestamp_column>" AS TIMESTAMPTZ) >= TIMESTAMPTZ '<cutoff_utc>')
     ```
  3. **Graph Cypher Interception**: Graph nodes/edges ingested via `ProjectGraphStorage` or `KDGGraphStore` carry `dataset_id`, `ingested_at`, and `lifecycle_status` metadata (or are filtered against active dataset IDs for that project), ensuring expired/`SOFT_DELETED` graph elements are excluded at read time.
- **Rationale**: Wrapping `read_parquet(...)` in a filtered subquery expression works transparently for arbitrary analyst `SELECT`, `JOIN`, `GROUP BY`, and CTE queries without requiring external SQL parser libraries that might break on DuckDB-specific syntax, and adds `< 2ms` planning overhead (`SC-006`).
- **Alternatives Considered**:
  - *Creating temporary DuckDB views for every dataset before every query*: Rejected because analysts and AI tools frequently write direct `read_parquet('s3://...')` expressions in SQL. Supporting both direct `read_parquet(...)` interception and dataset-level resolution satisfies the clarification decision (`Q4: Option A`).

---

## 5. Two-Stage Deletion Lifecycle, Virtual Soft-Delete, and Single-Pass Parquet Compaction

- **Decision**:
  - **Stage 1 (`ACTIVE` → `SOFT_DELETED`)**:
    - For whole-dataset/partition expiration (`now >= reference_ts + ttl_seconds` and `hold == false`), the dataset/partition status in PostgreSQL (and `DataResource.lifecycle_status` in Memgraph) transitions to `SOFT_DELETED` with `soft_deleted_at = NOW()` and `purge_after = NOW() + grace_period_seconds`. It is immediately excluded from all queries and invalidate triggers run on dependent ephemeral query caches.
    - For `timestamp_column` datasets where only some rows in a Parquet file are older than `now - ttl_seconds`: rows between `now - ttl_seconds - grace_period_seconds` and `now - ttl_seconds` are **virtually soft-deleted** (hidden immediately by `QueryTTLInterceptor` at read time without rewriting the Parquet file).
  - **Restoration during Grace Period**:
    - Explicit: `artemis project ttl restore` / `POST /api/v1/projects/{project_id}/datasets/{dataset_id}/ttl/restore` (requires `--ttl` extension or `--hold`).
    - Implicit: Updating a `SOFT_DELETED` dataset's TTL to a non-expired duration or setting `hold = true` automatically transitions `SOFT_DELETED` back to `ACTIVE` and clears `soft_deleted_at`.
  - **Stage 2 (`SOFT_DELETED` → `PURGED` / Physical Compaction)**:
    - Once `now >= purge_after` (or immediately if `grace_period == 0h`):
      - Fully expired partition files are deleted from MinIO via `remove_object`.
      - Partially expired `timestamp_column` Parquet files where `min_event_ts < now - ttl_seconds - grace_period_seconds <= max_event_ts` undergo a **single atomic PyArrow/DuckDB compaction**: rows with `<timestamp_column> >= now - ttl_seconds` are written to a new Parquet object in MinIO, the catalog `dataset_partitions` entry is atomically swapped to the new object key with updated `min_event_ts`/`size_bytes`/`record_count`, and the old S3 object is removed.
- **Rationale**: Deferring physical Parquet rewrite until `TTL + grace_period` elapses eliminates double file writes, consumes zero duplicate storage during the grace period, and makes restoration instantaneous (`Q2` / `Q5` clarification).
- **Alternatives Considered**:
  - *Splitting Parquet files into active and `.quarantine` files at Stage 1*: Rejected due to 2x write amplification and temporary storage bloat.

---

## 6. Reference-Counted Graph Pruning & Lineage Tombstones

- **Decision**:
  - **KDG & Project Graph Reference Counting**:
    - In `KDGGraphStore`, `GenericEntity` nodes are linked to `DataResource` via `(r:DataResource)-[:CONTAINS_ENTITY]->(e:GenericEntity)`.
    - In `ProjectGraphStorage`, domain nodes/edges store a `source_datasets` list property (or link to the dataset).
    - When a dataset is permanently purged:
      1. Delete all `(r:DataResource {project_id: $pid, resource_id: $did})-[:HAS_ATTRIBUTE]->(a:DataAttribute)` and `(r)-[rel:CONTAINS_ENTITY]->(e:GenericEntity)` relationships.
      2. Prune orphaned `GenericEntity` nodes in that project that now have zero incoming `:CONTAINS_ENTITY` edges:
         ```cypher
         MATCH (e:GenericEntity {project_id: $project_id})
         WHERE NOT (:DataResource)-[:CONTAINS_ENTITY]->(e)
         DETACH DELETE e;
         ```
      3. For custom project graph nodes/edges (`ProjectGraphStorage`), remove `dataset_id` from `n.source_datasets`; if `size(n.source_datasets) == 0`, `DETACH DELETE n`.
  - **Lineage Tombstones**:
    - Before deleting a `DataResource` node in Memgraph, check if it has outgoing `(:DataResource)-[:DERIVED_FROM]->(:DataResource)` or `(:PipelineExecution)-[:READS_FROM]->(:DataResource)` relationships.
    - If downstream lineage exists, convert the `DataResource` node in-place into a tombstone (`SET r:LineageTombstone, r.lifecycle_status = 'PURGED', r.purged_at = $now, r.applied_ttl = $ttl_str, r.location_uri = null, r.record_count = 0`) and record a row in PostgreSQL `lineage_tombstones`. This keeps `LineageTraverser` paths intact without broken links (`FR-009`).
- **Rationale**: In-place conversion of `DataResource` to carry `lifecycle_status = 'PURGED'` and `:LineageTombstone` preserves all existing `DERIVED_FROM` and `READS_FROM` edges in Memgraph with zero graph rewiring overhead, while excluding the resource from active workspace summaries (`FR-008`, `FR-009`).
- **Alternatives Considered**:
  - *Deleting `DataResource` and recreating separate `LineageTombstone` nodes with copied edges*: Rejected because mutating node labels/properties in-place in Memgraph is atomic and cannot lose edge properties like `via_run_id`.

---

## 7. Query Data Artifact Governance & Source-Aware Cache Invalidation

- **Decision**:
  - Classify query data into 4 governed artifact types tracked in `query_data_artifacts` (PostgreSQL) and Redis:
    1. `SQL_RESULT_CACHE` (ephemeral analytical query cache in Redis `artemis:sql:cache:<hash>`, default TTL `1h`).
    2. `AI_RAG_CACHE` (ephemeral semantic RAG cache in Redis `artemis:ai:query:<hash>`, default TTL `1h`).
    3. `MATERIALIZED_EXPORT` (saved query result dataset stored in MinIO `s3://telemetry/projects/<project_id>/query_exports/<artifact_id>.parquet`, default TTL `7d`, user-overridable via `--ttl` up to project max).
    4. `QUERY_HISTORY_LOG` (audit rows in `ai_queries` and `query_execution_logs`, default TTL `30d`).
  - **Dependency Tracking for Ephemeral Caches**: When caching a SQL or AI query response, record the referenced `project_id` / `dataset_id` keys in a Redis set `artemis:cache:deps:<project_id>:<dataset_id>` (and in `query_data_artifacts.source_datasets`). Whenever a dataset expires, transitions to `SOFT_DELETED`, or is purged, the retention engine immediately flushes all cache keys registered in `artemis:cache:deps:<project_id>:<dataset_id>`.
  - **Independent Lifecycle for Materialized Exports & Logs**: Materialized query exports (`MATERIALIZED_EXPORT`) and `QUERY_HISTORY_LOG` entries are governed strictly by their own `expires_at` timestamp (`FR-003`, `FR-004`).
- **Rationale**: Directly implements the clarification on `FR-003` (ephemeral caches invalidate immediately upon source dataset expiration; materialized exports and audit logs follow their own TTL).
- **Alternatives Considered**:
  - *Flushing the entire Redis database whenever any dataset expires*: Rejected because it would unnecessarily evict unrelated projects' cache entries.

---

## 8. Concurrency Control (Active Read/Write Lock Protection) & Multi-Store Retry State Machine

- **Decision**:
  - **Active Operation Lease Registry**: Provide an atomic lease table/registry (`dataset_active_leases` in PostgreSQL, backed by short-lived heartbeat/TTL timestamps so crashed processes never leave permanent deadlocks). `ScopedIngestionService`, `PipelineExecutor`, and `ProjectQueryExecutor`/`QueryService` acquire a shared/active lease (`acquire_lease(project_id, dataset_id, operation_type, ttl_seconds=300)`) during execution and release it in a `finally` block.
  - When the cleanup worker evaluates an expired dataset/partition, if an active non-expired lease exists in `dataset_active_leases`, cleanup skips physical mutation of that dataset, increments `skipped_locked_count` in `CleanupJobRun`, and defers it to the next cycle (`FR-011`, `SC-004`).
  - **Idempotent Multi-Store Cleanup & `CLEANUP_PENDING_RETRY`**:
    - Cleanup executes in deterministic order: (1) Mark `CLEANUP_IN_PROGRESS` → (2) Invalidate dependent Redis caches → (3) Delete/compact MinIO S3 objects → (4) Prune Memgraph entities & convert `DataResource` to `LineageTombstone` → (5) Mark `PURGED` in PostgreSQL and record `CleanupJobRun`.
    - If step (3) or (4) raises a transient error, the dataset's `lifecycle_status` is recorded as `CLEANUP_PENDING_RETRY` with the last completed step and error message. Subsequent cleanup cycles automatically pick up `CLEANUP_PENDING_RETRY` items and idempotently finish the remaining steps.
- **Rationale**: Prevents read errors during active DuckDB queries or Docker pipeline runs (`FR-011`) and guarantees eventual consistency across MinIO, Memgraph, Redis, and PostgreSQL without distributed 2-phase commit overhead.
- **Alternatives Considered**:
  - *OS file locks (`fcntl`)*: Ineffective across distributed containers (MinIO, Memgraph, FastAPI, CLI). PostgreSQL lease rows with automatic timestamp expiration work uniformly across CLI, API, and Temporal workers.

---

## 9. Background Auto-Cleanup Scheduling (Zero-JVM Compliance)

- **Decision**:
  - Implement `RetentionCleanupWorkflow` and `run_retention_cleanup_activity` in `src/domains/retention/operations/cleanup_workflow.py` using the platform's existing Temporal client pattern (`src/base/temporal.py`), paired with an embedded `asyncio` periodic background task started in FastAPI's `lifespan` (`src/api.py`) and registerable as a standard pipeline (`retention_auto_cleanup`) in the `pipelines` table (`artemis pipeline run retention_auto_cleanup` and `artemis project ttl cleanup`).
- **Rationale**: Reuses the exact dual-mode pattern proven in Feature 005 (`enrichment_workflow.py`): when Temporal server is connected, scheduled workflows execute via Temporal; when running standalone or in lightweight test/CLI environments without Temporal, the `asyncio` periodic loop and direct CLI/API triggers execute the identical idempotent cleanup activity with zero JVM dependencies and `< 20 MB` memory overhead (`SC-006`).
- **Alternatives Considered**:
  - *Adding Celery Beat or Apache Airflow*: Rejected as unnecessary dependencies that increase memory footprint.
