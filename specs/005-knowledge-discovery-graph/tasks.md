# Tasks: Knowledge Discovery Graph

**Input**: Design documents from `/specs/005-knowledge-discovery-graph/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included. The project constitution (Principle III) makes contract and integration tests mandatory; contract tests are written before implementation.

**Organization**: Tasks are grouped by user story so each can be implemented and tested independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story (US1–US4) the task belongs to
- All paths are relative to the repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffolding for the new `discovery` domain

- [X] T001 Run the dependency scan for `rapidfuzz` and `numpy`, then add the approved versions to the project dependency manifest (requirements/pyproject)
- [X] T002 Create the domain skeleton with `__init__.py` files: `src/domains/discovery/{facade,operations,models/contract,models/storage,api}/` and `tests/unit/discovery/`
- [X] T003 [P] Add discovery settings (sample size 10,000, entity cap per attribute 10,000, taxonomy thresholds 0.85/0.70, fuzzy threshold 0.93, lineage depth 10, retry attempts 3) to `src/config/settings.py`
- [X] T004 [P] Add test fixtures (`patients.csv`, `accounts.csv`, a sample text document) under `tests/fixtures/discovery/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Models, membership, graph store, job tracking and facade shell that every story depends on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 [P] Create Pydantic contracts (`WorkspaceKnowledgeContract`, `ResourceKnowledge`, `AttributeKnowledge`, `EntityCorrelationContract`, `EntityMatch`, `LineageContract`, `LineageNode`, `LineageEdge`, `IndexJobContract`) in `src/domains/discovery/models/contract/discovery.py`
- [X] T006 [P] Create the `kdg_index_jobs` SQLAlchemy model with phase/status enums in `src/domains/discovery/models/storage/index_job.py` and add the table to `src/config/postgres_init.sql`
- [X] T007 [P] Add the `project_members` table (project_id FK with cascade, user_id, role owner/member, added_by, added_at) and a backfill step for legacy projects (no rows → admin-only visibility until an owner is set) to `src/config/postgres_init.sql`
- [X] T008 [P] Create membership contracts (`MemberContract`, `MemberAddRequestContract`) in `src/domains/project/models/contract/membership.py`
- [X] T009 Implement `ProjectMembershipService` (`add_member`, `remove_member` with last-owner protection, `is_member`, `list_member_projects`, admin-role bypass, per-request evaluation without caching) in `src/domains/project/operations/membership.py` (depends on T007, T008)
- [X] T010 Pass the authenticated user (JWT `sub`) from the project create API route and CLI into `ProjectManager.create_project`, record that user as owner, and cascade membership removal on delete, in `src/domains/project/operations/project_manager.py`, `src/domains/project/api/routes.py` and `src/cli/commands/project.py` (depends on T009)
- [X] T011 Implement `KDGGraphStore` in `src/domains/discovery/operations/kdg_graph_store.py`: index bootstrap (project_id, normalized_value, entity_type, taxonomy name), parameterized MERGE helpers for Workspace/DataResource/DataAttribute/GenericEntity/SemanticTaxonomy, read queries that always take a `member_projects` list and filter with `project_id IN $member_projects` before computing counts/totals, stale-edge pruning by `index_version`, resource-subtree delete with orphan-entity cleanup (uses `src/services/graph/memgraph_client.py`)
- [X] T012 [P] Implement `IndexJobRepository` (create, transition status, retry with attempts ≤ 3, list by project/status) in `src/domains/discovery/operations/job_repository.py`
- [X] T013 Create the `DiscoveryFacade` shell extending `DomainFacade` in `src/domains/discovery/facade/discovery.py` with method stubs (`get_workspace_knowledge`, `find_entities`, `get_lineage`, `reindex`, `list_jobs`) and a shared helper that resolves the caller's member projects from the authenticated user context (depends on T009)
- [X] T014 [P] Create the FastAPI router skeleton with the JWT auth dependency in `src/domains/discovery/api/router.py` and register it in `src/api.py`
- [X] T015 [P] Create the CLI group skeleton `discover` in `src/cli/commands/discover.py` with a shared `--json` output helper, and register it in `src/cli/main.py`
- [X] T016 [P] Write unit tests for `KDGGraphStore` (including member filtering of counts), `IndexJobRepository` (state transitions) and `ProjectMembershipService` (owner/member rules, last-owner protection, bypass only for the `admin` role, legacy projects) in `tests/unit/discovery/test_graph_store.py`, `tests/unit/discovery/test_job_repository.py` and `tests/unit/discovery/test_membership.py`

**Checkpoint**: Foundation ready, user story implementation can begin

---

## Phase 3: User Story 1 - Discover What Exists Inside a Project (Priority: P1) 🎯 MVP

**Goal**: Ingested data is automatically indexed (structure, attributes, patterns, entities) and viewable as a project knowledge summary, visible to project members only.

**Independent Test**: Ingest a tabular dataset and a text document into one project, run `artemis project discover <id>`, and verify resources, attributes/types, tier, row counts and entity counts appear; empty project shows an empty-state message; a non-member gets the same response as for an unknown project.

### Tests for User Story 1

- [X] T017 [P] [US1] Contract tests for `GET /api/v1/discovery/workspace/{project_id}` (including 404 for non-member) and `artemis project discover` output/exit codes in `tests/contract/test_discovery_contracts.py`
- [X] T018 [P] [US1] Unit tests for the pattern profiler (UUID, hash, ISO/UNIX time, lat/long, IP, URL, email, phone, 80% threshold) in `tests/unit/discovery/test_pattern_profiler.py`
- [X] T019 [P] [US1] Unit tests for the structural indexer (tabular, JSON flattening, text resource, corrupt file) in `tests/unit/discovery/test_structural_indexer.py`
- [X] T020 [P] [US1] Unit tests for enrichment (mocked Gemini NER, taxonomy cosine thresholds, `skipped_no_ai` fallback) in `tests/unit/discovery/test_enrichment.py`
- [X] T021 [US1] Integration test: ingest tabular + text, assert Phase 1 summary immediately and Phase 2 enrichment later, and that an indexing failure does not fail ingestion, in `tests/integration/test_knowledge_discovery.py`

### Implementation for User Story 1

- [X] T022 [P] [US1] Implement the regex/set-logic `PatternProfiler` in `src/domains/discovery/operations/pattern_profiler.py`
- [X] T023 [US1] Implement Phase 1 `StructuralIndexer` (DuckDB DESCRIBE/SUMMARIZE within the project's own S3 path, JSON/XML flattening, text/graph resource handling, cardinality, null ratio, pattern-based entity capture capped per attribute) in `src/domains/discovery/operations/structural_indexer.py` (depends on T011, T022)
- [X] T024 [P] [US1] Implement Phase 2 `EnrichmentService` (Gemini open-vocabulary NER with JSON output and chunking, embeddings, taxonomy mapping with confidence/low_confidence flags, Redis caching, graceful no-API-key mode) in `src/domains/discovery/operations/enrichment.py`
- [X] T025 [US1] Create the Temporal workflow/activity for asynchronous enrichment with exponential-backoff retries and job-state updates in `src/domains/discovery/operations/enrichment_workflow.py` (depends on T012, T024)
- [X] T026 [US1] Hook indexing into `ScopedIngestionService` (`ingest_tabular`, `ingest_graph`, file/text uploads): run Phase 1 in a guarded try/except that records failures without failing ingestion, then dispatch the enrichment workflow, in `src/domains/project/operations/scoped_ingestion.py`
- [X] T027 [US1] Handle re-ingest and dataset deletion (index_version bump + stale pruning; cascade removal on delete) in `src/domains/project/operations/scoped_ingestion.py` and `src/domains/project/operations/project_manager.py`
- [X] T028 [US1] Implement `DiscoveryFacade.get_workspace_knowledge` and `list_jobs` (membership check treating non-members like unknown projects, enrichment status, empty state) in `src/domains/discovery/facade/discovery.py`
- [X] T029 [US1] Implement `GET /workspace/{project_id}` and `GET /jobs/{project_id}` in `src/domains/discovery/api/router.py`
- [X] T030 [US1] Implement `artemis project discover <id>` (human + `--json`) in `src/cli/commands/project.py` and `artemis discover jobs` in `src/cli/commands/discover.py`
- [X] T031 [US1] Add structured logging and failure surfacing for indexing operations across the US1 modules

**Checkpoint**: User Story 1 is fully functional and testable independently (MVP)

---

## Phase 4: User Story 2 - Find a Shared Entity Across Projects (Priority: P2)

**Goal**: Search an entity value/type across the user's projects and receive metadata-only correlations, including fuzzy matches with confidence; projects the user is not a member of leave no trace.

**Independent Test**: Ingest the same identifier into two projects, run `artemis discover entity --value ...`, and confirm both projects/datasets/fields are returned for a member of both; a member of only one sees only that project, with no trace of the other.

### Tests for User Story 2

- [X] T032 [P] [US2] Contract tests for `GET /api/v1/discovery/cross-project` (400 without value/type) and `artemis discover entity` in `tests/contract/test_discovery_contracts.py`
- [X] T033 [P] [US2] Unit tests for entity resolution (normalization, exact match, Jaro-Winkler ≥ 0.93, Union-Find clustering, type mismatch) in `tests/unit/discovery/test_entity_resolution.py`
- [X] T034 [P] [US2] Integration test for cross-project correlation and member scoping (a non-member project is absent from matches, counts and totals; no `location_uri`/sample rows exposed; membership removal takes effect on the next request) in `tests/integration/test_knowledge_discovery.py`
- [X] T035 [P] [US2] Contract tests for the membership endpoints and `artemis project members` commands (owner/admin only, last-owner 409) in `tests/contract/test_membership_contracts.py`

### Implementation for User Story 2

- [X] T036 [P] [US2] Implement `EntityResolver` (exact + `rapidfuzz` fuzzy candidates, in-process Union-Find, `SAME_AS` edges with confidence/method) in `src/domains/discovery/operations/entity_resolution.py`
- [X] T037 [US2] Invoke entity resolution at the end of the enrichment workflow in `src/domains/discovery/operations/enrichment_workflow.py` (depends on T036)
- [X] T038 [US2] Implement `DiscoveryFacade.find_entities` with metadata-only output, member-project filtering applied in the query, and totals computed after filtering in `src/domains/discovery/facade/discovery.py`
- [X] T039 [US2] Implement `GET /cross-project` in `src/domains/discovery/api/router.py`
- [X] T040 [US2] Implement `artemis discover entity --value/--type/--fuzzy` in `src/cli/commands/discover.py`
- [X] T041 [US2] Implement membership endpoints (`GET/POST /api/v1/projects/{id}/members`, `DELETE .../members/{user_id}`) in `src/domains/project/api/routes.py`
- [X] T042 [US2] Implement `artemis project members list|add|remove` (`list` supports `--json`) in `src/cli/commands/project.py`
- [X] T043 [US2] Implement `reindex` (facade, `POST /reindex/{project_id}` returning 202, `artemis discover reindex`) with owner/admin check in `src/domains/discovery/facade/discovery.py`, `src/domains/discovery/api/router.py`, `src/cli/commands/discover.py`

**Checkpoint**: User Stories 1 and 2 both work independently

---

## Phase 5: User Story 3 - Trace Data Lineage (Priority: P3)

**Goal**: Show where a dataset came from and which pipeline runs produced it, within and across the user's projects.

**Independent Test**: Run a pipeline that derives a Gold dataset from a Bronze one, request lineage for the Gold dataset, and verify the source and pipeline run appear; standalone datasets show as root; lineage nodes in non-member projects are omitted.

### Tests for User Story 3

- [X] T044 [P] [US3] Contract tests for `GET /lineage/{project_id}/{dataset_id}` and `artemis discover lineage` in `tests/contract/test_discovery_contracts.py`
- [X] T045 [P] [US3] Unit tests for lineage traversal (depth limit, root detection, cycles, non-member node omission) in `tests/unit/discovery/test_lineage.py`
- [X] T046 [US3] Integration test: pipeline run produces `PipelineExecution` and `DERIVED_FROM` edges in `tests/integration/test_knowledge_discovery.py`

### Implementation for User Story 3

- [X] T047 [US3] Emit `PipelineExecution` nodes with `READS_FROM`/`WRITES_TO`/`PROCESSED_BY` and infer `DERIVED_FROM` on pipeline run completion in `src/domains/pipeline/operations/pipeline_executor.py` (via `KDGGraphStore`, failure-safe)
- [X] T048 [P] [US3] Implement lineage traversal with member-project filtering in `src/domains/discovery/operations/lineage.py`
- [X] T049 [US3] Implement `DiscoveryFacade.get_lineage` in `src/domains/discovery/facade/discovery.py`
- [X] T050 [US3] Implement `GET /lineage/{project_id}/{dataset_id}` in `src/domains/discovery/api/router.py`
- [X] T051 [US3] Implement `artemis discover lineage --project --dataset --depth` in `src/cli/commands/discover.py`

**Checkpoint**: User Stories 1–3 work independently

---

## Phase 6: User Story 4 - Natural-Language Discovery Questions (Priority: P4)

**Goal**: The AI assistant answers discovery questions grounded in the knowledge graph, limited to the asking user's projects.

**Independent Test**: With indexed data in two projects, `artemis ask "Which projects reference account ACCT-99812?"` names both projects for a member of both, and only one for a member of one.

### Tests for User Story 4

- [x] T052 [P] [US4] Unit tests for the three agent tools (arguments, read-only, timeout, guardrails, member list taken from request context and not from model-supplied arguments) in `tests/unit/discovery/test_agent_tools.py`
- [x] T053 [US4] Integration test for `artemis ask` discovery questions with member scoping (mocked Gemini), run over a fixed validation set of about 20 question/answer pairs in `tests/fixtures/discovery/nl_questions.json` that asserts at least 85% correct (SC-007), in `tests/integration/test_knowledge_discovery.py`

### Implementation for User Story 4

- [x] T054 [US4] Register `discover_workspace_schema`, `find_cross_project_entities` and `get_data_lineage` in `src/domains/ai/operations/tools.py` using `DiscoveryFacade` with the existing 5 s timeout and the authenticated user's member projects
- [x] T055 [US4] Expose the new tool declarations and update the system prompt in `src/domains/ai/operations/dynamic_loop.py` and `src/domains/ai/operations/guardrails.py`
- [x] T056 [US4] Add the tools to the AI facade wiring in `src/domains/ai/facade/ai.py`

**Checkpoint**: All user stories independently functional


---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T057 [P] Write `docs/architecture/knowledge_discovery_graph_guide.md` from the implemented design (including the membership model) and link it in `README.md` (promote from `docs/architecture/ideas/`)
- [x] T058 Performance validation against SC-001–SC-004 (summary <5 s, structural index <30 s for a 1M-row, 20-column Parquet file, cross-project search <3 s over 50 projects including the membership filter, ingestion overhead ≤10%) in `tests/integration/test_discovery_performance.py`
- [x] T059 Entity-linking accuracy validation (≥90% recall, <5% false links) on a labeled fixture in `tests/integration/test_entity_linking_accuracy.py`
- [x] T060 Security hardening review: parameterized Cypher only, entity-value truncation in logs, 0% non-member references (SC-006) across API, CLI and AI tools
- [x] T061 [P] Cross-domain validation (healthcare, finance, IoT fixtures, no domain config) per SC-008 in `tests/integration/test_knowledge_discovery.py`
- [x] T062 Verify idle memory stays within budget (SC-009) and run `make test`
- [x] T063 Run all scenarios (1–6) in `specs/005-knowledge-discovery-graph/quickstart.md`, including the manual live-Gemini check for SC-007


---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (1)** → **Foundational (2)** → **User Stories (3–6)** → **Polish (7)**
- Within Foundational: T005–T008 first (parallel); T009 needs T007/T008; T010 and T013 need T009; T011 needs T005; T014–T016 after T005.

### User Story Dependencies
- **US1 (P1)**: starts after Phase 2; no dependency on other stories (MVP).
- **US2 (P2)**: starts after Phase 2; consumes entities produced by US1's indexers (T023/T024), so US1's indexing must exist for end-to-end tests. Membership management (T041, T042) is needed to exercise scoping end to end.
- **US3 (P3)**: starts after Phase 2; needs DataResource nodes from US1's indexer.
- **US4 (P4)**: depends on facade methods from US1–US3 (T028, T038, T049).

### Within Each Story
- Contract/unit tests first and failing → models → operations → facade → API/CLI.

## Parallel Opportunities

- Setup: T003, T004. Foundational: T005–T008, T012, T014–T016.
- US1 tests T017–T020 together; T022 and T024 together.
- US2: T032–T035 together; T036 alongside tests.
- US3: T044, T045, T048 together.
- After Phase 2, US1, US2 and US3 can proceed in parallel with separate developers (US2/US3 integration tests need US1's indexer).

### Parallel Example: User Story 1

```text
Task: "Contract tests in tests/contract/test_discovery_contracts.py"             (T017)
Task: "Pattern profiler tests in tests/unit/discovery/test_pattern_profiler.py"  (T018)
Task: "Structural indexer tests in tests/unit/discovery/test_structural_indexer.py" (T019)
Task: "Enrichment tests in tests/unit/discovery/test_enrichment.py"              (T020)
Task: "PatternProfiler in src/domains/discovery/operations/pattern_profiler.py"  (T022)
Task: "EnrichmentService in src/domains/discovery/operations/enrichment.py"      (T024)
```

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Phase 1 Setup → Phase 2 Foundational (includes membership, since all discovery reads are member-scoped).
2. Phase 3 (US1) → **stop and validate** with quickstart Scenario 1 and Scenario 5.
3. Demo project-level discovery.

### Incremental Delivery
1. Foundation → US1 (MVP) → US2 (cross-project + member management) → US3 (lineage) → US4 (natural language) → Polish.
2. Each increment is demonstrable without breaking earlier ones.

## Notes

- [P] tasks touch different files with no incomplete dependencies; several tasks edit `discover.py`, `router.py`, `project.py` or `discovery.py` and are therefore sequential, not [P].
- Indexing failures must never fail ingestion (FR-019); verify in T021.
- Commit after each task or logical group.
