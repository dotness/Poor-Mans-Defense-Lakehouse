# Implementation Plan: Knowledge Discovery Graph

**Branch**: `005-knowledge-discovery-graph` | **Date**: 2026-10-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-knowledge-discovery-graph/spec.md`

## Summary

Add a new `DiscoveryDomain` (`src/domains/discovery/`) that builds a federated semantic meta-layer in Memgraph over data ingested into project workspaces. A two-phase indexer hooks into `ScopedIngestionService`: Phase 1 (deterministic, synchronous-fast) introspects schemas with DuckDB and regex pattern profiling; Phase 2 (asynchronous, Temporal-backed) performs Gemini zero-shot NER, embedding-based attribute taxonomy mapping, and cross-project `SAME_AS` entity resolution (exact + fuzzy + Union-Find). Discovery is exposed through a `DiscoveryFacade`, REST endpoints, `artemis project discover` / `artemis discover entity|lineage` CLI commands, and three new `DynamicAgentLoop` tools. Cross-project queries read only graph metadata, never other projects' S3 paths, preserving existing confinement, and are filtered to the projects the requesting user is a member of (FR-021). A minimal membership model (`project_members` table; the creator becomes owner and owners manage members) is added to the project domain (FR-022).

## Technical Context

**Language/Version**: Python 3.12+ (strictly typed, Pydantic v2 contracts)

**Primary Dependencies**: existing `duckdb`, `neo4j` (Bolt client for Memgraph), `fastapi`, `click`, `tabulate`, `psycopg2-binary`, Temporal worker, Google GenAI SDK (already used by `genai_service`). New (to be vetted with dependency scan before adding): `rapidfuzz` (C++ fuzzy string matching), `numpy` (cosine similarity).

**Storage**:
- Memgraph: KDG nodes/edges (Workspace, DataResource, DataAttribute, GenericEntity, SemanticTaxonomy, PipelineExecution).
- PostgreSQL: indexing job state (`kdg_index_jobs`) for observability, retries and pending enrichment; project membership (`project_members`).
- Redis: embedding and NER response cache (existing AI cache).
- MinIO/DuckDB: read-only source of data for introspection, always within the owning project's path.

**Testing**: `pytest`, `pytest-asyncio`, contract tests for CLI/API, integration tests in `tests/integration/test_knowledge_discovery.py`; Gemini mocked via the existing dual-mode (no API key) fallback.

**Target Platform**: Linux VM (x86_64), Docker Compose stack.

**Project Type**: Multi-service platform (CLI + REST API + background Temporal activities).

**Performance Goals**: Structural index <30 s for ≤1M rows; project summary <5 s; cross-project entity search <3 s over ≥50 projects; ingestion overhead ≤10%.

**Constraints**: Idle memory budget unchanged (<12 GB); no JVM components; no Memgraph MAGE/GDS dependency required; indexing failures never fail ingestion; AI optional.

**Scale/Scope**: ~50 projects, up to millions of rows per resource; entity values sampled/capped per attribute (default 10,000 distinct values) to bound graph growth.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Library-First & Modular | PASS | Self-contained `discovery` domain with facade/operations/models/api, following existing hexagonal layout. |
| II. Unified CLI (`--json`) | PASS | New `artemis discover` group and `project discover`; all support `--json`, stdout/stderr conventions. |
| III. Test-First & Integration | PASS | Contract tests for CLI/API schemas precede implementation; integration test spans ingestion → DuckDB → Memgraph → AI. |
| IV. Resource Constraint / Zero-JVM | PASS | Only C++/Rust-backed libs (DuckDB, rapidfuzz, numpy); inference offloaded to Google AI Studio; Louvain/PageRank deferred as optional (no MAGE). |
| Memory ≤12 GB / Ingestion ≥10k ev/s | PASS | Phase 2 is async and bounded; telemetry MQTT path is not hooked. |
| Security (Traefik, auth) | PASS | Endpoints sit behind existing JWT auth middleware (`sub`, `roles` claims); every discovery result is filtered by project membership; cross-project results are metadata only. |

Post-design re-check: PASS (no violations; Complexity Tracking empty).

## Project Structure

### Documentation (this feature)

```text
specs/005-knowledge-discovery-graph/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli_contracts.md
│   └── api_contracts.md
├── checklists/requirements.md
└── tasks.md             # created by /speckit-tasks
```

### Source Code (repository root)

```text
src/
├── domains/
│   ├── discovery/
│   │   ├── facade/discovery.py            # DiscoveryFacade (summary, entity search, lineage, reindex)
│   │   ├── operations/
│   │   │   ├── structural_indexer.py      # Phase 1: DuckDB/JSON introspection + pattern profiling
│   │   │   ├── pattern_profiler.py        # regex primitives (UUID, ISO date, IP, email, ...)
│   │   │   ├── enrichment.py              # Phase 2: Gemini NER + embeddings + taxonomy mapping
│   │   │   ├── entity_resolution.py       # exact/fuzzy match + Union-Find SAME_AS
│   │   │   ├── kdg_graph_store.py         # Cypher MERGE/query procedures, indexes
│   │   │   └── lineage.py                 # DERIVED_FROM / PROCESSED_BY traversal
│   │   ├── models/
│   │   │   ├── contract/discovery.py      # WorkspaceKnowledgeContract, EntityCorrelationContract, LineageContract
│   │   │   └── storage/index_job.py       # SQLAlchemy kdg_index_jobs
│   │   └── api/router.py
│   ├── project/
│   │   ├── operations/scoped_ingestion.py   # MODIFIED: post-ingest indexing trigger
│   │   ├── operations/project_manager.py    # MODIFIED: record creator as owner; delete cascades
│   │   ├── operations/membership.py         # NEW: ProjectMembershipService (owner/member, is_member, list_member_projects)
│   │   ├── models/contract/membership.py    # NEW: MemberContract, MemberAddRequestContract
│   │   └── api/routes.py                    # MODIFIED: /projects/{id}/members endpoints
│   ├── pipeline/...                              # MODIFIED: emit lineage/execution events
│   └── ai/operations/tools.py                    # MODIFIED: 3 discovery tools
├── services/graph/memgraph_client.py             # MODIFIED: KDG index bootstrap helper
└── cli/commands/discover.py                      # NEW; registered in cli/main.py, project.py gets `discover` and `members` subcommands

tests/
├── contract/test_discovery_contracts.py
├── integration/test_knowledge_discovery.py
└── unit/discovery/
```

**Structure Decision**: Single-project layout reusing the existing domain-driven hexagonal structure (`src/domains/<domain>/{facade,operations,models,api}`) and the unified CLI package. A new domain is chosen (rather than extending `project`) so discovery can span projects without weakening the project domain's isolation guarantees.

## Complexity Tracking

No constitution violations; section intentionally empty.
