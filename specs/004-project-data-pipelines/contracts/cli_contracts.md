# CLI Interface Contracts: `artemis project`

**Feature**: `004-project-data-pipelines` | **Date**: 2026-10-12

---

## 1. Project Management CLI Commands

```bash
# 1. Create a project
artemis project create --id cyber-defense --name "Cyber Defense Operations" --desc "Perimeter network analysis"

# 2. List all projects
artemis project list [--json]

# 3. View project details and datasets
artemis project info --id cyber-defense [--json]

# 4. Delete project
artemis project delete --id cyber-defense
```

---

## 2. Ingestion CLI Commands

```bash
# Ingest tabular data into Bronze tier
artemis project ingest --project cyber-defense --dataset raw_logs --tier bronze --file ./network_traffic.csv

# Ingest graph entities into project knowledge graph
artemis project ingest-graph --project cyber-defense --file ./threat_recon.json
```

---

## 3. Shareable Pipeline Entity CLI Commands

```bash
# 1. Create and upload a pipeline with a script
artemis project pipeline create \
  --project cyber-defense \
  --name "normalize_logs" \
  --stage BRONZE_TO_SILVER \
  --script ./scripts/normalize.py \
  [--image artemis-pipeline-runner:latest]

# 2. List pipelines in project
artemis project pipeline list --project cyber-defense [--json]

# 3. Inspect pipeline definition and script
artemis project pipeline get --project cyber-defense --id pipe-123 [--json]

# 4. Update pipeline script
artemis project pipeline update --project cyber-defense --id pipe-123 --script ./scripts/normalize_v2.py

# 5. Delete pipeline
artemis project pipeline delete --project cyber-defense --id pipe-123
```

---

## 4. Pipeline Execution & Querying CLI Commands

```bash
# 1. Trigger a pipeline run with dataset mapping
artemis project pipeline run \
  --project cyber-defense \
  --id pipe-123 \
  --input-dataset raw_logs \
  --target-dataset clean_events \
  --target-tier silver \
  [--timeout 300] \
  [--json]

# 2. View pipeline execution history
artemis project pipeline runs --project cyber-defense --id pipe-123 [--json]

# 3. Query project-scoped tabular data via DuckDB
artemis project query --project cyber-defense \
  --sql "SELECT count(*), avg(bytes) FROM read_parquet('s3://telemetry/projects/cyber-defense/silver/**/*.parquet')" \
  [--json]
```
