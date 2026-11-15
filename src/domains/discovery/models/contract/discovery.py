from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AttributeKnowledge(BaseModel):
    name: str = Field(..., description="Attribute/column name")
    physical_type: str = Field(..., description="Physical data type (e.g. VARCHAR, INTEGER)")
    inferred_type: Optional[str] = Field(default=None, description="Inferred semantic type")
    taxonomy: Optional[str] = Field(default=None, description="Mapped semantic taxonomy concept")
    confidence: Optional[float] = Field(default=None, description="Taxonomy mapping confidence")
    low_confidence: bool = Field(default=False, description="Flag indicating taxonomy confidence < high threshold")
    cardinality: float = Field(default=0.0, description="Estimated cardinality ratio (0.0 to 1.0)")
    null_ratio: float = Field(default=0.0, description="Ratio of null values (0.0 to 1.0)")
    pattern: Optional[str] = Field(default=None, description="Detected universal pattern (e.g. uuid, ip, email)")


class ResourceKnowledge(BaseModel):
    resource_id: str = Field(..., description="Dataset or resource identifier")
    format: str = Field(default="PARQUET", description="Data format (PARQUET, CSV, JSON, TEXT, GRAPH)")
    tier: str = Field(default="BRONZE", description="Storage tier (BRONZE, SILVER, GOLD)")
    record_count: int = Field(default=0, ge=0, description="Total record or line count")
    location_uri: Optional[str] = Field(default=None, description="Internal S3 or storage URI")
    kind: str = Field(default="tabular", description="Resource kind (tabular, json, text, graph)")
    attributes: List[AttributeKnowledge] = Field(default_factory=list, description="Extracted schema attributes")
    entity_counts: Dict[str, int] = Field(default_factory=dict, description="Counts of extracted entities by type")
    derived_from: List[str] = Field(default_factory=list, description="IDs of upstream source resources")


class WorkspaceKnowledgeContract(BaseModel):
    project_id: str = Field(..., description="Project workspace identifier")
    resources: List[ResourceKnowledge] = Field(default_factory=list, description="Knowledge resources cataloged")
    entity_type_counts: Dict[str, int] = Field(default_factory=dict, description="Aggregate counts by entity type")
    enrichment_status: str = Field(default="completed", description="Status: pending, running, completed, failed, skipped_no_ai")


class EntityMatch(BaseModel):
    project_id: str = Field(..., description="Matching project identifier")
    resource_id: str = Field(..., description="Matching resource identifier")
    tier: str = Field(default="BRONZE", description="Storage tier")
    attribute: str = Field(..., description="Field or attribute containing the entity")
    entity_type: str = Field(..., description="Entity classification (e.g. Identifier, Person, Organization)")
    value: str = Field(..., description="Original or matching entity value")
    match_method: str = Field(default="exact", description="Resolution method: exact, fuzzy")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Match confidence score")


class EntityCorrelationContract(BaseModel):
    query: str = Field(..., description="Search value or entity type queried")
    matches: List[EntityMatch] = Field(default_factory=list, description="Discovered entity matches across member projects")
    total_projects: int = Field(default=0, ge=0, description="Count of distinct member projects with matches")


class LineageNode(BaseModel):
    resource_id: str = Field(..., description="Resource identifier")
    project_id: str = Field(..., description="Project identifier")
    tier: str = Field(default="BRONZE", description="Storage tier")
    format: str = Field(default="PARQUET", description="Data format")


class LineageEdge(BaseModel):
    source: str = Field(..., description="Source resource ID")
    target: str = Field(..., description="Target resource ID")
    relationship: str = Field(default="DERIVED_FROM", description="Relationship type")
    run_id: Optional[str] = Field(default=None, description="Pipeline run ID if derived via pipeline")


class LineageContract(BaseModel):
    resource_id: Optional[str] = None
    dataset_id: Optional[str] = None
    project_id: str = Field(..., description="Target project ID")
    nodes: List[LineageNode] = Field(default_factory=list, description="Lineage graph nodes")
    edges: List[LineageEdge] = Field(default_factory=list, description="Lineage graph edges")
    is_root: bool = Field(default=False, description="True if resource has no upstream dependencies")

    def model_post_init(self, __context: Any) -> None:
        if not self.resource_id and self.dataset_id:
            self.resource_id = self.dataset_id
        elif not self.dataset_id and self.resource_id:
            self.dataset_id = self.resource_id
        if not self.resource_id:
            self.resource_id = ""
            self.dataset_id = ""


class IndexJobContract(BaseModel):
    job_id: str = Field(..., description="Unique job UUID")
    project_id: str = Field(..., description="Target project identifier")
    resource_id: str = Field(..., description="Target resource identifier")
    phase: str = Field(default="structural", description="phase: structural, enrichment")
    status: str = Field(default="pending", description="status: pending, running, completed, failed, skipped_no_ai")
    attempts: int = Field(default=1, ge=0, description="Execution attempt counter")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
