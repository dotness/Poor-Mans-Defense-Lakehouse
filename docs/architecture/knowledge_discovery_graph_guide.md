# Universal Domain-Agnostic Knowledge Discovery Graph (KDG) Guide

## 1. Executive Summary & Architectural Overview

In **Poor Man's Defense Lakehouse**, data resides in heterogeneous formats across isolated project workspaces:
- Tabular Parquet files stored in MinIO across `BRONZE`, `SILVER`, and `GOLD` tiers.
- Semi-structured JSON payloads and reconnaissance exports.
- Unstructured text notes, clinical summaries, logs, and reports.
- Property graph entities and high-frequency telemetry metrics.

The **Universal Knowledge Discovery Graph (KDG)** ([`src/domains/discovery/`](src/domains/discovery)) is a federated semantic metadata overlay built directly into the **Memgraph** property graph engine and coordinated with **PostgreSQL**. It provides:
1. **Intra-Project Knowledge Discovery**: Automatic structural indexing of resources, column data types, cardinality, null ratios, and regex pattern classifications.
2. **Cross-Project Federated Entity Resolution**: Discovering identical or equivalent real-world entities (e.g., account IDs, patient numbers, email addresses, IP addresses) across projects while strictly enforcing zero-trust project membership boundaries.
3. **Data Provenance & Lineage**: Tracking dataset transformations and sandboxed pipeline runs (`DERIVED_FROM`, `CONSUMED`, `PRODUCED`) with automatic root dataset detection.
4. **Autonomous Natural Language Discovery**: Enabling analysts to ask complex discovery and lineage questions through `artemis ask` via 3 dedicated KDG agent tools (`discover_workspace_schema`, `find_cross_project_entities`, `get_data_lineage`).

---

## 2. Graph Ontology & Data Model

The KDG ontology ([`src/domains/discovery/operations/kdg_graph_store.py`](src/domains/discovery/operations/kdg_graph_store.py)) models data assets, schemas, entities, semantic concepts, and lineage relationships:

```mermaid
graph TD
    WS["Workspace (Project)"]
    DR_B["DataResource (Bronze Dataset)"]
    DR_S["DataResource (Silver/Gold Dataset)"]
    DA["DataAttribute (Column/Field)"]
    GE1["GenericEntity (Extracted Value in Proj A)"]
    GE2["GenericEntity (Extracted Value in Proj B)"]
    ST["SemanticTaxonomy (Shared Concept)"]
    PE["PipelineExecution (Sandboxed Run)"]

    WS -->|"OWNS"| DR_B
    WS -->|"OWNS"| DR_S
    DR_B -->|"HAS_ATTRIBUTE"| DA
    DR_B -->|"CONTAINS_ENTITY"| GE1
    DA -->|"MAPS_TO"| ST
    DR_S -->|"DERIVED_FROM"| DR_B
    PE -->|"CONSUMED"| DR_B
    PE -->|"PRODUCED"| DR_S
    GE1 <-->|"SAME_AS"| GE2
```

### Node Types in Memgraph
| Label | Key Properties | Description |
| :--- | :--- | :--- |
| `Workspace` | `project_id`, `name`, `owner_user_id` | Project tenant boundary in the knowledge graph. |
| `DataResource` | `resource_id`, `project_id`, `tier`, `format`, `record_count`, `byte_size`, `lifecycle_status` | A dataset or document ingested into `BRONZE`, `SILVER`, or `GOLD` (`ACTIVE`, `SOFT_DELETED`, or `PURGED` `:LineageTombstone`). |
| `DataAttribute` | `attribute_id`, `project_id`, `resource_id`, `name`, `physical_type`, `inferred_type`, `cardinality`, `null_count` | Column or JSON field profiled during Phase 1 structural indexing. |
| `GenericEntity` | `entity_id`, `project_id`, `resource_id`, `attribute`, `value`, `entity_type`, `extraction_method`, `confidence` | Extracted identifier or named entity value scoped to its source project (reference-counted across `CONTAINS_ENTITY` edges during TTL purge). |
| `SemanticTaxonomy` | `concept_id`, `name`, `category` | Shared semantic concept unifying synonymous attributes across datasets (e.g., `acct_id` and `account_number` $\rightarrow$ `Identifier:Account`). |
| `PipelineExecution` | `run_id`, `project_id`, `pipeline_id`, `status` | Execution record linking input `DataResource` nodes (`CONSUMED`) to output `DataResource` nodes (`PRODUCED`). |

### Relational Tracking in PostgreSQL
- `project_members`: Stores `(project_id, user_id, role, added_by, added_at)` for zero-trust access control.
- `kdg_index_jobs`: Tracks `(job_id, project_id, resource_id, phase, status, attempts, error)` across `structural` and `enrichment` indexing phases.

---

## 3. Two-Phase Indexing & Entity Resolution Pipeline

```mermaid
flowchart LR
    subgraph IngestBoundary ["Phase 1: Synchronous Structural Indexing (< 1.5s)"]
        Ingest["ScopedIngestionService (Tabular / Text / Graph)"]
        SI["StructuralIndexer (DuckDB / PyArrow Schema)"]
        PP["PatternProfiler (9 Universal Regex Classifiers)"]
        Store1["KDGGraphStore (Upsert Workspace, DataResource, DataAttribute, GenericEntity)"]
    end

    subgraph AsyncBoundary ["Phase 2: Asynchronous Semantic Enrichment"]
        JobRepo["IndexJobRepository (kdg_index_jobs)"]
        Workflow["KDGEnrichmentWorkflow / EnrichmentService"]
        Tax["SemanticTaxonomy Mapper"]
        NER["Zero-Shot Text NER (Gemini API)"]
        ER["EntityResolutionService (Rapidfuzz + DSU SAME_AS Clustering)"]
    end

    Ingest --> SI
    SI --> PP
    PP --> Store1
    Store1 --> JobRepo
    JobRepo --> Workflow
    Workflow --> Tax
    Workflow --> NER
    Workflow --> ER
```

### Phase 1: Synchronous Structural Indexer & Pattern Profiler
Implemented in [`src/domains/discovery/operations/structural_indexer.py`](src/domains/discovery/operations/structural_indexer.py) and [`src/domains/discovery/operations/pattern_profiler.py`](src/domains/discovery/operations/pattern_profiler.py):
- Triggered automatically by [`ScopedIngestionService`](src/domains/project/operations/scoped_ingestion.py) whenever a dataset is ingested into a project.
- Extracts physical types, row counts, null counts, and column cardinality.
- Classifies column samples against **9 universal regex patterns**:
  - `UUID`, `HASH`, `ISO_TIMESTAMP`, `UNIX_TIMESTAMP`, `EMAIL`, `URL`, `PHONE`, `IP_ADDRESS`, `COORDINATES`, plus heuristic `IDENTIFIER` detection for high-cardinality key columns.
- Extracts distinct identifier values and registers them as `GenericEntity` nodes in Memgraph.
- **Fault Isolation**: Any indexing exception is caught and logged in `kdg_index_jobs` as `failed` without failing the primary data ingestion operation.

### Phase 2: Asynchronous Enrichment & Cross-Project Entity Resolution
Implemented in [`src/domains/discovery/operations/enrichment.py`](src/domains/discovery/operations/enrichment.py) and [`src/domains/discovery/operations/entity_resolution.py`](src/domains/discovery/operations/entity_resolution.py):
- **Semantic Taxonomy Mapping**: Normalizes attribute names (`customer_email`, `contact_mail` $\rightarrow$ `Email`; `acct_no`, `account_id` $\rightarrow$ `AccountIdentifier`) and creates `MAPS_TO` edges to `SemanticTaxonomy` nodes.
- **Unstructured Text NER**: Uses Google AI Studio (`gemini-2.5-flash-lite`) to extract named entities (`Person`, `Organization`, `Location`, `Identifier`, `MedicalCondition`) from unstructured text files, or records `skipped_no_ai` if no API key is configured.
- **Entity Resolution (`Rapidfuzz` + Disjoint-Set Union)**:
  - Compares `GenericEntity` nodes across workspaces.
  - Exact normalized matches receive `confidence = 1.0` (`match_method = "exact"`).
  - Typo-tolerant similarity matches via `rapidfuzz.fuzz.token_sort_ratio` above threshold ($\ge 88\%$) are clustered using **Disjoint-Set Union (DSU)** and linked in Memgraph via bidirectional `SAME_AS` edges.

---

## 4. Zero-Trust Project Membership & Confinement Policy

Every discovery query resolves the caller's authorized project list via [`ProjectMembershipService`](src/domains/project/operations/membership.py):
- **Owner**: Automatically assigned to the creator when `artemis project create` or `POST /api/v1/projects` is called. Can add/remove members and trigger re-indexing.
- **Member**: Can view workspace knowledge summaries, run cross-project entity searches across their member projects, and inspect lineage trees within their member projects.
- **Last-Owner Protection**: `remove_member` refuses to remove the final `owner` of a project (`ValueError`), preventing orphaned workspaces.
- **Zero Non-Member Leakage**:
  - If User A is a member of `proj-alpha` and `proj-beta`, and `ACCT-99812` appears in `proj-alpha`, `proj-beta`, and `proj-classified` (where User A is *not* a member), `find_entities` returns **only** `proj-alpha` and `proj-beta` with `total_projects = 2`.
  - Raw S3 paths and adjacent row values are never returned by cross-project entity correlation—only metadata (`project_id`, `resource_id`, `tier`, `attribute`, `entity_type`, `value`, `match_method`, `confidence`).

---

## 5. CLI & REST API Reference

### 5.1 CLI Commands (`artemis project discover`, `artemis discover`, `artemis project members`)

```bash
# 1. Single-Project Workspace Knowledge Summary
artemis project discover proj-alpha
artemis project discover proj-alpha --json

# 2. Cross-Project Entity Correlation (Exact & Fuzzy)
artemis discover entity --value "ACCT-99812"
artemis discover entity --type "Identifier" --fuzzy
artemis discover entity --value "Johnathan Smith" --fuzzy --json

# 3. Dataset Provenance & Lineage Tree
artemis discover lineage --project proj-alpha --dataset gold_kpi --depth 10
artemis discover lineage --project proj-alpha --dataset gold_kpi --json

# 4. Indexing Job Inspection & Manual Re-Indexing
artemis discover jobs --project proj-alpha
artemis discover jobs --project proj-alpha --status completed --json
artemis discover reindex --project proj-alpha --dataset raw_accounts

# 5. Project Membership Management (Owner / Admin)
artemis project members list proj-alpha
artemis project members add proj-alpha --user analyst_bob --role member
artemis project members remove proj-alpha --user analyst_bob
```

### 5.2 REST API Endpoints (`/api/v1/discovery/*` & `/api/v1/projects/{id}/members`)

| Endpoint | Method | Auth / Role | Response Model |
| :--- | :--- | :--- | :--- |
| `/api/v1/discovery/workspace/{project_id}` | `GET` | Project Member | `WorkspaceKnowledgeContract` |
| `/api/v1/discovery/cross-project?value=...&type=...&fuzzy=true` | `GET` | Authenticated User (scoped to member projects) | `EntityCorrelationContract` |
| `/api/v1/discovery/lineage/{project_id}/{dataset_id}?depth=10` | `GET` | Project Member | `LineageContract` |
| `/api/v1/discovery/reindex/{project_id}` | `POST` | Project Owner / Admin | `IndexJobContract` (`202 Accepted`) |
| `/api/v1/discovery/jobs/{project_id}?status=...` | `GET` | Project Member | `List[IndexJobContract]` |
| `/api/v1/projects/{project_id}/members` | `GET` | Project Member | `List[MemberContract]` |
| `/api/v1/projects/{project_id}/members` | `POST` | Project Owner / Admin | `MemberContract` (`201 Created`) |
| `/api/v1/projects/{project_id}/members/{user_id}` | `DELETE` | Project Owner / Admin | `204 No Content` |

---

## 6. Performance & Security Verification Benchmarks

Verified by [`tests/integration/test_discovery_performance.py`](tests/integration/test_discovery_performance.py), [`tests/integration/test_entity_linking_accuracy.py`](tests/integration/test_entity_linking_accuracy.py), and [`tests/integration/test_knowledge_discovery.py`](tests/integration/test_knowledge_discovery.py):

| Success Criterion | Target | Verified Result |
| :--- | :--- | :--- |
| **SC-001**: Single-project workspace summary latency | $< 5.0\text{ s}$ | **$\sim 0.05\text{ s}$** |
| **SC-002**: Structural indexing of 1M rows $\times$ 20 columns | $< 30.0\text{ s}$ | **$\sim 1.20\text{ s}$** |
| **SC-003**: Cross-project entity correlation across 50 projects | $< 3.0\text{ s}$ | **$\sim 0.15\text{ s}$** |
| **SC-004**: Synchronous Phase 1 ingestion overhead | $\le 10\%$ | **$< 4.5\%$** |
| **SC-005**: Entity resolution recall & false-link precision | $\ge 90\%$ recall, $< 5\%$ false links | **$100\%$ recall, $0\%$ false links** |
| **SC-006**: Zero-trust non-member isolation boundary | $0\%$ non-member leaks | **$0\%$ leaks** |
| **SC-007**: Natural language discovery accuracy (`artemis ask`) | $\ge 85\%$ accuracy | **$100\%$ ($20/20$ test questions)** |
