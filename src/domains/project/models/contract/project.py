from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ProjectCreateContract(BaseModel):
    project_id: str = Field(..., pattern=r"^[a-z0-9-_]+$", max_length=64, description="Unique project slug identifier")
    name: str = Field(..., min_length=1, max_length=128, description="Human-readable project name")
    description: Optional[str] = Field(default=None, description="Optional context or purpose of the project")


class ProjectResponseContract(BaseModel):
    project_id: str
    name: str
    description: Optional[str] = None
    status: str = "ACTIVE"
    created_at: datetime
    updated_at: datetime


class ProjectDatasetContract(BaseModel):
    project_id: str
    dataset_id: str
    tier: str = "BRONZE"
    dataset_type: str = "PARQUET"
    storage_uri: str
    size_bytes: int = 0
    record_count: int = 0
    last_modified: datetime


class TabularIngestRequestContract(BaseModel):
    dataset_name: str = Field(..., description="Dataset identifier")
    tier: str = Field(default="BRONZE", description="Target tier: BRONZE, SILVER, GOLD")
    filename: Optional[str] = Field(default="data.csv", description="Original filename")
    content_base64: Optional[str] = Field(default=None, description="Base64 encoded binary data (parquet/zip)")
    content_text: Optional[str] = Field(default=None, description="Plain text tabular data (CSV/JSON/TSV)")
    ttl_expression: Optional[str] = Field(default=None, description="Optional dataset TTL duration e.g. '30d', '7d', 'never'")
    timestamp_column: Optional[str] = Field(default=None, description="Optional event timestamp column for row-level TTL")
    overwrite: bool = Field(default=False, description="Whether to overwrite existing partitions and reset ingestion TTL clock")


class TabularIngestResponseContract(BaseModel):
    status: str = "SUCCESS"
    project_id: str
    tier: str
    dataset_name: str
    records_ingested: int
    storage_uri: str
    effective_ttl_expression: Optional[str] = None


class GraphNodeContract(BaseModel):
    name: str
    label: str = "ENTITY"
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphEdgeContract(BaseModel):
    source: str
    target: str
    relationship: str = "RELATED_TO"
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphIngestRequestContract(BaseModel):
    nodes: List[GraphNodeContract] = Field(default_factory=list)
    edges: List[GraphEdgeContract] = Field(default_factory=list)
    dataset_name: str = Field(default="knowledge_graph", description="Graph dataset identifier")
    ttl_expression: Optional[str] = Field(default=None, description="Optional TTL duration for this graph dataset")
    overwrite: bool = Field(default=False, description="Whether to reset TTL ingestion clock")


class GraphIngestResponseContract(BaseModel):
    status: str = "SUCCESS"
    project_id: str
    nodes_imported: int
    edges_imported: int
