# Data Model: Knowledge Discovery Graph

## Graph Nodes (Memgraph)

| Node | Key | Properties | Validation |
|------|-----|------------|------------|
| `Workspace` | `project_id` | name, owner, created_at | must match an existing project |
| `DataResource` | `(project_id, resource_id)` | format, tier (BRONZE/SILVER/GOLD), record_count, location_uri, kind (tabular/json/text/graph), index_version, indexed_at | tier in enum; record_count ≥ 0 |
| `DataAttribute` | `(project_id, resource_id, name)` | physical_type, inferred_type, cardinality (0–1), null_ratio, pattern (uuid/ip/email/…), sample_size | cardinality in [0,1] |
| `GenericEntity` | `(entity_type, normalized_value, project_id)` | entity_id, entity_type, value, normalized_value, canonical_id, source (pattern/ner/column) | entity_type non-empty; value ≤ 512 chars |
| `SemanticTaxonomy` | `concept_id` | name, description | name unique |
| `PipelineExecution` | `run_id` | pipeline_id, project_id, status, executed_at | status in enum |

## Relationships

| Edge | From → To | Properties |
|------|-----------|-----------|
| `OWNS_RESOURCE` | Workspace → DataResource | – |
| `HAS_ATTRIBUTE` | DataResource → DataAttribute | – |
| `MAPS_TO_TAXONOMY` | DataAttribute → SemanticTaxonomy | confidence, low_confidence |
| `CONTAINS_ENTITY` | DataResource → GenericEntity | attribute, occurrences |
| `SAME_AS` | GenericEntity ↔ GenericEntity | confidence, method (exact/fuzzy) |
| `DERIVED_FROM` | DataResource → DataResource | via_run_id |
| `READS_FROM` / `WRITES_TO` | PipelineExecution → DataResource | – |
| `PROCESSED_BY` | DataResource → PipelineExecution | – |

Indexes: `:DataResource(project_id)`, `:DataAttribute(project_id)`, `:GenericEntity(project_id)`, `:GenericEntity(normalized_value)`, `:GenericEntity(entity_type)`, `:SemanticTaxonomy(name)`.

## Relational (PostgreSQL): `kdg_index_jobs`

| Column | Type | Notes |
|--------|------|-------|
| job_id | UUID PK | |
| project_id | text | indexed |
| resource_id | text | |
| phase | enum(structural, enrichment) | |
| status | enum(pending, running, completed, failed, skipped_no_ai) | |
| attempts | int | max 3 |
| error | text null | surfaced to users (FR-019) |
| created_at / updated_at | timestamp | |

**State transitions**: `pending → running → completed | failed`; `failed → pending` (retry, attempts < 3); `pending → skipped_no_ai` when AI unavailable; reindex creates a new job.

## Relational (PostgreSQL): `project_members`

| Column | Type | Notes |
|--------|------|-------|
| project_id | VARCHAR(64) FK → projects | PK part; cascade delete |
| user_id | VARCHAR(64) | PK part; JWT `sub` |
| role | enum(owner, member) | at least one owner per project |
| added_by | VARCHAR(64) | |
| added_at | timestamp | |

**Rules**: creator inserted as `owner` on project creation; only owners (or `admin` role) add/remove members; the last owner cannot be removed; legacy projects without rows are visible only to `admin` until an owner is set (spec assumption). Membership is read per request (no caching beyond the request) so changes apply immediately (FR-022).

## Pydantic Contracts (`src/domains/discovery/models/contract/discovery.py`)

- `WorkspaceKnowledgeContract`: project_id, resources[`ResourceKnowledge`], entity_type_counts, enrichment_status.
- `ResourceKnowledge`: resource_id, format, tier, record_count, attributes[`AttributeKnowledge`], entity_counts, derived_from[].
- `AttributeKnowledge`: name, physical_type, inferred_type, taxonomy (nullable), confidence (nullable), low_confidence.
- `EntityCorrelationContract`: query, matches[`EntityMatch`(project_id, resource_id, tier, attribute, entity_type, match_method, confidence)], total_projects.
- `LineageContract`: resource_id, project_id, nodes[`LineageNode`], edges[`LineageEdge`], is_root.
- `IndexJobContract`: job_id, project_id, resource_id, phase, status, attempts, error.
- `MemberContract` / `MemberAddRequestContract` (`src/domains/project/models/contract/membership.py`): project_id, user_id, role.
