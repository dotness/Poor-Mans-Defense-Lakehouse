# Feature Specification: Dataset & Query Data TTL Management and Automated Cleanup

**Feature Branch**: `009-dataset-ttl-cleanup`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "new feature to set ttl of data and auto-cleanup that will cleanup out of date data. It is to.be set per data set and query data as well. Use data platform best practices for such feature. Ask me questions if needed."

## Clarifications

### Session 2026-11-21

- Q: How should TTL apply to "query data" and active queries when dataset data has expired? → A: Both Query Artifacts TTL & Read-Time Filtering — query outputs (cached SQL/AI results, materialized query exports, and query audit history) have configurable TTLs, and live queries automatically filter out expired datasets/partitions/rows at read time even before the background purge runs.
- Q: At what granularity should dataset TTL expiration be evaluated and cleaned up? → A: Configurable per dataset: defaults to whole-dataset/partition age (based on ingestion time), with an optional per-dataset `timestamp_column` setting to filter and purge individual expired rows/time-partitions in streaming or append-only telemetry datasets.
- Q: When data reaches its TTL expiration, what deletion lifecycle should auto-cleanup follow? → A: Two-stage soft-delete (`SOFT_DELETED`) with a configurable grace period (e.g., 24h default, or `0h` for immediate purge) before permanent physical deletion across storage and graph, allowing recovery from accidental TTL misconfigurations while preserving lineage tombstones.
- Q: How should a user restore a soft-deleted dataset or query artifact during its grace period before permanent purge? → A: Both explicit and implicit restoration — support an explicit `restore` command (CLI/API) that transitions the item to `ACTIVE` (with TTL extension or Retention Hold to prevent immediate re-expiration) AND automatically restore a `SOFT_DELETED` item if an authorized user updates its TTL to a non-expired duration or enables a Retention Hold.
- Q: When a dataset uses `timestamp_column` row-level TTL and some rows in a file have expired, how should physical cleanup and soft-delete recovery work for those expired rows? → A: Virtual soft-delete during the grace period — rows older than `now - TTL` are hidden at query time via read-time filtering, and physical Parquet file compaction/rewrite is deferred until `TTL + grace_period` elapses (requiring only a single atomic file rewrite and allowing instant restoration during the grace period).
- Q: When an analyst executes raw SQL or Cypher queries (`artemis query` / `artemis project query`) against datasets with active TTL policies, how should read-time TTL enforcement behave? → A: Transparent query-layer interception — the query service resolves dataset paths excluding expired/`SOFT_DELETED` files and automatically applies `timestamp_column >= now - TTL` filters (and graph node/edge expiration filters) to both raw SQL/Cypher and dataset-named queries.
- Q: What happens when a cached query result or materialized query export still has time remaining on its own TTL, but an underlying source dataset it was derived from expires or is purged? → A: Split by artifact type — ephemeral SQL/AI query caches are immediately invalidated when any underlying source dataset expires, while explicit materialized query exports (and query audit logs) follow their own assigned TTL independently once created.
- Q: When an existing dataset is re-ingested or appended to with new records, how should its whole-dataset TTL reference timestamp behave? → A: Per-file/partition ingestion clock — overwriting a dataset resets its TTL reference timestamp to the new ingestion time, while appending new batch files tracks `ingested_at` per partition/file so older batch files expire on schedule without deleting newly appended files.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Per-Dataset Retention (TTL) Configuration (Priority: P1)

As a project owner or data analyst, I need to configure, view, and update a Time-To-Live (TTL) policy for any dataset (tabular, semi-structured, or graph) within a project—or inherit a tier/project default—so that data lifecycles are explicitly governed according to operational and compliance requirements.

**Why this priority**: Foundation for all retention and cleanup behaviors. Without per-dataset TTL metadata and policy resolution (dataset override vs. tier/project default), neither query-time filtering nor automated cleanup can operate.

**Independent Test**: Configure a TTL policy on an existing dataset via the CLI or API, inspect the dataset metadata, and verify the effective TTL, expiration reference rule, and calculated expiration status are accurately persisted and returned.

**Acceptance Scenarios**:

1. **Given** an existing dataset in a project, **When** a project owner sets a TTL duration (e.g., `30d`, `24h`, or `never` for permanent retention) on that dataset, **Then** the system persists the policy and displays the active TTL and next expiration boundary when inspected.
2. **Given** a new dataset being ingested without an explicit TTL parameter, **When** ingestion completes, **Then** the system automatically assigns the default TTL for that storage tier (Bronze, Silver, or Gold) or project.
3. **Given** a dataset with an active TTL policy, **When** an authorized user updates or removes the TTL policy, **Then** the system immediately recalculates the dataset's expiration status using the new duration.
4. **Given** an invalid TTL format or duration below the platform minimum (e.g., negative or zero duration), **When** a user attempts to apply it, **Then** the system rejects the request with a clear validation error.

---

### User Story 2 - Query Result & Query Artifact TTL Governance (Priority: P1)

As a data analyst or platform administrator, I need TTL policies applied to "query data"—including cached analytical query results, AI assistant semantic query caches, materialized query exports, and query execution history—and I need analytical queries to respect data expiration boundaries so that out-of-date data is neither served to analysts nor left accumulating indefinitely.

**Why this priority**: Directly addresses the core requirement that TTL applies to "query data as well" and prevents stale data exposure between background cleanup cycles.

**Independent Test**: Execute an analytical query that produces cached/stored query data with a configured TTL, verify the query data is accessible before expiration, and confirm that after the TTL elapses it is automatically excluded from responses and slated for cleanup.

**Acceptance Scenarios**:

1. **Given** an analytical or natural-language query execution, **When** query results, semantic cache entries, or materialized query outputs are stored, **Then** the system attaches a configurable query-data TTL (with a user-overridable duration up to the project maximum).
2. **Given** a dataset, partition, or row (when `timestamp_column` is configured) whose TTL has expired but has not yet been physically purged by the background cleanup worker, **When** an analyst executes a query against that dataset, **Then** the query engine automatically filters out and excludes the expired dataset, partition, or rows at read time so stale data is never returned.
3. **Given** cached query results whose TTL has elapsed, **When** an identical query is submitted, **Then** the system bypasses the expired cache entry, computes fresh results from active data, and stores a new TTL-bound entry.

---

### User Story 3 - Automated Background Cleanup & Safe Purge Workflow (Priority: P2)

As a platform administrator, I need an automated background cleanup process—as well as an on-demand CLI/API trigger with a dry-run preview—that safely identifies and purges out-of-date dataset data, associated knowledge graph nodes/edges, and expired query artifacts while maintaining cross-store consistency and an immutable audit trail.

**Why this priority**: Automates storage reclamation and compliance enforcement across tabular storage, graph storage, discovery indexes, and query caches without manual intervention.

**Independent Test**: Create a dataset and query cache entry with a short TTL, allow them to expire, trigger the cleanup job in dry-run mode to verify impact preview, then run the live cleanup job and verify storage objects, graph elements, and catalog entries are purged and an audit log is recorded.

**Acceptance Scenarios**:

1. **Given** expired datasets, partitions, or query artifacts across projects, **When** the scheduled auto-cleanup cycle runs (or is triggered on-demand), **Then** the system removes the expired data across object storage, knowledge graph entities/edges, discovery catalog indexes, and query caches in a coordinated manner.
2. **Given** a user requesting a cleanup preview (`--dry-run`), **When** the dry-run executes, **Then** the system reports all datasets, partitions, graph nodes, and query artifacts that would be purged—along with estimated storage bytes reclaimed—without modifying or deleting any data.
3. **Given** an active pipeline run or query currently reading a dataset that reaches expiration, **When** the auto-cleanup job runs concurrently, **Then** the system safely skips or defers deletion of in-use data until the active operation finishes, preventing read corruption.
4. **Given** a completed auto-cleanup cycle, **When** an administrator inspects cleanup history, **Then** the audit record lists the run timestamp, items evaluated, items purged, bytes reclaimed, duration, and any skipped/failed items.

---

### User Story 4 - Legal Hold, Grace Period & Lifecycle Observability (Priority: P3)

As a project owner or compliance officer, I need to place datasets on temporary retention hold (pausing auto-cleanup during active investigations) and follow data platform lifecycle best practices for deletion safety so that critical investigative data is never accidentally lost.

**Why this priority**: Essential data platform best practice to prevent catastrophic, irreversible data loss from misconfigured TTLs or active incidents.

**Independent Test**: Enable a retention hold on an expired dataset, run the auto-cleanup job, and verify the dataset is skipped and logged as held; release the hold and verify the next cleanup cycle processes it according to the configured deletion lifecycle.

**Acceptance Scenarios**:

1. **Given** a dataset with an active TTL policy, **When** a project owner places a retention hold (`hold = true`) on the dataset, **Then** automated and on-demand cleanup jobs skip the dataset and flag it as "Held" in cleanup reports.
2. **Given** a dataset reaching its TTL expiration timestamp, **When** the cleanup process evaluates the expired data, **Then** the system performs a two-stage deletion lifecycle: first transitioning the data to `SOFT_DELETED` (immediately hidden from queries and recoverable during a configurable grace period, defaulting to 24 hours or `0h` for immediate purge), and then permanently hard-deleting physical storage, graph elements, and catalog entries once the grace period elapses.
3. **Given** a dataset or query artifact in `SOFT_DELETED` state within its grace period, **When** an authorized user invokes the explicit `restore` action (specifying an extended TTL or hold) or updates the item's TTL to a non-expired duration or applies a Retention Hold, **Then** the system restores the item to `ACTIVE` status and makes it immediately queryable again.
4. **Given** a project workspace, **When** an analyst views the project retention summary via CLI or API, **Then** the system displays all datasets, their TTL rules, current age, time remaining until expiration, hold status, and datasets expiring within the next 24 hours.

---

### Edge Cases

- **Granularity of Dataset Expiration**: Datasets may be ingested as monolithic batch snapshots or append-only time-series telemetry streams; expiration evaluation defaults to whole-dataset/partition age based on ingestion timestamp, and supports an optional per-dataset `timestamp_column` configuration to evaluate, filter at query time, and purge expired records/time-partitions based on event timestamps. For `timestamp_column` datasets with partially expired files, rows older than `now - TTL` are virtually soft-deleted (excluded via read-time filtering) during the grace period, and physical Parquet compaction/rewrite is performed once after `TTL + grace_period` elapses (or the entire file is dropped if all rows in the file exceed `TTL + grace_period`).
- **Shared Graph Entities Across Datasets/Projects**: When an expired dataset is purged, knowledge graph nodes or discovery entities that were also referenced by another active (non-expired) dataset must have only the expired dataset's provenance references removed; nodes/edges are physically deleted only when zero active dataset references remain.
- **Partial Failure Across Multi-Store Cleanup**: If deleting an expired dataset succeeds in object storage but encounters a transient error when cleaning up graph metadata or catalog state, the item must be marked in a `CLEANUP_PENDING_RETRY` state so subsequent runs idempotently complete the purge without leaving orphaned pointers.
- **Clock Skew & Boundary Timestamps**: Expiration evaluation must use monotonically consistent UTC server timestamps; data ingested with future-dated event timestamps (if row/partition-based) must not prematurely expire or cause integer underflow.
- **Lineage Preservation After Purge**: When an upstream Bronze or Silver dataset is purged due to TTL expiration, downstream Gold datasets and lineage provenance graphs must retain lightweight tombstone metadata (dataset ID, purge timestamp, TTL policy ID) so lineage trees remain unbroken and auditable.
- **Resource Budget During Cleanup**: Background cleanup tasks must operate in bounded batches so memory consumption stays strictly within the platform's idle budget and does not degrade concurrent ingestion or analytical queries.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow authorized users (project owners and administrators) to set, update, inspect, and clear a TTL retention policy on any project dataset via both CLI and REST API.
- **FR-002**: System MUST support human-readable TTL duration expressions (hours, days, weeks, months, or `never`/infinite), configurable expiration granularity (whole-dataset/partition ingestion age by default, or row/partition event-timestamp pruning via an optional `timestamp_column`), as well as tier-level (Bronze, Silver, Gold) and project-level default TTL policies that apply automatically when a dataset does not specify an explicit override. When using ingestion-age granularity, overwriting a dataset MUST reset its TTL reference timestamp to the new ingestion time, whereas appending new batch files MUST track `ingested_at` per partition/file so older batch files expire independently without deleting newly appended files.
- **FR-003**: System MUST apply TTL policies to query data artifacts, including cached analytical query results, natural-language AI query cache entries, saved/materialized query result datasets, and query execution audit logs. Ephemeral query caches (analytical SQL and AI RAG caches) MUST be automatically invalidated if any underlying source dataset they depend on expires or is soft-deleted, whereas explicit materialized query exports and query audit logs MUST be governed independently by their own assigned TTL once created.
- **FR-004**: System MUST allow users executing queries or exporting query results to specify an explicit TTL for the generated query data artifact, bounded by the project's maximum retention policy.
- **FR-005**: System MUST enforce TTL boundaries at query time via transparent query-layer interception: the query service MUST exclude expired/`SOFT_DELETED` dataset files from S3 path/glob resolution and automatically apply `timestamp_column >= now - TTL` predicates (and graph entity/relationship expiration filters) across both raw SQL/Cypher queries (`artemis query`, `artemis project query`, AI agent tools) and dataset-named queries, as well as invalidating expired query cache entries.
- **FR-006**: System MUST execute an automated background cleanup schedule at configurable intervals using a two-stage deletion lifecycle: first marking expired whole datasets/partitions as `SOFT_DELETED` (and virtually soft-deleting expired rows in `timestamp_column` datasets via read-time filtering) during a configurable grace period (defaulting to 24 hours, or `0h` for immediate purge), and then permanently purging physical files/partitions, atomically compacting/rewriting partially expired `timestamp_column` files (for rows older than `TTL + grace_period`), and purging query data artifacts once the grace period elapses. During the grace period, authorized users MUST be able to restore `SOFT_DELETED` items (and virtually soft-deleted rows) to `ACTIVE` either via an explicit `restore` CLI/API command (coupled with a TTL extension or Retention Hold) or implicitly by updating the item's TTL to a non-expired duration or enabling a Retention Hold.
- **FR-007**: System MUST provide an on-demand cleanup command via CLI and API supporting a `--dry-run` mode that outputs a deterministic report of candidate items and reclaimable storage volume without deleting data.
- **FR-008**: When purging an expired dataset, the system MUST atomically coordinate cleanup across all storage layers: primary dataset files/partitions, associated knowledge graph entities/relationships (using reference counting so shared entities remain intact), and discovery catalog indexes.
- **FR-009**: When purging a dataset that participates in a data lineage graph, the system MUST replace the deleted dataset's catalog entry with a lightweight tombstone record preserving lineage provenance for surviving downstream datasets.
- **FR-010**: System MUST support placing and releasing a Retention Hold (legal/investigative hold) on individual datasets or projects, which suspends TTL expiration and auto-cleanup for held assets until lifted.
- **FR-011**: System MUST protect active operations by ensuring the auto-cleanup process skips or defers purging any dataset or partition currently locked by an active ingestion job, pipeline execution, or running analytical query.
- **FR-012**: System MUST record an immutable audit log entry for every automated and manual cleanup execution, detailing run ID, trigger source, start/end timestamps, datasets/query artifacts purged, bytes reclaimed, items skipped (due to holds or active locks), and any errors encountered.
- **FR-013**: All CLI commands for TTL configuration, retention status inspection, hold management, and cleanup execution MUST support standard formatted stdout output and `--json` output for automation.
- **FR-014**: Cross-project isolation and membership access controls MUST be strictly enforced: users can only configure TTLs, inspect retention statuses, or trigger on-demand cleanup for projects in which they hold appropriate ownership/admin permissions.

### Key Entities *(include if feature involves data)*

- **TTLPolicy**: Defines retention rules attached to a project, storage tier, dataset, or query artifact category. Key attributes: policy ID, target scope (project default, tier default, dataset override, query data), retention duration, expiration reference rule (ingestion time vs. event timestamp), deletion lifecycle mode, and retention hold status.
- **DatasetRetentionState**: Tracks the lifecycle state of a specific dataset or partition. Key attributes: dataset ID, project ID, effective TTL duration, policy source (explicit vs. inherited), reference timestamp, computed expiration timestamp, lifecycle status (`ACTIVE`, `EXPIRING_SOON`, `HELD`, `SOFT_DELETED` / `EXPIRED`, `PURGED`, `CLEANUP_PENDING_RETRY`), and last evaluated timestamp.
- **QueryDataArtifact**: Represents stored or cached data produced by analytical or natural-language queries. Key attributes: query artifact ID, project ID, artifact type (result cache, semantic RAG cache, materialized query export, query history log), creation timestamp, TTL duration, expiration timestamp, and byte size.
- **CleanupJobRun**: Audit record of a scheduled or on-demand cleanup execution. Key attributes: run ID, trigger type (`SCHEDULED`, `MANUAL`, `DRY_RUN`), scope (global or project-specific), started at, completed at, status (`RUNNING`, `SUCCESS`, `PARTIAL_FAILURE`, `FAILED`), datasets purged count, query artifacts purged count, graph elements pruned count, total bytes reclaimed, skipped items count, and structured error details.
- **LineageTombstone**: Lightweight placeholder retained in the catalog and lineage graph after an upstream dataset is purged by TTL cleanup. Key attributes: original dataset ID, project ID, tier, purged timestamp, applied TTL policy summary, and upstream/downstream lineage pointers.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can configure, update, or inspect a TTL policy on any dataset or query artifact category in under 2 seconds via CLI or API.
- **SC-002**: 100% of expired datasets and expired query data artifacts are excluded from analytical and natural-language query results immediately after their TTL timestamp elapses, even if the background physical purge has not yet executed.
- **SC-003**: Automated cleanup processes reclaim 100% of storage bytes from expired, non-held datasets and query artifacts within one scheduled cleanup interval of their eligibility for permanent purge, leaving zero orphaned graph nodes or stale discovery catalog entries.
- **SC-004**: 100% of datasets placed under a Retention Hold or actively being read by a running pipeline/query are protected from deletion during concurrent cleanup cycles.
- **SC-005**: Executing a `--dry-run` cleanup preview across a project with up to 1,000 datasets completes in under 5 seconds and accurately predicts the exact set of items and byte volume purged by an immediate subsequent live run.
- **SC-006**: Background cleanup execution adds less than 5% overhead to concurrent query latency and maintains total platform idle RAM strictly within the 12 GB system budget.
- **SC-007**: 100% of cleanup executions (scheduled, manual, and dry-run) produce a complete, queryable audit record with item counts and reclaimed storage metrics.

## Assumptions

- Sensible industry-standard default TTLs will be configured out-of-the-box if not overridden by a project owner (e.g., Bronze raw data: 30 days; Silver cleansed data: 90 days; Gold aggregated data: 365 days or permanent; cached query results: 1 hour; materialized query exports: 7 days; query history logs: 30 days).
- Only project owners and platform administrators can modify dataset TTL policies, toggle retention holds, or trigger manual live cleanup runs; regular project members can view TTL statuses, run `--dry-run` previews, and set TTLs on their own ad-hoc query exports within project limits.
- Background cleanup scheduling will leverage the platform's existing lightweight task/workflow scheduling architecture without introducing any heavyweight or JVM-based daemons.
- Reference counting on knowledge graph entities and discovery catalog nodes will determine whether graph elements can be deleted or merely disassociated from an expired dataset.
