# Feature Specification: Knowledge Discovery Graph

**Feature Branch**: `005-knowledge-discovery-graph`

**Created**: 2026-10-19

**Status**: Draft

**Input**: User description: "Build a Universal, Domain-Agnostic Knowledge Discovery Graph (KDG) as described in docs/architecture/ideas/knowledge_discovery_graph.md: a federated semantic meta-layer that automatically catalogs datasets, attributes, entities and lineage inside each project workspace and enables discovery of shared entities and lineage across projects, usable via CLI, API and natural-language questions."

## Clarifications

### Session 2026-10-19

- Q: Which projects' matches may a user see in cross-project entity search? → A: Only matches in projects the user is a member of; matches elsewhere are hidden entirely.
- Q: How is a user's membership of a project determined? → A: A minimal per-project membership list is added; the creator is the owner, and owners can add or remove members.
- Q: Can users review or reject uncertain entity links in v1? → A: No; links show a confidence score and match method only. Review/reject is out of scope for v1.
- Q: How is the natural-language answer accuracy target checked? → A: A fixed set of about 20 question/answer pairs run with the AI mocked, plus a manual live check.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Discover What Exists Inside a Project (Priority: P1)

An analyst opens a project workspace and wants to know which datasets, fields and real-world entity types it holds, without any manual cataloging. When data is ingested (tabular, semi-structured, or unstructured text), the platform automatically builds a searchable knowledge summary for that project.

**Why this priority**: It is the foundation for everything else and delivers standalone value: without a per-project index, cross-project discovery is impossible and natural-language questions about project contents fail.

**Independent Test**: Ingest a tabular dataset and a text document into one project, run the project discovery command, and verify the summary lists both resources, their attributes/types, storage tier, record counts, and extracted entity counts.

**Acceptance Scenarios**:

1. **Given** a project with an ingested tabular dataset, **When** the analyst requests a project knowledge summary, **Then** the summary lists the dataset, its tier and format, record count, each attribute with its detected type, and any semantic concept assigned to attributes.
2. **Given** a project with an unstructured text document, **When** ingestion completes, **Then** entities (people, organizations, locations, identifiers, etc.) found in the text appear in the project summary with their types.
3. **Given** a newly ingested dataset, **When** the analyst requests the summary immediately, **Then** structural information (resources, attributes, types) is already available, and richer enrichment (entities, semantic mapping) appears once background processing finishes.
4. **Given** a project with no ingested data, **When** the analyst requests a summary, **Then** a clear empty-state message is shown.

---

### User Story 2 - Find a Shared Entity Across Projects (Priority: P2)

An investigator has an identifier (e.g., an account number or device serial) and wants to learn which projects and datasets mention it, without being able to directly query other projects' raw data.

**Why this priority**: This is the core cross-project value, yielding hidden correlations; it depends on Story 1's index.

**Independent Test**: Ingest data containing the same identifier into two projects, search for the value, and verify both projects, datasets and fields are returned with no raw record content from other projects.

**Acceptance Scenarios**:

1. **Given** the same entity value exists in two projects, **When** the investigator searches for that value, **Then** matches in both projects are returned with project, dataset, tier and field.
2. **Given** an entity value that appears nowhere, **When** searched, **Then** a "no matches" result is returned.
3. **Given** near-identical values (e.g., typos or formatting differences), **When** entity linking runs, **Then** they are recognized as the same real-world entity and the match is reported with a confidence indication.
4. **Given** cross-project discovery, **When** results are shown, **Then** only metadata (locations, field names, entity links) is exposed, and only for projects the user is a member of; underlying raw data stays confined to its own project.
5. **Given** a value that also exists in a project the user is not a member of, **When** the user searches for it, **Then** no trace of that project (name, count, or existence) appears in the results.

---

### User Story 3 - Trace Data Lineage (Priority: P3)

An analyst wants to see where a dataset came from and which pipeline runs produced it, both within one project and across projects.

**Why this priority**: Provenance builds trust in results but is useful only after resources are cataloged.

**Independent Test**: Run a pipeline that derives a Gold dataset from a Bronze dataset, request lineage for the Gold dataset, and verify the source dataset and pipeline run are shown.

**Acceptance Scenarios**:

1. **Given** a derived dataset, **When** lineage is requested, **Then** a provenance tree shows upstream datasets and the pipeline executions (with status and time) that connect them.
2. **Given** a dataset with no known origin, **When** lineage is requested, **Then** it is shown as a root source.

---

### User Story 4 - Ask Discovery Questions in Natural Language (Priority: P4)

An analyst asks the AI assistant questions such as "Which projects contain datasets referencing customer accounts flagged for high risk?" and receives answers grounded in the knowledge graph.

**Why this priority**: Convenience layer built on Stories 1-3.

**Independent Test**: With indexed data in two projects, ask a discovery question and verify the answer cites the correct projects and datasets.

**Acceptance Scenarios**:

1. **Given** indexed projects, **When** the analyst asks what datasets and columns a project contains, **Then** the answer reflects the project's knowledge summary.
2. **Given** an entity present in multiple projects, **When** asked which projects reference it, **Then** the answer lists those projects.
3. **Given** a question about a dataset's origin, **When** asked, **Then** the answer reflects the lineage tree.

---

### Edge Cases

- Data with ambiguous or meaningless field names (e.g., `col_1`): the platform infers meaning from sample values; low-confidence mappings are flagged rather than asserted.
- Very large or wide datasets: indexing must not block ingestion; the dataset becomes available immediately and discovery info completes asynchronously.
- AI enrichment unavailable (no API key / outage): structural and pattern-based discovery still works; enrichment is retried or marked pending.
- Ingestion of unsupported or corrupt files: ingestion outcome is unaffected, and the indexing failure is recorded and visible.
- Deleted or re-ingested datasets: index entries are updated or removed so no stale results appear.
- Entities with conflicting types across projects, or falsely similar values: links carry a confidence score and match method so users can judge them; review or rejection of links is out of scope for v1.
- A user requests discovery for a non-existent project: clear error.
- Sensitive entity values: discovery output respects project access boundaries; a user who loses membership of a project immediately stops seeing its matches, summaries and lineage.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST automatically index every dataset ingested into a project (tabular, semi-structured, unstructured text, graph payloads) without manual cataloging.
- **FR-002**: System MUST record for each dataset: owning project, format, storage tier, record count, and location.
- **FR-003**: System MUST record each dataset's attributes with physical type, inferred type, and cardinality.
- **FR-004**: System MUST detect common universal value patterns (identifiers, timestamps, geographic coordinates, network addresses, emails, phone numbers) deterministically, without relying on AI.
- **FR-005**: System MUST extract named entities (people, organizations, locations, products, identifiers, concepts) from unstructured text and from ambiguous attributes using AI-assisted extraction.
- **FR-006**: System MUST group semantically similar attributes (e.g., `client_number` and `customer_id`) under shared semantic concepts.
- **FR-007**: System MUST link identical or near-identical entities across projects as the same real-world entity, with a confidence indication.
- **FR-008**: System MUST record dataset lineage (derived-from) and pipeline execution provenance (inputs, outputs, status, time).
- **FR-009**: Indexing MUST run in two phases: fast deterministic structural indexing available promptly after ingestion, followed by asynchronous AI/similarity enrichment that does not block ingestion.
- **FR-010**: Users MUST be able to request a knowledge summary for a single project via the CLI.
- **FR-011**: Users MUST be able to search for an entity value or type across all projects via the CLI.
- **FR-012**: Users MUST be able to retrieve lineage for any dataset.
- **FR-013**: CLI discovery commands MUST support human-readable and machine-readable (`--json`) output.
- **FR-014**: Discovery capabilities MUST also be available through the programmatic API.
- **FR-015**: The AI assistant MUST be able to answer questions about project contents, cross-project entity occurrences, and lineage using the knowledge graph.
- **FR-016**: Cross-project discovery MUST expose only metadata and entity links; it MUST NOT permit direct reading of another project's raw data, preserving existing project isolation.
- **FR-017**: System MUST keep the index consistent when datasets are re-ingested or removed.
- **FR-018**: System MUST degrade gracefully when AI enrichment is unavailable, retaining structural and pattern-based discovery and recording pending enrichment.
- **FR-019**: Indexing failures MUST NOT cause ingestion failures and MUST be observable to users.
- **FR-020**: System MUST NOT assume any domain-specific schema; it must work for arbitrary data domains.
- **FR-021**: Cross-project search, lineage and AI-assistant discovery answers MUST be limited to projects the requesting user is a member of; matches in other projects MUST be omitted entirely, including from counts and totals.
- **FR-022**: Each project MUST have a membership list; the project creator is its owner and first member, and owners MUST be able to add and remove members via the CLI and API (listing members supports `--json`). Membership changes take effect on the next request.

### Key Entities

- **Workspace (Project)**: An isolated tenant workspace that owns datasets (the graph node is named `Workspace`; "project" is the user-facing term).
- **Data Resource**: A dataset, file, stream or document in a storage tier, with format, record count and location.
- **Data Attribute**: A column, key or field within a resource, with physical/inferred type and cardinality.
- **Generic Entity**: A real-world value (person, organization, location, device, identifier, code) extracted from a resource; can be linked to equivalent entities in other projects.
- **Semantic Taxonomy Concept**: A shared concept unifying equivalent attributes across datasets.
- **Pipeline Execution**: A provenance record of a transformation run linking input and output resources.
- **Entity Link / Lineage Link**: Relationships connecting equivalent entities (with confidence) and derived datasets.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An analyst can get a complete structural summary of a project (datasets, attributes, types) within 5 seconds of requesting it, without prior manual setup.
- **SC-002**: Structural index of a newly ingested dataset is available within 30 seconds of ingestion completing, for datasets up to 1 million rows.
- **SC-003**: A cross-project entity search returns results in under 3 seconds across at least 50 projects.
- **SC-004**: Ingestion throughput and completion time degrade by no more than 10% with indexing enabled.
- **SC-005**: At least 90% of known shared entities in a validation dataset are correctly linked across projects, with false links below 5%.
- **SC-006**: 100% of cross-project discovery results contain no raw record content from other projects, and 0% reference projects the requesting user is not a member of.
- **SC-007**: At least 85% of a fixed validation set of about 20 discovery questions (project contents, cross-project entities, lineage) receive correct answers from the AI assistant, measured with the AI service mocked, and confirmed by a manual check against the live service.
- **SC-008**: Discovery works end to end on at least three unrelated data domains (e.g., healthcare, finance, IoT) without domain-specific configuration.
- **SC-009**: Total platform idle memory stays within the project's existing budget after the feature is added.

## Assumptions

- Existing ingestion, project isolation, graph store, analytical store and AI assistant capabilities are reused; this feature extends them.
- The platform has no project membership model yet; a minimal one (owner plus member list, evaluated per request, see FR-022) is added as part of this work. Roles beyond owner/member and finer-grained control inside a project (per dataset or field) are out of scope for v1.
- Projects created before this feature are assigned their creator as owner; where the creator is unknown, they are visible only to administrators until an owner is set.
- AI enrichment relies on the existing external AI service; offline operation provides structural and pattern-based discovery only.
- Supported v1 data kinds: tabular, JSON/semi-structured, plain-text documents, and graph payloads; media content analysis is out of scope.
- Community detection and centrality ranking are optional enhancements, not required for v1.
- Adheres to the project constitution: modular domain, unified CLI with `--json`, integration tests, and no JVM-based components.
- Existing data ingested before this feature is not indexed automatically unless a reindex is requested.
