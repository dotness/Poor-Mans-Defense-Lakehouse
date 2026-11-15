# Research: Knowledge Discovery Graph

All Technical Context unknowns are resolved below.

## R1. Where indexing runs relative to ingestion
- **Decision**: Phase 1 (structural) runs right after upload in `ScopedIngestionService` inside a guarded `try/except` (target <30 s); Phase 2 (AI enrichment, entity resolution) is dispatched as an asynchronous Temporal workflow with retries.
- **Rationale**: Meets FR-009/FR-019; Temporal is already part of the architecture and provides retry/visibility.
- **Alternatives**: Fully synchronous (blocks ingestion, violates SC-004); in-process thread pool (no durability/retry); message queue (adds a service).

## R2. Structural introspection
- **Decision**: DuckDB `DESCRIBE`/`SUMMARIZE` over the resource's own S3 path for tabular data; Python flattening for JSON/XML; plain text treated as a document resource.
- **Rationale**: Deterministic, C++ speed, no hallucination (FR-004); reuses existing DuckDB client and project path confinement.
- **Alternatives**: pandas profiling (memory heavy); LLM schema guessing (nondeterministic).

## R3. Pattern profiling
- **Decision**: Regex/set-logic profiler over a bounded sample (default 10,000 rows) detecting UUID, hashes, ISO-8601/UNIX timestamps, WKT/lat-long, IPv4/6, URLs, emails, phones; attribute tagged when ≥80% of non-null sample matches.
- **Rationale**: 100% precise on matches, cheap. **Alternatives**: ML classifiers (extra deps).

## R4. Entity extraction
- **Decision**: Structured attributes with identifier-like patterns or high cardinality → distinct values become `GenericEntity` (capped, default 10,000 per attribute). Unstructured text and ambiguous attributes → Gemini (`gemini-2.5-flash`) open-vocabulary NER with JSON-schema output, chunked and cached in Redis.
- **Rationale**: Limits graph growth and AI cost; satisfies FR-005/FR-020. **Alternatives**: local spaCy models (domain-bound, memory cost); NER on all values (cost).

## R5. Semantic taxonomy mapping
- **Decision**: Embed attribute name + description + a few sample values with the Google embeddings API (768-dim), cache in Redis, compute cosine similarity in-process with numpy against existing taxonomy concepts; assign when ≥0.85, else create a new concept; confidence stored on `MAPS_TO_TAXONOMY`; <0.85 and ≥0.70 flagged `low_confidence`.
- **Rationale**: Attribute counts are small, so a dedicated vector DB is unnecessary (Constitution IV). **Alternatives**: Memgraph vector index (version dependency); pgvector (new extension).

## R6. Cross-project entity resolution
- **Decision**: Exact match on normalized (case/whitespace-folded) `(entity_type, value)` via Memgraph index; fuzzy candidates via `rapidfuzz` Jaro-Winkler ≥0.93 within same entity_type; clusters merged with in-process Union-Find; `SAME_AS` edges carry `confidence` and `method` (`exact`|`fuzzy`).
- **Rationale**: Precision first (SC-005 <5% false links); `rapidfuzz` is a C++ library. **Alternatives**: Memgraph MAGE (not in base image); all-pairs LLM comparison (cost).

## R7. Isolation of cross-project discovery
- **Decision**: Discovery reads only Memgraph/Postgres metadata and every query is restricted to the caller's member projects (`project_id IN $member_projects`), resolved per request from `project_members`. Results contain project id, resource, tier, attribute and entity value/links, with no sample rows or S3 URIs. Counts and totals are computed after filtering, so non-member projects leave no trace (FR-021, SC-006). Administrators (JWT role `admin`) are treated as members of all projects.
- **Rationale**: FR-016, FR-021, SC-006; `ProjectQueryExecutor` guardrails untouched.
- **Alternatives**: Post-filtering results in Python (risks leaking totals); hiding only for non-members' raw data (rejected by the clarification).

## R8. Lineage capture
- **Decision**: Pipeline runs (existing `PipelineDomain`) emit `PipelineExecution` nodes with `READS_FROM`/`WRITES_TO`; `DERIVED_FROM` inferred between those resources. Lineage traversal depth-limited (default 10).
- **Alternatives**: OpenLineage integration (additional service).

## R9. Consistency on re-ingest / delete
- **Decision**: Resource nodes keyed by `(project_id, resource_id)`; re-index performs MERGE then deletes stale attribute/entity edges not seen in the latest `index_version`; dataset deletion cascades via `DETACH DELETE` of the resource subtree and orphan-entity cleanup.
- **Rationale**: FR-017.

## R10. Graceful degradation
- **Decision**: Enrichment job state (`pending`, `running`, `completed`, `failed`, `skipped_no_ai`) is persisted in `kdg_index_jobs`; with no API key the dual-mode fallback marks `skipped_no_ai`, and pattern-based entities still index. Failed jobs retry with exponential backoff (3 attempts).
- **Rationale**: FR-018/FR-019.

## R11. Optional analytics (Louvain/PageRank)
- **Decision**: Out of scope for v1 (needs MAGE); revisit later.

## R12. AI agent integration
- **Decision**: Register `discover_workspace_schema`, `find_cross_project_entities`, `get_data_lineage` in `tools.py` with the existing 5 s timeout and guardrails; read-only Cypher parameterized (no LLM-generated Cypher for these tools).
- **Rationale**: Safe, deterministic tools; FR-015.

## R13. Security / access
- **Decision**: Endpoints use existing JWT auth middleware; all Cypher parameterized; entity values truncated in logs; reindex and member management require project ownership (or `admin` role). The `admin` role exists today only in the hard-coded user table in `src/domains/auth/facade/auth.py`; the bypass must key off the JWT `roles` claim so it keeps working when that table is replaced. The AI agent tools receive the user's member-project list from the request context, never from model-provided arguments.
