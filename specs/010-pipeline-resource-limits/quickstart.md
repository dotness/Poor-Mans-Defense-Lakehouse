# Quickstart Guide: Customizable CPU and Memory Limits for Pipeline Runs

**Feature**: `010-pipeline-resource-limits` | **Date**: 2026-11-21 | **Spec**: [spec.md](./spec.md)

---

## Overview

This guide provides runnable validation scenarios demonstrating:
1. System default resource fallback (`2.0` CPU cores / `2g` memory) when limits are omitted.
2. Per-pipeline default resource configuration (`--default-cpu`, `--default-memory`) and per-run overrides (`--cpu`, `--memory`).
3. Administrator hard maximum cap validation (`4.0` CPU cores / `4g` memory) under both `reject` (default) and `clamp` overflow policies.
4. Runtime Out-of-Memory (`exit_code: 137`) detection and diagnostic reporting in pipeline run history.

See [api_contracts.md](./contracts/api_contracts.md) and [cli_contracts.md](./contracts/cli_contracts.md) for full payload schemas.

---

## 1. Prerequisites

- Docker daemon running on host (`docker info`).
- Platform services running (`make up`).
- Default environment settings active:
  - `DOCKER_RUNNER_CPU_LIMIT=2.0`
  - `DOCKER_RUNNER_MEMORY_LIMIT=2g`
  - `DOCKER_RUNNER_MAX_CPU_LIMIT=4.0`
  - `DOCKER_RUNNER_MAX_MEMORY_LIMIT=4g`
  - `DOCKER_RUNNER_RESOURCE_OVERFLOW_POLICY=reject`

---

## 2. Step 1: Create a Project and Pipeline with Pipeline-Level Resource Defaults

Create a workspace and a pipeline configured with `1.5` CPU cores and `1g` memory as its pipeline-level defaults:

```bash
artemis project create --id res-demo --name "Resource Limits Demo"

cat << 'EOF' > /tmp/transform_demo.py
import glob, pandas as pd
files = glob.glob('/workspace/input/*')
df = pd.DataFrame([{"status": "ok", "files": len(files)}])
df.to_parquet('/workspace/output/out.parquet', index=False)
print("Transformation complete")
EOF

artemis project pipeline create \
  --project res-demo \
  --name "bounded_transform" \
  --stage BRONZE_TO_SILVER \
  --script /tmp/transform_demo.py \
  --default-cpu 1.5 \
  --default-memory 1g
```

Verify the saved pipeline defaults:

```bash
artemis project pipeline get --project res-demo --name bounded_transform --json
```

Expected JSON fields include `"default_cpu_limit": 1.5` and `"default_memory_limit": "1g"`.

---

## 3. Step 2: Run Pipeline Using Inherited Pipeline Defaults vs. Per-Run Overrides

1. **Run without per-run flags** (resolves to pipeline defaults `1.5` CPU / `1g` memory):

```bash
artemis project pipeline run \
  --project res-demo \
  --name bounded_transform \
  --target-dataset silver_default_run \
  --target-tier silver \
  --json
```

Expected response fields:
- `"effective_cpu_limit": 1.5`
- `"effective_memory_limit": "1g"`
- `"resource_clamped": false`

2. **Run with per-run custom CPU and memory overrides** (`--cpu 2.5 --memory 2048m`):

```bash
artemis project pipeline run \
  --project res-demo \
  --name bounded_transform \
  --target-dataset silver_custom_run \
  --target-tier silver \
  --cpu 2.5 \
  --memory 2048m \
  --json
```

Expected response fields:
- `"effective_cpu_limit": 2.5`
- `"effective_memory_limit": "2048m"`
- `"requested_cpu_limit": 2.5`
- `"requested_memory_limit": "2048m"`
- `"resource_clamped": false`

---

## 4. Step 3: Validate Administrator Hard Cap Enforcement (`reject` vs. `clamp`)

1. **Exceeding Hard Cap under Default `reject` Policy**:

```bash
artemis project pipeline run \
  --project res-demo \
  --name bounded_transform \
  --target-dataset silver_rejected \
  --cpu 8.0 \
  --memory 8g
```

Expected outcome: Command fails with exit code `1` before launching any container and outputs a clear validation error referencing the `4.0` CPU / `4g` memory maximum cap.

2. **Minimum Operational Floor Validation (`< 0.1` CPU or `< 64m` Memory)**:

```bash
artemis project pipeline run \
  --project res-demo \
  --name bounded_transform \
  --target-dataset silver_too_small \
  --cpu 0.05 \
  --memory 16m
```

Expected outcome: Command fails with exit code `1` and reports minimum operational floor violation (`>= 0.1` CPU cores and `>= 64m` memory required).

3. **Clamping Policy (`DOCKER_RUNNER_RESOURCE_OVERFLOW_POLICY=clamp`)**:

```bash
DOCKER_RUNNER_RESOURCE_OVERFLOW_POLICY=clamp artemis project pipeline run \
  --project res-demo \
  --name bounded_transform \
  --target-dataset silver_clamped \
  --cpu 6.0 \
  --memory 6g \
  --json
```

Expected outcome: Run succeeds with `"effective_cpu_limit": 4.0`, `"effective_memory_limit": "4g"`, and `"resource_clamped": true`.

---

## 5. Step 4: Inspect Execution History

View all historical runs and their applied resource allocations:

```bash
artemis project pipeline runs --project res-demo
```

Expected output lists `CPU`, `MEMORY`, `STATUS`, `EXIT_CODE`, and `DURATION_MS` for each run.
