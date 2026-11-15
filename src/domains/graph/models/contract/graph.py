from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GraphNodeContract(BaseModel):
    name: str
    label: str
    confidence: float = 0.8
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphEdgeContract(BaseModel):
    source: str
    target: str
    relationship: str
    properties: Dict[str, Any] = Field(default_factory=dict)


class OsintImportRequestContract(BaseModel):
    raw_json_data: str


class OsintImportResultContract(BaseModel):
    nodes_imported: int
    edges_imported: int
    status: str = "SUCCESS"


class RelatedEntitiesResultContract(BaseModel):
    query_term: str
    entities: List[Dict[str, Any]] = Field(default_factory=list)
