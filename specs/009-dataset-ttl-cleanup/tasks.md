---
description: "Task list for Dataset & Query Data TTL Management and Automated Cleanup (009-dataset-ttl-cleanup)"
---

# Tasks: Dataset & Query Data TTL Management and Automated Cleanup

**Input**: Design documents from `/specs/009-dataset-ttl-cleanup/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api_contracts.md](./contracts/api_contracts.md), [contracts/cli_contracts.md](./contracts/cli_contracts.md), [quickstart.md](./quickstart.md)

**Tests**: Included per Constitution Principle III ("Integration and contract testing are NON-NEGOTIABLE. Before code delivery, interface contracts MUST have contract tests written. Integration tests MUST verify end-to-end data flow across container boundaries").

**Organization**: Tasks are grouped by user story (`US1`–`US4`) to enable independent implementation, verification, and incremental delivery.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`, `[US4]`)
- Exact file paths are included in all task descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize the `retention` domain package structure and test directories per [plan.md](./plan.md).

- [x] T001 Create `retention` domain package directories and `__init__.py` files in `src/domains/retention/__init__.py`, `src/domains/retention/facade/__init__.py`, `src/domains/retention/models/__init__.py`, `src/domains/retention/models/contract/__init__.py`, `src/domains/retention/operations/__init__.py`, and `src/domains/retention/api/__init__.py`
- [x] T002 [P] Create unit, contract, and integration test scaffolding directories and `__init__.py` in `tests/unit/retention/__init__.py`
- [x] T003 [P] Add default retention settings (`default_bronze_ttl`, `default_silver_ttl`, `default_gold_ttl`, `default_query_cache_ttl`, `default_query_export_ttl`, `default_query_history_ttl`, `default_grace_period`, `cleanup_interval_seconds`) in `src/config/settings.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core database schema, Pydantic contracts, duration parser, and PostgreSQL repository that MUST be complete before any user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 Add DDL statements and indexes for `ttl_policies`, `dataset_retention_states`, `dataset_partitions`, `query_data_artifacts`, `dataset_active_leases`, `cleanup_job_runs`, and `lineage_tombstones` in `src/config/postgres_init.sql` (and register `retention_auto_cleanup` in `pipelines` seed)
- [x] T005 [P] Implement human-readable TTL and grace-period duration parser (`parse_ttl_expression`, `format_ttl_seconds`, supporting `m`, `h`, `d`, `w`, `mo`, `y`, `0h`, `never`) with strict validation in `src/domains/retention/operations/ttl_parser.py`
- [x] T006 [P] Unit test TTL duration parser edge cases (positive durations, `0h` grace period, `never`/`infinite`, negative/zero rejection, malformed strings) in `tests/unit/retention/test_ttl_parser.py`
- [x] T007 [P] Define Pydantic v2 domain and API contracts (`TTLPolicyContract`, `DatasetTTLSetRequestContract`, `ProjectTTLDefaultsRequestContract`, `DatasetRetentionStateContract`, `DatasetPartitionContract`, `QueryDataArtifactContract`, `RetentionHoldRequestContract`, `DatasetRestoreRequestContract`, `ProjectRetentionSummaryContract`, `CleanupTriggerRequestContract`, `CleanupJobRunContract`, `LineageTombstoneContract`) in `src/domains/retention/models/contract/retention.py`
- [x] T008 Implement `RetentionRepository` for PostgreSQL CRUD across policies, dataset retention states, dataset partitions, query artifacts, active operation leases, cleanup job runs, and lineage tombstones (including auto-schema bootstrap if tables are missing) in `src/domains/retention/operations/retention_repository.py`
- [x] T009 Implement active operation lease manager (`acquire_lease`, `release_lease`, `has_active_lease`, `cleanup_expired_leases`) in `src/domains/retention/operations/retention_repository.py`

**Checkpoint**: Foundation ready — database schema, contracts, duration parser, and repository are available for User Stories 1–4.

---

## Phase 3: User Story 1 - Per-Dataset Retention (TTL) Configuration (Priority: P1) 🎯 MVP

**Goal**: Enable project owners and administrators to configure, view, update, and clear TTL policies on datasets (or inherit tier/project/platform defaults), supporting both per-file/partition ingestion age (with overwrite reset vs. append independent clocks) and optional `timestamp_column` row-level granularity via CLI and REST API.

**Independent Test**: Create a project, ingest a dataset without an explicit TTL and verify it inherits the tier default (`30d` Bronze); set an explicit dataset TTL override (with `INGESTION_AGE` or `TIMESTAMP_COLUMN`), inspect the calculated expiration state via CLI (`artemis project ttl get --json`) and API (`GET /api/v1/projects/{project_id}/datasets/{dataset_id}/ttl`), and clear the override to verify fallback to tier defaults.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T010 [P] [US1] Write contract tests for `DatasetTTLSetRequestContract`, `ProjectTTLDefaultsRequestContract`, `DatasetRetentionStateContract`, CLI `artemis project ttl set|get|clear|set-default`, and REST endpoints in `tests/contract/test_retention_contracts.py`
- [x] T011 [P] [US1] Write unit tests for 3-tier policy hierarchy resolution (`DATASET_EXPLICIT` > `TIER_DEFAULT` > `PROJECT_DEFAULT` > `PLATFORM_DEFAULT`) and overwrite vs. append partition clock calculation in `tests/unit/retention/test_policy_resolver.py`

### Implementation for User Story 1

- [x] T012 [US1] Implement `PolicyResolver` for hierarchical TTL resolution, expiration timestamp calculation, and partition reference clock aggregation in `src/domains/retention/operations/policy_resolver.py`
- [x] T013 [US1] Implement policy management methods (`set_dataset_ttl`, `get_dataset_ttl`, `clear_dataset_ttl`, `set_default_ttl`, `register_ingested_partition`) on `RetentionFacade` in `src/domains/retention/facade/retention.py`
- [x] T014 [US1] Extend `TabularIngestRequestContract` and `GraphIngestRequestContract` with optional `ttl_expression`, `timestamp_column`, and `overwrite` fields in `src/domains/project/models/contract/project.py`
- [x] T015 [US1] Update `ProjectS3Storage.upload_tabular_data` (to extract PyArrow `min_event_ts`/`max_event_ts` when `timestamp_column` is present and handle `--overwrite` object cleanup) in `src/domains/project/operations/s3_storage.py`
- [x] T016 [US1] Update `ScopedIngestionService.ingest_tabular` and `ingest_graph` to acquire ingestion leases, register partition records (`dataset_partitions`), and initialize/update `DatasetRetentionState` via `RetentionFacade` in `src/domains/project/operations/scoped_ingestion.py`
- [x] T017 [US1] Implement FastAPI endpoints `PUT/GET/DELETE /api/v1/projects/{project_id}/datasets/{dataset_id}/ttl` and `PUT /api/v1/projects/{project_id}/ttl/defaults` with project owner/member RBAC checks in `src/domains/retention/api/router.py` and mount router in `src/api.py`
- [x] T018 [US1] Implement CLI subcommands `artemis project ttl set`, `get`, `clear`, and `set-default` in `src/cli/commands/ttl.py` and register `ttl_group` + `--ttl`/`--timestamp-column`/`--overwrite` flags on `artemis project ingest` in `src/cli/commands/project.py`

**Checkpoint**: User Story 1 is complete and independently testable via CLI and API.

---

## Phase 4: User Story 2 - Query Result & Query Artifact TTL Governance (Priority: P1)

**Goal**: Apply configurable TTL policies to query data artifacts (`SQL_RESULT_CACHE`, `AI_RAG_CACHE`, `MATERIALIZED_EXPORT`, `QUERY_HISTORY_LOG`), enforce transparent read-time SQL/Cypher query interception to exclude expired/`SOFT_DELETED` datasets, partitions, and `timestamp_column` rows before physical purge runs, and invalidate dependent ephemeral caches when source datasets expire.

**Independent Test**: Ingest a dataset with both fresh and expired rows (or an expired partition), execute a DuckDB SQL query (`artemis project query`) and Cypher query, and verify expired records are excluded immediately at read time; verify `--cache-ttl` and `--export-dataset`/`--export-ttl` create governed `QueryDataArtifact` records and that expiring a source dataset immediately invalidates its ephemeral SQL/AI cache while preserving materialized query exports until their own TTL expires.

### Tests for User Story 2 ⚠️

- [x] T019 [P] [US2] Write unit tests for `QueryTTLInterceptor` covering whole-dataset expiration short-circuiting, active partition S3 URI list substitution, `timestamp_column >= cutoff` SQL subquery wrapping, and Cypher graph dataset filtering in `tests/unit/retention/test_query_interceptor.py`
- [x] T020 [P] [US2] Add contract tests for `QueryDataArtifactContract` and extended query request parameters (`cache_ttl`, `export_dataset`, `export_ttl`) in `tests/contract/test_retention_contracts.py`

### Implementation for User Story 2

- [x] T021 [US2] Implement `QueryTTLInterceptor` (`intercept_sql_query`, `intercept_cypher_query`, `extract_referenced_datasets`) to filter out expired/`SOFT_DELETED` partitions and inject `timestamp_column` predicates in `src/domains/retention/operations/query_interceptor.py`
- [x] T022 [US2] Implement `QueryArtifactManager` to register and track `SQL_RESULT_CACHE`, `AI_RAG_CACHE`, `MATERIALIZED_EXPORT` (writing Parquet export to MinIO), and `QUERY_HISTORY_LOG` artifacts, enforce project max retention bounds, and invalidate dependent ephemeral caches on source dataset expiration in `src/domains/retention/operations/query_artifact_manager.py`
- [x] T023 [US2] Extend `QueryCache` in `src/services/ai/cache.py` to support SQL result caching (`artemis:sql:cache:*`), dataset dependency registration (`artemis:cache:deps:{project_id}:{dataset_id}`), and targeted invalidation (`invalidate_for_dataset`)
- [x] T024 [US2] Update `ProjectQueryExecutor` (`src/domains/analytics/operations/project_query.py`), `QueryService` (`src/services/analytics/query_service.py`), and `QueryRequestContract` (`src/domains/analytics/models/contract/query.py`) to acquire active query leases, run SQL through `QueryTTLInterceptor`, cache results with `cache_ttl`, and materialize exports with `export_ttl`
- [x] T025 [US2] Update `KDGGraphStore` (`src/domains/discovery/operations/kdg_graph_store.py`), `ProjectGraphStorage` (`src/domains/project/operations/graph_storage.py`), and `AgentTools` (`src/domains/ai/operations/tools.py`) so discovery summaries, entity searches, and AI SQL/Cypher queries automatically exclude expired and `SOFT_DELETED` datasets
- [x] T026 [US2] Update `POST /api/v1/projects/{project_id}/query` (`src/domains/project/api/routes.py`) and CLI commands `artemis project query` (`src/cli/commands/project.py`) and `artemis ask` (`src/cli/commands/ask.py`, `src/cli/main.py`) to accept `--cache-ttl`, `--export-dataset`, and `--export-ttl` options

**Checkpoint**: User Stories 1 and 2 are complete — datasets and query artifacts have governed TTLs, and read-time filtering guarantees 0% stale data exposure prior to physical background purge.

---

## Phase 5: User Story 3 - Automated Background Cleanup & Safe Purge Workflow (Priority: P2)

**Goal**: Provide a scheduled background cleanup worker and on-demand CLI/API cleanup command (with `--dry-run` preview) that performs two-stage deletion (`ACTIVE` → `SOFT_DELETED` → `PURGED`), single-pass Parquet compaction for partially expired `timestamp_column` files after `TTL + grace_period`, reference-counted Memgraph entity pruning, in-place `LineageTombstone` preservation, active lease deferral, and immutable `CleanupJobRun` audit logging.

**Independent Test**: Expire a dataset and a query artifact, run `artemis project ttl cleanup --project <id> --dry-run --json` and verify the predicted candidate items and byte counts match without deleting data; run live cleanup and verify Stage 1 (`SOFT_DELETED`) and Stage 2 (`PURGED` after grace period or `0h` grace), verify shared Memgraph entities survive while unshared entities are pruned, verify downstream lineage retains a `LineageTombstone`, and verify the `CleanupJobRun` audit record in `artemis project ttl history --json`.

### Tests for User Story 3 ⚠️

- [x] T027 [P] [US3] Write unit tests for `ParquetCompactor` verifying single-pass row pruning (`timestamp_column >= now - TTL` after `TTL + grace_period`), whole-file drop when all rows are expired, and updated partition stats in `tests/unit/retention/test_parquet_compactor.py`
- [x] T028 [P] [US3] Add contract tests for `CleanupTriggerRequestContract`, `CleanupJobRunContract`, `LineageTombstoneContract`, and CLI `artemis project ttl cleanup|history` in `tests/contract/test_retention_contracts.py`

### Implementation for User Story 3

- [x] T029 [US3] Implement `ParquetCompactor` using PyArrow/DuckDB to compact partially expired `timestamp_column` Parquet files in MinIO once `TTL + grace_period` has elapsed and remove obsolete S3 objects in `src/domains/retention/operations/parquet_compactor.py`
- [x] T030 [US3] Extend `KDGGraphStore` and `LineageTraverser` (`src/domains/discovery/operations/kdg_graph_store.py`, `src/domains/discovery/operations/lineage.py`) with reference-counted entity pruning (`prune_expired_resource_entities`) and in-place `:LineageTombstone` conversion (`convert_resource_to_tombstone`) when downstream `DERIVED_FROM` lineage exists
- [x] T031 [US3] Implement `CleanupEngine` (`evaluate_and_cleanup`, supporting `dry_run=True/False`, Stage 1 `SOFT_DELETED` transition, Stage 2 S3/Memgraph/Redis/PostgreSQL purge, active lease skipping, `CLEANUP_PENDING_RETRY` recovery, and `CleanupJobRun` recording) in `src/domains/retention/operations/cleanup_engine.py`
- [x] T032 [US3] Implement Temporal `RetentionCleanupWorkflow` / `run_retention_cleanup_activity` and embedded `asyncio` periodic background task in `src/domains/retention/operations/cleanup_workflow.py`, and hook background scheduler startup/shutdown into FastAPI `lifespan` in `src/api.py` and `artemis pipeline run retention_auto_cleanup` in `src/cli/commands/pipeline.py`
- [x] T033 [US3] Expose `trigger_cleanup` and `list_cleanup_runs` on `RetentionFacade` (`src/domains/retention/facade/retention.py`) and implement REST endpoints `POST /api/v1/projects/{project_id}/ttl/cleanup`, `POST /api/v1/retention/cleanup`, `GET /api/v1/projects/{project_id}/ttl/cleanup/runs`, and `GET /api/v1/retention/cleanup/runs` in `src/domains/retention/api/router.py`
- [x] T034 [US3] Implement CLI commands `artemis project ttl cleanup` (with `--dry-run`) and `artemis project ttl history` (with `--limit` and `--json`) in `src/cli/commands/ttl.py`

**Checkpoint**: User Stories 1, 2, and 3 are complete — automated and on-demand multi-store cleanup, dry-run previews, reference-counted graph pruning, and lineage tombstones work end-to-end.

---

## Phase 6: User Story 4 - Legal Hold, Grace Period & Lifecycle Observability (Priority: P3)

**Goal**: Allow project owners and compliance officers to place and release Retention Holds on datasets or projects (pausing auto-cleanup), restore `SOFT_DELETED` items during the grace period (explicitly via `restore` or implicitly via TTL extension or Hold placement), and inspect a comprehensive project retention summary dashboard showing dataset ages, remaining time, holds, and items expiring within 24 hours.

**Independent Test**: Place a Retention Hold on an expired dataset (`artemis project ttl hold`), run auto-cleanup and verify it is skipped as held; release the hold, let cleanup move it to `SOFT_DELETED`, and test both explicit restoration (`artemis project ttl restore --ttl 30d`) and implicit restoration (updating TTL or enabling a hold on a `SOFT_DELETED` dataset); run `artemis project ttl summary --project <id> --json` and verify counts and expiring-soon statuses.

### Tests for User Story 4 ⚠️

- [x] T035 [P] [US4] Write unit tests for explicit restoration (`restore_dataset`), implicit restoration on `SOFT_DELETED` datasets via TTL extension or Retention Hold, `409 Conflict` when restoring already-`PURGED` datasets, and `EXPIRING_SOON` (`<= 24h`) status calculation in `tests/unit/retention/test_policy_resolver.py`
- [x] T036 [P] [US4] Add contract tests for `RetentionHoldRequestContract`, `DatasetRestoreRequestContract`, `ProjectRetentionSummaryContract`, and CLI `artemis project ttl hold|unhold|restore|summary` in `tests/contract/test_retention_contracts.py`

### Implementation for User Story 4

- [x] T037 [US4] Implement `set_retention_hold` (dataset and project scope), `restore_soft_deleted` (explicit `restore` command and implicit auto-restore hook inside `set_dataset_ttl` and `set_retention_hold`), and `get_project_retention_summary` in `src/domains/retention/operations/policy_resolver.py` and `src/domains/retention/facade/retention.py`
- [x] T038 [US4] Implement FastAPI endpoints `PUT /api/v1/projects/{project_id}/datasets/{dataset_id}/hold`, `PUT /api/v1/projects/{project_id}/ttl/hold`, `POST /api/v1/projects/{project_id}/datasets/{dataset_id}/ttl/restore`, and `GET /api/v1/projects/{project_id}/ttl/summary` in `src/domains/retention/api/router.py`
- [x] T039 [US4] Implement CLI subcommands `artemis project ttl hold`, `unhold`, `restore`, and `summary` (supporting human-readable tables and `--json`) in `src/cli/commands/ttl.py`

**Checkpoint**: All 4 User Stories (`US1`–`US4`) are complete and independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end multi-store integration verification, documentation updates, and quickstart validation.

- [x] T040 Write comprehensive end-to-end integration test covering dataset & query TTL inheritance, read-time SQL/Cypher filtering, cache invalidation vs. materialized export independence, `--dry-run` preview accuracy, active lease lock protection, retention hold skipping, `SOFT_DELETED` explicit/implicit restoration, single-pass `timestamp_column` Parquet compaction, reference-counted Memgraph entity pruning, and `LineageTombstone` preservation in `tests/integration/test_dataset_ttl_cleanup.py`
- [x] T041 [P] Update `README.md` CLI reference section with `artemis project ttl` commands and retention governance overview in `README.md`
- [x] T042 Execute full test suite (`pytest tests/unit/retention/ tests/contract/test_retention_contracts.py tests/integration/test_dataset_ttl_cleanup.py`) and validate all scenarios in `specs/009-dataset-ttl-cleanup/quickstart.md`

---

## Phase 8: Convergence

- [x] T043 Acquire and release active operation leases (`PIPELINE_RUN`) for `input_datasets` and `target_dataset` during pipeline execution in `src/domains/pipeline/operations/pipeline_executor.py` per FR-011 (partial)
- [x] T044 Register `SQL_RESULT_CACHE` and `MATERIALIZED_EXPORT` query data artifacts when `cache_ttl` or `export_dataset` are supplied to `AnalyticsFacade.execute_query` in `src/domains/analytics/facade/analytics.py` per FR-004 (partial)
- [x] T045 Add `QUERY_HISTORY_LOG` database table purge (`DELETE FROM ai_queries` for rows exceeding `QUERY_HISTORY_LOG` TTL policy) inside `CleanupEngine._process_query_artifacts` and `RetentionRepository` in `src/domains/retention/operations/cleanup_engine.py` and `src/domains/retention/operations/retention_repository.py` per FR-003 (partial)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1: Setup (`T001`–`T003`)**: No dependencies — starts immediately.
- **Phase 2: Foundational (`T004`–`T009`)**: Depends on Phase 1 — **BLOCKS** all user stories (`US1`–`US4`).
- **Phase 3: User Story 1 (`T010`–`T018`, P1 🎯 MVP)**: Depends on Phase 2. Delivers per-dataset, tier, and project TTL policy management and per-file ingestion clocks.
- **Phase 4: User Story 2 (`T019`–`T026`, P1)**: Depends on Phase 2 and `PolicyResolver` from Phase 3 (`T012`). Delivers query artifact TTLs, source-aware cache invalidation, and transparent read-time SQL/Cypher filtering.
- **Phase 5: User Story 3 (`T027`–`T034`, P2)**: Depends on Phase 3 and Phase 4 (`QueryArtifactManager` for cache/export cleanup). Delivers two-stage auto-cleanup, `--dry-run`, Parquet compaction, reference-counted graph pruning, and lineage tombstones.
- **Phase 6: User Story 4 (`T035`–`T039`, P3)**: Depends on Phase 3 and Phase 5 (`SOFT_DELETED` state transitions). Delivers Retention Holds, explicit/implicit grace-period restoration, and the project retention summary dashboard.
- **Phase 7: Polish (`T040`–`T042`)**: Depends on Phases 3–6 completion.

### User Story Dependency Graph

```text
Phase 1: Setup (T001-T003)
   │
   ▼
Phase 2: Foundational (T004-T009)
   │
   ├───────────────────────────────────┐
   ▼                                   ▼
Phase 3: US1 (P1 - Dataset TTL) ──► Phase 4: US2 (P1 - Query Data & Read-Time Filtering)
   │                                   │
   └───────────────┬───────────────────┘
                   ▼
        Phase 5: US3 (P2 - Auto-Cleanup, Dry-Run, Compaction & Tombstones)
                   │
                   ▼
        Phase 6: US4 (P3 - Legal Holds, Grace-Period Restore & Summary)
                   │
                   ▼
        Phase 7: Polish & End-to-End Integration Validation (T040-T042)
```

---

## Parallel Opportunities

- **Setup & Foundational**:
  - `T002` and `T003` can run in parallel after `T001`.
  - `T005`, `T006`, and `T007` can run in parallel with `T004`.
- **User Story 1 (`US1`)**:
  - `T010` (contract tests) and `T011` (policy resolver unit tests) run in parallel.
  - `T014`/`T015` (S3 & project contracts) and `T012`/`T013` (PolicyResolver & RetentionFacade) can be developed in parallel before wiring `T017` (REST API) and `T018` (CLI).
- **User Story 2 (`US2`)**:
  - `T019` (QueryTTLInterceptor unit tests) and `T020` (QueryDataArtifact contract tests) run in parallel.
  - `T021` (`QueryTTLInterceptor`) and `T022`/`T023` (`QueryArtifactManager` + Redis `QueryCache` dependency tagging) operate on separate files and can run in parallel.
- **User Story 3 (`US3`)**:
  - `T027` (`ParquetCompactor` unit tests) and `T028` (Cleanup contract tests) run in parallel.
  - `T029` (`ParquetCompactor` in MinIO) and `T030` (Memgraph reference-counted entity pruning & `:LineageTombstone` in `KDGGraphStore`) operate on independent storage backends and can run in parallel before `T031` (`CleanupEngine`).
- **User Story 4 (`US4`)**:
  - `T035` and `T036` run in parallel; `T038` (FastAPI endpoints) and `T039` (CLI commands) can run in parallel after `T037`.

---

## Parallel Example: User Story 3 (Multi-Store Cleanup & Compaction)

```bash
# 1. Run US3 unit & contract tests in parallel:
Task T027: "Write unit tests for ParquetCompactor in tests/unit/retention/test_parquet_compactor.py"
Task T028: "Add contract tests for CleanupTriggerRequestContract and CleanupJobRunContract in tests/contract/test_retention_contracts.py"

# 2. Build S3 Parquet compactor and Memgraph reference-counted graph pruner in parallel:
Task T029: "Implement ParquetCompactor using PyArrow/DuckDB in src/domains/retention/operations/parquet_compactor.py"
Task T030: "Extend KDGGraphStore and LineageTraverser with reference-counted entity pruning and LineageTombstone conversion in src/domains/discovery/operations/kdg_graph_store.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 + User Story 2 Core P1)

1. Complete **Phase 1 (Setup)** and **Phase 2 (Foundational)**.
2. Complete **Phase 3 (User Story 1 — Per-Dataset TTL Configuration)**: Delivers immediate dataset/tier/project TTL policy persistence, CLI/API inspection, and per-partition ingestion clocks.
3. Complete **Phase 4 (User Story 2 — Query Artifact TTL & Read-Time Filtering)**: Ensures expired data is immediately excluded at query time and query caches/exports are governed by TTLs.
4. **STOP and VALIDATE**: Run unit and contract tests for `US1` and `US2`.

### Incremental Delivery

1. Add **Phase 5 (User Story 3 — Automated Background Cleanup & Safe Purge)**: Enables `--dry-run` impact previews, scheduled two-stage cleanup, single-pass Parquet compaction, reference-counted graph pruning, and lineage tombstones.
2. Add **Phase 6 (User Story 4 — Legal Hold, Grace Period Restoration & Observability)**: Adds investigative holds, explicit/implicit `SOFT_DELETED` restoration, and the project retention summary dashboard.
3. Complete **Phase 7 (Polish & Integration)**: Run full end-to-end integration tests across all stories and verify `quickstart.md`.
