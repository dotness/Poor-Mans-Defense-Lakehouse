# Quickstart & Validation Guide: Dataset & Query Data TTL Management and Automated Cleanup

**Feature**: `009-dataset-ttl-cleanup`  
**Spec**: [spec.md](./spec.md) | **Data Model**: [data-model.md](./data-model.md) | **API Contracts**: [contracts/api_contracts.md](./contracts/api_contracts.md) | **CLI Contracts**: [contracts/cli_contracts.md](./contracts/cli_contracts.md)

---

## Prerequisites

1. Platform services running (`make up` or local pytest harness).
2. Python environment activated with `artemis` CLI installed (`pip install -e .`).
3. Verify platform health:
   ```bash
   artemis status
   ```

---

## Scenario 1: Per-Dataset TTL Configuration & Tier Default Inheritance (User Story 1)

1. **Create an isolated project and ingest a Bronze dataset without an explicit TTL**:
   ```bash
   artemis project create --project-id ttl-demo --name "TTL Lifecycle Demo"
   artemis project ingest --project ttl-demo --dataset sensor_events --tier bronze --file ./tests/fixtures/sample_telemetry.csv
   ```
2. **Inspect the inherited tier default TTL (`30d` for Bronze)**:
   ```bash
   artemis project ttl get --project ttl-demo --dataset sensor_events --tier bronze --json
   ```
   *Expected Outcome*: `policy_source` is `"TIER_DEFAULT"` (or `"PLATFORM_DEFAULT"`), `effective_ttl_expression` is `"30d"`, and `lifecycle_status` is `"ACTIVE"`.
3. **Override the dataset TTL with row-level `timestamp_column` granularity**:
   ```bash
   artemis project ttl set \
     --project ttl-demo \
     --dataset sensor_events \
     --tier bronze \
     --ttl 7d \
     --granularity TIMESTAMP_COLUMN \
     --timestamp-column timestamp \
     --grace-period 24h
   ```
   *Expected Outcome*: Policy updates in `< 2s` (`SC-001`) with `granularity: "TIMESTAMP_COLUMN"` and `timestamp_column: "timestamp"`.

---

## Scenario 2: Transparent Read-Time Filtering & Query Data Artifact TTL (User Story 2)

1. **Execute a scoped analytical query with a custom query cache TTL and materialized export TTL**:
   ```bash
   artemis project query \
     --project ttl-demo \
     --sql "SELECT device_id, COUNT(*) FROM read_parquet('s3://telemetry/projects/ttl-demo/bronze/sensor_events/**/*.parquet') GROUP BY device_id" \
     --cache-ttl 15m \
     --export-dataset device_counts_export \
     --export-ttl 2d \
     --json
   ```
   *Expected Outcome*:
   - Any rows where `timestamp < NOW() - INTERVAL '7 days'` are transparently excluded at read time (`FR-005`, `SC-002`).
   - A `SQL_RESULT_CACHE` artifact (`ttl_expression: "15m"`) and a `MATERIALIZED_EXPORT` artifact (`ttl_expression: "2d"`) are registered in `query_data_artifacts`.
2. **Verify immediate exclusion of expired whole-dataset data**:
   - Set a short TTL on a batch dataset or expire its policy timestamp, and re-run `artemis project query`.
   - *Expected Outcome*: The query returns `0 rows` immediately upon expiration—even before the background cleanup worker runs—and invalidates the dependent `SQL_RESULT_CACHE` while leaving `device_counts_export` governed by its own `2d` TTL (`FR-003`).

---

## Scenario 3: Dry-Run Preview, Two-Stage Soft-Delete, Restoration & Safe Purge (User Stories 3 & 4)

1. **Preview candidate cleanup actions using `--dry-run`**:
   ```bash
   artemis project ttl cleanup --project ttl-demo --dry-run --json
   ```
   *Expected Outcome*: Completes in `< 5s` (`SC-005`), listing candidate datasets, partitions, and query artifacts along with `bytes_reclaimed` without deleting any data.
2. **Place a Retention Hold on an investigative dataset**:
   ```bash
   artemis project ttl hold --project ttl-demo --dataset sensor_events --tier bronze --reason "Incident review"
   ```
   *Expected Outcome*: Dataset status becomes `"HELD"`; running `artemis project ttl cleanup --project ttl-demo` skips `sensor_events` and increments `skipped_held_count` (`SC-004`).
3. **Test Soft-Delete and Grace-Period Restoration**:
   - Release the hold (`artemis project ttl unhold --project ttl-demo --dataset sensor_events --tier bronze`) on an expired dataset with a `24h` grace period and trigger cleanup:
     ```bash
     artemis project ttl cleanup --project ttl-demo
     ```
   - *Expected Outcome*: Dataset transitions to `"SOFT_DELETED"` and is hidden from queries.
   - Restore the dataset during the grace period (explicitly via `restore` or implicitly by setting a longer `--ttl` or enabling `--hold`):
     ```bash
     artemis project ttl restore --project ttl-demo --dataset sensor_events --tier bronze --ttl 30d
     ```
   - *Expected Outcome*: Dataset returns to `"ACTIVE"` and is immediately queryable again (`FR-006`).
4. **Verify Permanent Purge, Reference-Counted Graph Pruning & Lineage Tombstones**:
   - Configure `--grace-period 0h` on an expired upstream Bronze dataset that has a derived Silver dataset, and run live cleanup:
     ```bash
     artemis project ttl cleanup --project ttl-demo --json
     ```
   -Inspect lineage and audit history:
     ```bash
     artemis discover lineage ttl-demo <derived_silver_dataset> --json
     artemis project ttl history --project ttl-demo --json
     ```
   - *Expected Outcome*:
     - Upstream S3 objects and unshared Memgraph entities are permanently removed (`SC-003`).
     - Shared graph entities referenced by other active datasets remain intact (`FR-008`).
     - The upstream dataset node in the lineage tree is preserved as a `LineageTombstone` (`FR-009`).
     - `artemis project ttl history` outputs the immutable `CleanupJobRun` audit record (`SC-007`).

---

## Automated Verification Suite

Run the full contract, unit, and integration test suite for Feature 009:

```bash
pytest tests/contract/test_retention_contracts.py \
       tests/unit/retention/ \
       tests/integration/test_dataset_ttl_cleanup.py -v
```
