# Data Model: Project-Scoped Data Ingestion & Medallion Pipelines

**Feature**: `004-project-data-pipelines` | **Date**: 2026-10-12

---

## 1. Relational Entities (PostgreSQL)

```mermaid
erDiagram
    PROJECT ||--o{ PROJECT_PIPELINE : "owns"
    PROJECT ||--o{ PROJECT_DATASET : "contains"
    PROJECT ||--o{ PIPELINE_RUN : "executes"
    PROJECT_PIPELINE ||--o{ PIPELINE_RUN : "triggers"

    PROJECT {
        string project_id PK "Unique slug, e.g. project-alpha"
        string name "Human-readable name"
        string description "Optional project context"
        string status "ACTIVE, ARCHIVED"
        timestamp created_at "Creation timestamp"
        timestamp updated_at "Last update timestamp"
    }

    PROJECT_PIPELINE {
        uuid pipeline_id PK "Unique pipeline identifier"
        string project_id FK "Owning project"
        string name "Pipeline name"
        string description "Pipeline purpose"
        string stage "INGESTION, BRONZE_TO_SILVER, SILVER_TO_GOLD, CUSTOM"
        text script_content "Python source code"
        string docker_image "Container image tag, default: artemis-runner:latest"
        int version "Monotonically increasing version"
        string created_by "Username / author"
        timestamp created_at "Created timestamp"
        timestamp updated_at "Updated timestamp"
    }

    PIPELINE_RUN {
        uuid run_id PK "Execution run identifier"
        string project_id FK "Project context"
        uuid pipeline_id FK "Triggered pipeline"
        string status "PENDING, RUNNING, SUCCESS, FAILED, TIMED_OUT"
        string stage "Executed stage"
        string target_tier "BRONZE, SILVER, GOLD"
        jsonb input_datasets "Array of source dataset identifiers"
        string target_dataset "Destination dataset name"
        int records_processed "Number of records written"
        int exit_code "Container exit code"
        text logs "Stdout and stderr captured from container"
        jsonb details "Execution metadata and error details"
        timestamp started_at "Run start time"
        timestamp completed_at "Run finish time"
    }

    PROJECT_DATASET {
        string dataset_id PK "Dataset slug or name within project"
        string project_id PK "Owning project"
        string tier "BRONZE, SILVER, GOLD"
        string dataset_type "PARQUET, GRAPH, JSON, CSV"
        string storage_uri "S3 URI or Memgraph tag"
        bigint size_bytes "Total byte size"
        bigint record_count "Total records/entities"
        timestamp last_modified "Last update"
    }
```

---

## 2. Storage Entities (MinIO & Memgraph)

### 2.1 MinIO Parquet Partitioning Scheme
Every project and tier is mapped to a dedicated S3 hierarchy:
```text
telemetry/
└── projects/
    └── {project_id}/
        ├── bronze/
        │   └── {dataset_name}/
        │       └── year=YYYY/month=MM/day=DD/raw_batch_{ts}_{uuid}.parquet (or .jsonl/.csv)
        ├── silver/
        │   └── {dataset_name}/
        │       └── year=YYYY/month=MM/day=DD/clean_batch_{ts}_{uuid}.parquet
        └── gold/
            └── {dataset_name}/
                └── year=YYYY/month=MM/day=DD/curated_batch_{ts}_{uuid}.parquet
```

### 2.2 Memgraph Graph Isolation Model
Entities ingested or extracted via project pipelines are tagged with `project_id`:
```cypher
(:LABEL {
    name: $name,
    project_id: $project_id,
    confidence: $confidence,
    tier: $tier,
    ...properties
})
```
Relationships:
```cypher
(a)-[:RELATIONSHIP {project_id: $project_id, tier: $tier, ...properties}]->(b)
```

---

## 3. Pydantic Domain Contracts

### 3.1 Project Contracts
```python
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class ProjectCreateContract(BaseModel):
    project_id: str = Field(..., pattern=r"^[a-z0-9-_]+$", max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None

class ProjectResponseContract(BaseModel):
    project_id: str
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
```

### 3.2 Pipeline & Script Contracts
```python
class PipelineCreateContract(BaseModel):
    name: str
    description: Optional[str] = None
    stage: str = Field(default="BRONZE_TO_SILVER") # INGESTION, BRONZE_TO_SILVER, SILVER_TO_GOLD, CUSTOM
    script_content: str
    docker_image: str = "artemis-pipeline-runner:latest"

class PipelineUpdateContract(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    stage: Optional[str] = None
    script_content: Optional[str] = None
    docker_image: Optional[str] = None

class PipelineResponseContract(BaseModel):
    pipeline_id: str
    project_id: str
    name: str
    description: Optional[str]
    stage: str
    docker_image: str
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime
```

### 3.3 Pipeline Run Contracts
```python
class PipelineRunTriggerContract(BaseModel):
    input_data: Optional[Dict[str, Any]] = None
    input_datasets: List[str] = Field(default_factory=list)
    target_dataset: str
    target_tier: str = Field(default="SILVER") # BRONZE, SILVER, GOLD
    parameters: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 300

class PipelineRunResponseContract(BaseModel):
    run_id: str
    project_id: str
    pipeline_id: str
    status: str # PENDING, RUNNING, SUCCESS, FAILED, TIMED_OUT
    stage: str
    target_tier: str
    target_dataset: str
    records_processed: int
    duration_ms: int
    exit_code: Optional[int]
    logs: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
```
