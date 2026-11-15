# Quickstart Guide: Project Data Pipelines Validation

**Feature**: `004-project-data-pipelines` | **Date**: 2026-10-12

---

## Overview
This guide provides an end-to-end runnable walkthrough demonstrating project creation, raw data ingestion into Bronze, custom pipeline creation with user script, Docker-sandboxed execution to Silver, and scoped query verification.

---

## 1. Prerequisites
- Docker daemon running on host (`docker info`).
- Artemis services active (`make up` or Docker Swarm running).
- CLI authenticated (`artemis login -u admin -p admin`).

---

## 2. Step 1: Create a Project
Create a new project workspace:
```bash
artemis project create --id alpha-ops --name "Alpha Operations" --desc "Test project for medallion pipeline validation"
```
Verify the project exists:
```bash
artemis project list
```
Expected output:
```text
PROJECT_ID    NAME               STATUS    CREATED_AT
alpha-ops     Alpha Operations   ACTIVE    2026-10-12 ...
```

---

## 3. Step 2: Ingest Raw Data into Bronze Tier
Create a sample raw telemetry CSV file:
```bash
cat << 'EOF' > /tmp/sample_traffic.csv
timestamp,device_id,metric_name,value,unit
2026-10-12T12:00:00Z,sensor-101,cpu_usage,78.5,percent
2026-10-12T12:01:00Z,sensor-102,cpu_usage,94.2,percent
2026-10-12T12:02:00Z,sensor-103,cpu_usage,45.1,percent
EOF
```
Ingest it into `alpha-ops` under the Bronze tier:
```bash
artemis project ingest --project alpha-ops --dataset raw_metrics --tier bronze --file /tmp/sample_traffic.csv
```
Expected output:
```text
Successfully ingested 3 records into alpha-ops (tier: bronze, dataset: raw_metrics).
Storage URI: s3://telemetry/projects/alpha-ops/bronze/raw_metrics/...
```

---

## 4. Step 3: Create a Shareable Pipeline Entity with Script
Create a custom Python transformation script that cleans the data and flags high CPU anomalies:
```bash
cat << 'EOF' > /tmp/clean_and_flag.py
import os
import glob
import pandas as pd

# Standard Docker runner contract: read from /workspace/input, write to /workspace/output
input_files = glob.glob('/workspace/input/*')
if not input_files:
    print("No input files found!")
    exit(0)

dfs = []
for f in input_files:
    if f.endswith('.csv'):
        dfs.append(pd.read_csv(f))
    elif f.endswith('.parquet'):
        dfs.append(pd.read_parquet(f))

if dfs:
    df = pd.concat(dfs, ignore_index=True)
    # Transformation: normalize values and flag anomalies
    df['is_anomaly'] = df['value'] > 90.0
    df['processed_by'] = 'custom_user_script_v1'
    
    output_path = '/workspace/output/cleaned_metrics.parquet'
    df.to_parquet(output_path, index=False)
    print(f"Processed {len(df)} records. Output written to {output_path}")
EOF
```

Register the pipeline under `alpha-ops`:
```bash
artemis project pipeline create \
  --project alpha-ops \
  --name "filter_high_cpu" \
  --stage BRONZE_TO_SILVER \
  --script /tmp/clean_and_flag.py
```
Expected output:
```text
Created pipeline 'filter_high_cpu' (ID: pipe-...) for project alpha-ops.
Stage: BRONZE_TO_SILVER | Version: 1
```

---

## 5. Step 4: Execute the Docker-Sandboxed Pipeline Run
Trigger the pipeline run, specifying the Bronze source dataset and Silver destination:
```bash
artemis project pipeline run \
  --project alpha-ops \
  --name filter_high_cpu \
  --input-dataset raw_metrics \
  --target-dataset clean_anomalies \
  --target-tier silver
```
Expected output:
```text
Pipeline run completed successfully:
Status: SUCCESS
Records Processed: 3
Execution Time: 1250ms
Output: s3://telemetry/projects/alpha-ops/silver/clean_anomalies/...
```

---

## 6. Step 5: Verify Project-Scoped Analytical Queries
Query the refined Silver data using DuckDB:
```bash
artemis project query --project alpha-ops \
  --sql "SELECT device_id, value, is_anomaly FROM read_parquet('s3://telemetry/projects/alpha-ops/silver/clean_anomalies/**/*.parquet')"
```
Expected output:
```text
device_id    value    is_anomaly
sensor-101   78.5     False
sensor-102   94.2     True
sensor-103   45.1     False
```

Verify cross-project isolation:
Querying `project-beta` yields zero results or returns 404:
```bash
artemis project query --project project-beta \
  --sql "SELECT * FROM read_parquet('s3://telemetry/projects/project-beta/silver/**/*.parquet')"
```
Output:
```text
No data found (telemetry lake in object storage is empty for project-beta).
```
