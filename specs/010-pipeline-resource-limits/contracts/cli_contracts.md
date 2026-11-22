# CLI Contracts: Customizable CPU and Memory Limits for Pipeline Runs

**Feature**: `010-pipeline-resource-limits` | **Date**: 2026-11-21 | **Spec**: [spec.md](../spec.md)

All commands obey Constitution Principle II (Unified CLI Interface): formatted text/tables on `stdout`, errors on `stderr` with non-zero exit code (`1`), and full `--json` serialization support.

---

## 1. `artemis project pipeline create`

Adds optional `--default-cpu` and `--default-memory` options.

### Synopsis

```bash
artemis project pipeline create \
  --project <PROJECT_ID> \
  --name <PIPELINE_NAME> \
  --script <PATH_TO_SCRIPT> \
  [--stage BRONZE_TO_SILVER] \
  [--desc <DESCRIPTION>] \
  [--image artemis-pipeline-runner:latest] \
  [--default-cpu <FLOAT_CORES>] \
  [--default-memory <SIZE_STR>] \
  [--json]
```

### Standard Output

```text
Created pipeline 'cleanse_logs' (ID: 550e8400-e29b-41d4-a716-446655440000) for project alpha-ops.
Stage: BRONZE_TO_SILVER | Version: 1 | Default CPU: 1.5 cores | Default Memory: 1g
```

---

## 2. `artemis project pipeline update`

Adds optional `--default-cpu` and `--default-memory` options.

### Synopsis

```bash
artemis project pipeline update \
  --project <PROJECT_ID> \
  --id <PIPELINE_ID_OR_NAME> \
  [--script <PATH_TO_SCRIPT>] \
  [--name <NEW_NAME>] \
  [--stage <NEW_STAGE>] \
  [--default-cpu <FLOAT_CORES>] \
  [--default-memory <SIZE_STR>] \
  [--json]
```

---

## 3. `artemis project pipeline get`

Displays configured pipeline-level default CPU and memory limits (or indicates system defaults).

### Standard Output

```text
Pipeline: cleanse_logs (550e8400-e29b-41d4-a716-446655440000)
Stage: BRONZE_TO_SILVER | Version: 1 | Author: admin
Docker Image: artemis-pipeline-runner:latest
Default Resources: CPU=1.5 cores, Memory=1g
```

---

## 4. `artemis project pipeline run`

Adds optional `--cpu` and `--memory` per-run resource override options.

### Synopsis

```bash
artemis project pipeline run \
  --project <PROJECT_ID> \
  --name <PIPELINE_ID_OR_NAME> \
  [--input-dataset <DATASET_NAME> ...] \
  --target-dataset <TARGET_DATASET> \
  [--target-tier silver] \
  [--timeout 300] \
  [--cpu <FLOAT_CORES>] \
  [--memory <SIZE_STR>] \
  [--json]
```

### Standard Output (Success)

```text
Pipeline run completed successfully:
Status: SUCCESS
Run ID: 9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d
Records Processed: 1500
Execution Time: 1420ms (Exit Code: 0)
Resources Applied: CPU=3.0 cores, Memory=3g
Target Dataset: clean_network_logs (Tier: SILVER)
```

*(If clamped under `DOCKER_RUNNER_RESOURCE_OVERFLOW_POLICY=clamp`, displays `Resources Applied: CPU=4.0 cores, Memory=4g (CLAMPED)`.)*

### Standard Error (Validation Rejection or OOM Failure)

When rejected by hard cap validation (`exit code 1`):

```text
Error triggering pipeline run: Requested CPU limit 8.0 cores exceeds administrator hard maximum cap of 4.0 cores.
```

When terminated at runtime due to Out-of-Memory (`exit_code: 137`):

```text
Pipeline run FAILED (Exit Code: 137):
Resources Applied: CPU=1.5 cores, Memory=128m
Error: Out of Memory (OOM): Container killed (exit code 137) after exceeding effective memory limit of 128m.
```

---

## 5. `artemis project pipeline runs`

Includes applied CPU and memory limits in the historical execution table and JSON output.

### Standard Output

```text
RUN_ID        PIPELINE_ID   STATUS   STAGE             TARGET_DATASET      RECORDS   CPU   MEMORY   DURATION_MS   EXIT_CODE   STARTED_AT
------------  ------------  -------  ----------------  ------------------  --------  ----  -------  ------------  ----------  -------------------
9b1deb4d-3b7  550e8400-e29  SUCCESS  BRONZE_TO_SILVER  clean_network_logs  1500      3.0   3g       1420          0           2026-11-21T19:10:00
1c2deb4d-3b7  550e8400-e29  FAILED   BRONZE_TO_SILVER  clean_network_logs  0         1.5   128m     890           137         2026-11-21T19:12:00
```
