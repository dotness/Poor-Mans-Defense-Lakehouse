# Implementation Plan: Dataset & Query Data TTL Management and Automated Cleanup

**Branch**: `009-dataset-ttl-cleanup` | **Date**: 2026-11-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-dataset-ttl-cleanup/spec.md`

## Summary

Introduce a self-contained `RetentionDomain` (`src/domains/retention/`) that governs Time-To-Live (TTL) retention policies and automated two-stage lifecycle cleanup across project datasets (tabular, semi-structured, and graph) and query data artifacts (analytical SQL caches, AI RAG caches, materialized query exports, and query execution audit logs).

Key technical capabilities:
1. **Hierarchical Policy & Granularity Governance**: Supports project, Medallion tier (`BRONZE=30d`, `SILVER=90d`, `GOLD=365d`), query artifact category, and dataset-level TTL policies with per-file/partition `ingested_at` tracking (for appends vs. overwrites) and optional row-level `timestamp_column` event-timestamp pruning.
2. **Transparent Read-Time Query Interception**: `QueryTTLInterceptor` hooks into `ProjectQueryExecutor`, `QueryService`, and `AgentTools` to exclude expired or `SOFT_DELETED` dataset files from S3 path/glob resolution and inject `timestamp_column >= now - TTL` predicates (and graph entity expiration filters) into raw SQL and Cypher queries before execution.
3. **Source-Aware Query Artifact Lifecycle**: Governs `SQL_RESULT_CACHE`, `AI_RAG_CACHE`, `MATERIALIZED_EXPORT`, and `QUERY_HISTORY_LOG` artifacts; automatically invalidates ephemeral SQL/AI caches when any underlying source dataset expires while allowing materialized exports and audit logs to follow their own assigned TTLs.
4. **Two-Stage Deletion, Instant Recovery & Multi-Store Atomic Purge**: Implements a configurable `SOFT_DELETED` grace period (default `24h`, or `0h` for immediate purge) with both explicit (`restore`) and implicit (TTL extension or Retention Hold) restoration, single-pass Parquet compaction for partially expired `timestamp_column` files after `TTL + grace_period`, active read/write lease protection, reference-counted Memgraph entity pruning, in-place `LineageTombstone` preservation, and immutable `CleanupJobRun` audit trails via Temporal/asyncio background scheduling.

## Technical Context

**Language/Version**: Python 3.12+ (strictly typed, Pydantic v2 contracts)

**Primary Dependencies**: Existing `duckdb`, `pyarrow`, `minio`, `neo4j` (Memgraph Bolt client), `redis`, `psycopg2-binary`, `fastapi`, `click`, `tabulate`, `temporalio` (with built-in `asyncio` fallback). Zero new third-party dependencies required.

**Storage**:
- **PostgreSQL**: `ttl_policies`, `dataset_retention_states`, `dataset_partitions`, `query_data_artifacts`, `dataset_active_leases`, `cleanup_job_runs`, `lineage_tombstones`.
- **MinIO (S3)**: Project dataset Parquet/CSV/JSON partitions and materialized query exports (`s3://telemetry/projects/{project_id}/...`).
- **Memgraph**: `DataResource` lifecycle attributes (`lifecycle_status`, `expires_at`, `:LineageTombstone` conversion) and reference-counted `GenericEntity` / project graph nodes.
- **Redis**: Ephemeral SQL & AI RAG caches (`artemis:sql:cache:*`, `artemis:ai:query:*`) and dataset-to-cache dependency sets (`artemis:cache:deps:{project_id}:{dataset_id}`).

**Testing**: `pytest`, `pytest-asyncio`, contract tests (`tests/contract/test_retention_contracts.py`), unit tests (`tests/unit/retention/`), and end-to-end integration tests (`tests/integration/test_dataset_ttl_cleanup.py`).

**Target Platform**: Linux VM (x86_64, 16–32 GB RAM, CPU-only), Docker Compose stack.

**Project Type**: Multi-service data lakehouse platform (Unified CLI + FastAPI REST Gateway + background Temporal/asyncio worker).

**Performance Goals**:
- Policy CRUD and inspection: `< 2 seconds` (`SC-001`).
- Read-time query interception overhead: `< 5%` query latency overhead (`< 2ms` SQL rewrite planning) (`SC-006`).
- `--dry-run` cleanup preview across 1,000 datasets: `< 5 seconds` (`SC-005`).
- Immediate 100% read-time exclusion of expired data and query caches (`SC-002`).

**Constraints**: Total platform idle memory `< 12 GB RAM`; strictly Zero-JVM; active queries/pipelines protected from concurrent purge corruption via short-lived database leases (`FR-011`); cross-project isolation and project membership RBAC strictly enforced (`FR-014`).

**Scale/Scope**: ~50+ projects, up to 1,000+ datasets and thousands of partition files per project, millions of rows per Parquet dataset.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Library-First & Modular Architecture** | **PASS** | Self-contained `src/domains/retention/` domain with clean facade, Pydantic contracts, operations, and FastAPI router. |
| **II. Unified CLI Interface (`--json`)** | **PASS** | All `artemis project ttl` subcommands (`set`, `get`, `clear`, `set-default`, `hold`, `unhold`, `restore`, `summary`, `cleanup`, `history`) output formatted tables to stdout, errors to stderr, and support `--json`. |
| **III. Test-First & Integration Rigor** | **PASS** | Contract tests for all Pydantic schemas, CLI commands, and REST endpoints precede implementation; integration tests verify cross-store coordination (PostgreSQL → MinIO → DuckDB → Memgraph → Redis). |
| **IV. Resource Constraint & Zero-JVM Sovereignty** | **PASS** | Zero JVM components; Parquet compaction uses native C++ PyArrow/DuckDB in bounded batches; scheduling uses existing Temporal/asyncio pattern. |
| **Operating Constraints (RAM < 12 GB, Latency < 5s)** | **PASS** | Metadata-driven expiration checks in PostgreSQL avoid scanning MinIO during dry-runs; single-pass Parquet compaction runs only after `TTL + grace_period`. |
| **Security & Confinement** | **PASS** | Reuses `ProjectMembershipService` (`is_member` for read/dry-run, `is_owner` for policy mutations, holds, restore, and live cleanup) and JWT auth middleware. |

*Post-Design Gate Evaluation*: **PASS** (Zero violations; Complexity Tracking table empty).

## Project Structure

### Documentation (this feature)

```text
specs/009-dataset-ttl-cleanup/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── api_contracts.md
│   └── cli_contracts.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── config/
│   └── postgres_init.sql                              # MODIFIED: add 7 retention tables & indexes
├── domains/
│   ├── retention/                                     # NEW DOMAIN: Dataset & Query Data TTL Governance
│   │   ├── __init__.py
│   │   ├── facade/
│   │   │   ├── __init__.py
│   │   │   └── retention.py                           # RetentionFacade (policies, holds, restore, summary, cleanup)
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── contract/
│   │   │       ├── __init__.py
│   │   │       └── retention.py                       # Pydantic v2 contracts for TTL policies, states, artifacts, runs
│   │   ├── operations/
│   │   │   ├── __init__.py
│   │   │   ├── ttl_parser.py                          # Human-readable duration parser (30d, 24h, 0h, never)
│   │   │   ├── retention_repository.py                # PostgreSQL persistence for policies, states, partitions, leases, audit runs
│   │   │   ├── policy_resolver.py                     # Hierarchical resolution (Dataset > Tier > Project > Platform)
│   │   │   ├── query_interceptor.py                   # Transparent DuckDB SQL & Cypher read-time TTL filtering
│   │   │   ├── query_artifact_manager.py              # SQL/AI cache dependency invalidation, materialized exports, log pruning
│   │   │   ├── parquet_compactor.py                   # Single-pass PyArrow/DuckDB row-level compaction after TTL + grace
│   │   │   ├── cleanup_engine.py                      # Two-stage soft-delete, multi-store atomic purge, ref-counted graph & tombstones
│   │   │   └── cleanup_workflow.py                    # Temporal workflow + asyncio background periodic scheduler
│   │   └── api/
│   │       ├── __init__.py
│   │       └── router.py                              # FastAPI routes under /api/v1/projects/{project_id}/... & /api/v1/retention/...
│   ├── project/
│   │   ├── operations/
│   │   │   ├── project_manager.py                     # MODIFIED: register dataset partitions & default retention state
│   │   │   └── scoped_ingestion.py                    # MODIFIED: support --ttl, --timestamp-column, --overwrite, lease acquisition
│   │   ├── models/contract/project.py                 # MODIFIED: optional ttl_expression, timestamp_column, overwrite fields
│   │   └── api/routes.py                              # MODIFIED: pass optional TTL parameters on tabular/graph ingest
│   ├── analytics/
│   │   ├── operations/project_query.py                # MODIFIED: integrate QueryTTLInterceptor, active lease & query cache/export TTL
│   │   └── models/contract/query.py                   # MODIFIED: optional cache_ttl, export_dataset, export_ttl fields
│   ├── discovery/
│   │   └── operations/
│   │       ├── kdg_graph_store.py                     # MODIFIED: exclude SOFT_DELETED/PURGED from summaries; ref-counted entity pruning & LineageTombstone conversion
│   │       └── lineage.py                             # MODIFIED: include LineageTombstone metadata in provenance trees
│   └── ai/
│       └── operations/tools.py                        # MODIFIED: route AI SQL/Cypher queries through QueryTTLInterceptor
├── services/
│   ├── ai/cache.py                                    # MODIFIED: source dataset dependency tagging & targeted cache invalidation
│   └── analytics/query_service.py                     # MODIFIED: integrate QueryTTLInterceptor & SQL result cache TTL
├── cli/
│   └── commands/
│       ├── project.py                                 # MODIFIED: register `artemis project ttl` subgroup and `--ttl` / `--cache-ttl` flags
│       └── ttl.py                                     # NEW: CLI implementation for `artemis project ttl ...` commands
└── api.py                                             # MODIFIED: mount retention_router and start background cleanup loop in lifespan

tests/
├── contract/
│   └── test_retention_contracts.py                    # NEW: Pydantic, CLI, and REST API contract tests
├── unit/
│   └── retention/
│       ├── test_ttl_parser.py                         # NEW: Duration expression parsing & validation
│       ├── test_policy_resolver.py                    # NEW: Hierarchy resolution & implicit/explicit restore transitions
│       ├── test_query_interceptor.py                  # NEW: SQL/Cypher read-time filtering & timestamp_column subquery rewrite
│       └── test_parquet_compactor.py                  # NEW: Single-pass row pruning after TTL + grace_period
└── integration/
    └── test_dataset_ttl_cleanup.py                    # NEW: End-to-end ingestion -> TTL -> read-time filter -> soft-delete -> restore -> purge -> lineage tombstone
```

**Structure Decision**: Extends the existing single-repository hexagonal domain architecture (`src/domains/<domain>/{facade,models,operations,api}`) by adding `src/domains/retention/` and `src/cli/commands/ttl.py`, keeping cross-store lifecycle management modular while integrating cleanly with `project`, `analytics`, `discovery`, and `ai` domains.

## Complexity Tracking

No constitution violations; section intentionally empty.

## Verification Plan

### Automated Security Check

- **Security Scanner**: Run a scan on all newly created files to identify common vulnerabilities (e.g., XSS, SQL injection). If findings are detected, auto-apply the fix and document the results.
- **Security Audit**: Audit the new code for design-level security issues (input validation, secrets handling, auth checks). Document findings and remediations in the `walkthrough.md` artifact using the `generate_security_audit_report` skill.

